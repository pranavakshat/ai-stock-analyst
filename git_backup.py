"""
git_backup.py — auto-commit + push the backups/ folder.

Why: Railway free tier wipes the SQLite DB on every redeploy. The recovery
path is restore_from_backups() reading committed CSVs from backups/. The
auto-backup writes those CSVs but never commits them, so any redeploy
between manual commits loses data. This helper closes that gap by
committing + pushing backups/ at the end of every scheduled job.

Implementation: Railway's Nixpacks build typically does NOT include the
`.git` directory in the deployed image, so we can't run git commands in
place. Instead, on each invocation we:

  1. Shadow-clone the repo to /tmp via the authed GitHub URL
  2. Copy the freshly-written /app/backups/*.csv into the clone's backups/
  3. Stage / commit / push from the clone
  4. Clean up the clone

This is slightly slower than a local commit but is independent of how
the container was built. The shadow clone is shallow (depth=1) so it's
fast even as history grows.

Designed to fail safe: every function returns False on any error and
logs a warning. A push failure must never crash the morning/evening job.

Required env vars:
  BACKUP_GIT_PUSH=1                — opt-in flag
  GH_TOKEN=<github personal token> — fine-scoped PAT with contents:write
                                     on the target repo
  BACKUP_REPO_URL                  — optional override for the remote URL.
                                     Required if /app has no .git/config.
                                     Example:
                                       https://github.com/pranavakshat/ai-stock-analyst.git
  GIT_USER_NAME / GIT_USER_EMAIL   — optional; defaults set below
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent
BACKUPS_DIR = REPO_ROOT / "backups"

DEFAULT_GIT_USER_NAME = "AI Stock Analyst Bot"
DEFAULT_GIT_USER_EMAIL = "ai-stock-analyst-bot@users.noreply.github.com"

# Hard-coded fallback so deploys without BACKUP_REPO_URL still work for the
# project this file lives in. Override via env var if you fork the repo.
DEFAULT_REPO_URL = "https://github.com/pranavakshat/ai-stock-analyst.git"


def _run(cmd: list[str], cwd: str | None = None,
         **kwargs) -> subprocess.CompletedProcess:
    """Run a command with captured output. Never raises on non-zero exit."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def _resolve_remote_url() -> str | None:
    """
    Pick the remote URL to push to. Order of preference:
      1. BACKUP_REPO_URL env var
      2. `git remote get-url origin` if /app/.git exists
      3. DEFAULT_REPO_URL fallback
    """
    env = os.environ.get("BACKUP_REPO_URL", "").strip()
    if env:
        return env

    res = _run(["git", "remote", "get-url", "origin"], cwd=str(REPO_ROOT))
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()

    return DEFAULT_REPO_URL


def _build_authed_url(url: str, token: str) -> str | None:
    """Inject x-access-token:<token>@ into the netloc of an https://github.com URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc.endswith("github.com"):
        return None
    netloc_host = parsed.netloc.split("@")[-1]
    return urlunparse(parsed._replace(netloc=f"x-access-token:{token}@{netloc_host}"))


def _copy_backups_into(dest_dir: Path) -> int:
    """Copy /app/backups/*.csv into <dest>/backups/. Returns number of files copied."""
    if not BACKUPS_DIR.exists():
        return 0
    target = dest_dir / "backups"
    target.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in BACKUPS_DIR.glob("*.csv"):
        try:
            shutil.copy2(src, target / src.name)
            n += 1
        except Exception as exc:
            logger.warning("Failed copying %s into shadow clone: %s", src.name, exc)
    return n


def git_autocommit_backups(label: str = "auto-backup") -> bool:
    """
    Shadow-clone the repo, copy current backups/*.csv in, commit, push.
    Returns True on a successful push, False otherwise. Never raises.
    """
    if os.environ.get("BACKUP_GIT_PUSH", "0") != "1":
        logger.info("git_autocommit_backups: BACKUP_GIT_PUSH != 1 — skipping.")
        return False

    if not BACKUPS_DIR.exists():
        logger.warning("git_autocommit_backups: backups/ dir missing — skipping.")
        return False

    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        logger.warning("git_autocommit_backups: GH_TOKEN not set — cannot push.")
        return False

    remote_url = _resolve_remote_url()
    if not remote_url:
        logger.warning("git_autocommit_backups: could not resolve remote URL — skipping.")
        return False

    authed = _build_authed_url(remote_url, token)
    if not authed:
        logger.warning(
            "git_autocommit_backups: remote URL %r is not an https GitHub URL — skipping.",
            remote_url,
        )
        return False

    name  = os.environ.get("GIT_USER_NAME",  DEFAULT_GIT_USER_NAME)
    email = os.environ.get("GIT_USER_EMAIL", DEFAULT_GIT_USER_EMAIL)

    tmp = Path(tempfile.mkdtemp(prefix="ai-stock-analyst-clone-"))
    try:
        # 1. Shallow-clone main into the temp dir.
        clone = _run(["git", "clone", "--depth", "1", "--branch", "main",
                      authed, str(tmp / "repo")])
        if clone.returncode != 0:
            logger.warning(
                "git_autocommit_backups: clone failed: %s",
                (clone.stderr or clone.stdout).strip(),
            )
            return False
        repo = tmp / "repo"

        # 2. Configure identity inside the clone.
        _run(["git", "config", "user.name",  name],  cwd=str(repo))
        _run(["git", "config", "user.email", email], cwd=str(repo))

        # 3. Copy /app/backups/*.csv into the clone's backups/.
        copied = _copy_backups_into(repo)
        if copied == 0:
            logger.info("git_autocommit_backups: no CSVs in /app/backups/ to commit.")
            return False

        # 4. Stage and check whether anything actually differs from origin/main.
        _run(["git", "add", "--", "backups/"], cwd=str(repo))
        diff = _run(["git", "diff", "--cached", "--quiet"], cwd=str(repo))
        if diff.returncode == 0:
            # Exit 0 from --quiet means no staged differences.
            logger.info("git_autocommit_backups: backups already up to date on origin/main.")
            return False

        # 5. Commit and push.
        ts  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = f"chore(backups): {label} {ts}"
        commit = _run(["git", "commit", "-m", msg], cwd=str(repo))
        if commit.returncode != 0:
            logger.warning(
                "git_autocommit_backups: commit failed: %s",
                (commit.stderr or commit.stdout).strip(),
            )
            return False

        push = _run(["git", "push", "origin", "HEAD:main"], cwd=str(repo))
        if push.returncode != 0:
            logger.warning(
                "git_autocommit_backups: push failed: %s",
                (push.stderr or push.stdout).strip(),
            )
            return False

        logger.info("git_autocommit_backups: pushed %s (%d CSVs)", msg, copied)
        return True

    except Exception as exc:
        # Belt-and-braces — must never crash the calling job.
        logger.warning("git_autocommit_backups: unexpected error: %s", exc)
        return False
    finally:
        # Clean up the shadow clone — we never want it to grow on the FS.
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
