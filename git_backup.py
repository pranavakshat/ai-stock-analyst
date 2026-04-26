"""
git_backup.py — auto-commit + push the backups/ folder.

Why: Railway free tier wipes the SQLite DB on every redeploy. The recovery
path is restore_from_backups() reading committed CSVs from backups/. The
auto-backup writes those CSVs but never commits them, so any redeploy
between manual commits loses data. This helper closes that gap by
committing + pushing backups/ at the end of every scheduled job.

Designed to fail safe: every function returns False on any error and
logs a warning. A push failure must never crash the morning/evening job.

Required env vars (only on hosts that should push):
  BACKUP_GIT_PUSH=1                — opt-in flag
  GH_TOKEN=<github personal token> — fine-scoped PAT with contents:write
                                     on this repo
  GIT_USER_NAME / GIT_USER_EMAIL   — optional, defaults set below
"""

from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent
BACKUPS_DIR = REPO_ROOT / "backups"

DEFAULT_GIT_USER_NAME = "AI Stock Analyst Bot"
DEFAULT_GIT_USER_EMAIL = "ai-stock-analyst-bot@users.noreply.github.com"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a git command in the repo root with captured output."""
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def _has_changes_in_backups() -> bool:
    """True iff there's anything new/modified under backups/ vs HEAD."""
    res = _run(["git", "status", "--porcelain", "--", "backups/"])
    return res.returncode == 0 and bool(res.stdout.strip())


def _ensure_identity() -> None:
    """Set git user.name / user.email locally if not already configured."""
    name = os.environ.get("GIT_USER_NAME", DEFAULT_GIT_USER_NAME)
    email = os.environ.get("GIT_USER_EMAIL", DEFAULT_GIT_USER_EMAIL)
    _run(["git", "config", "user.name", name])
    _run(["git", "config", "user.email", email])


def _authed_remote_url(token: str) -> str | None:
    """
    Return the origin URL with the GH_TOKEN injected for HTTPS auth, or None
    if the remote isn't an https GitHub URL we recognise.
    """
    res = _run(["git", "remote", "get-url", "origin"])
    if res.returncode != 0:
        return None
    url = res.stdout.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc.endswith("github.com"):
        return None
    # Inject x-access-token:<token>@ into netloc
    netloc = f"x-access-token:{token}@{parsed.netloc.split('@')[-1]}"
    return urlunparse(parsed._replace(netloc=netloc))


def git_autocommit_backups(label: str = "auto-backup") -> bool:
    """
    Stage backups/, commit with a timestamped message, push to origin.

    Returns True on a successful push, False otherwise (no changes, no
    token, push failed, etc.). Never raises.
    """
    if os.environ.get("BACKUP_GIT_PUSH", "0") != "1":
        logger.info("git_autocommit_backups: BACKUP_GIT_PUSH != 1 — skipping.")
        return False

    if not BACKUPS_DIR.exists():
        logger.warning("git_autocommit_backups: backups/ dir missing — skipping.")
        return False

    # No-op if there's nothing to commit. Avoids empty-commit noise and
    # avoids racing pushes when both morning + evening land on the same minute.
    if not _has_changes_in_backups():
        logger.info("git_autocommit_backups: no changes under backups/ — skipping.")
        return False

    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        logger.warning("git_autocommit_backups: GH_TOKEN not set — cannot push.")
        return False

    try:
        # Resolve the authed push URL up-front so we can early-exit without
        # leaving a phantom local commit if the remote isn't auth-able.
        authed = _authed_remote_url(token)
        if not authed:
            logger.warning("git_autocommit_backups: origin is not an https GitHub URL — skipping.")
            return False

        _ensure_identity()

        add = _run(["git", "add", "--", "backups/"])
        if add.returncode != 0:
            logger.warning("git add backups/ failed: %s", add.stderr.strip())
            return False

        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = f"chore(backups): {label} {ts}"
        commit = _run(["git", "commit", "-m", msg])
        if commit.returncode != 0:
            # Could be "nothing to commit" if the index matched HEAD after add
            if "nothing to commit" in (commit.stdout + commit.stderr).lower():
                logger.info("git_autocommit_backups: nothing to commit after add.")
                return False
            logger.warning("git commit failed: %s", (commit.stderr or commit.stdout).strip())
            return False

        # Fetch + rebase on top of remote main so we don't fight a manual push.
        # Use the authed URL — the regular `origin` has no creds on Railway.
        fetch = _run(["git", "fetch", authed, "main"])
        if fetch.returncode != 0:
            logger.warning("git fetch failed (will still try push): %s",
                           (fetch.stderr or fetch.stdout).strip())
        else:
            rebase = _run(["git", "rebase", "--autostash", "FETCH_HEAD"])
            if rebase.returncode != 0:
                logger.warning("git rebase FETCH_HEAD failed (will still try push): %s",
                               (rebase.stderr or rebase.stdout).strip())
                # Abort the rebase so we don't leave the tree in REBASE state
                _run(["git", "rebase", "--abort"])

        push = _run(["git", "push", authed, "HEAD:main"])
        if push.returncode != 0:
            logger.warning("git push failed: %s", (push.stderr or push.stdout).strip())
            return False

        logger.info("git_autocommit_backups: pushed %s", msg)
        return True

    except Exception as exc:   # belt-and-braces — must never crash caller
        logger.warning("git_autocommit_backups: unexpected error: %s", exc)
        return False
