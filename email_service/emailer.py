"""
email_service/emailer.py — Compile and send the daily AI stock digest via Resend.
"""

import logging
import resend
from datetime import date

from config import RESEND_API_KEY, EMAIL_RECIPIENT, EMAIL_FROM, MODELS, DASHBOARD_URL

logger = logging.getLogger(__name__)

# Confidence badge colours
CONFIDENCE_COLORS = {
    "High":   ("#d1fae5", "#065f46"),
    "Medium": ("#fef3c7", "#92400e"),
    "Low":    ("#fee2e2", "#991b1b"),
}

# Avatar emoji per model
MODEL_AVATARS = {
    "claude":  "🤖",
    "chatgpt": "💬",
    "grok":    "⚡",
    "gemini":  "✨",
}


# ── Snapshot card (above the fold) ────────────────────────────────────────────

def _snapshot_card(model_key: str, picks: list[dict]) -> str:
    display = MODELS.get(model_key, {}).get("display", model_key)
    color   = MODELS.get(model_key, {}).get("color", "#6b7280")
    avatar  = MODEL_AVATARS.get(model_key, "🤖")

    if not picks:
        body = '<tr><td style="padding:12px 14px;color:#9ca3af;font-style:italic;font-size:13px;">No picks returned</td></tr>'
    else:
        body = ""
        for pick in sorted(picks, key=lambda p: p["rank"]):
            direction = pick.get("direction", "LONG").upper()
            conf      = pick.get("confidence", "Medium")
            alloc     = float(pick.get("allocation_pct", 20.0))
            conf_bg, conf_fg = CONFIDENCE_COLORS.get(conf, ("#f3f4f6", "#374151"))

            if direction == "LONG":
                arrow_html = '<span style="color:#16a34a;font-size:18px;font-weight:900;line-height:1;">▲</span>'
            else:
                arrow_html = '<span style="color:#dc2626;font-size:18px;font-weight:900;line-height:1;">▼</span>'

            body += f"""
            <tr>
              <td style="padding:9px 14px;border-bottom:1px solid #f1f5f9;font-family:system-ui,sans-serif;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="width:22px;vertical-align:middle;">{arrow_html}</td>
                    <td style="vertical-align:middle;padding-left:6px;">
                      <strong style="font-size:15px;letter-spacing:0.06em;color:#0f172a;">{pick['ticker']}</strong>
                    </td>
                    <td style="text-align:right;vertical-align:middle;">
                      <span style="background:{conf_bg};color:{conf_fg};font-size:10px;
                                   font-weight:700;padding:2px 7px;border-radius:999px;
                                   display:inline-block;">{conf}</span>
                      <span style="color:#94a3b8;font-size:11px;margin-left:6px;">{alloc:.0f}%</span>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;
                  box-shadow:0 1px 4px rgba(0,0,0,0.07);background:#fff;">
      <tr>
        <td style="background:{color};padding:12px 14px;">
          <span style="color:#fff;font-size:15px;font-weight:800;
                       font-family:system-ui,sans-serif;">{avatar} {display}</span>
        </td>
      </tr>
      {body}
    </table>"""


# ── Full analysis section (below the fold) ───────────────────────────────────

def _full_analysis_section(model_key: str, picks: list[dict]) -> str:
    display = MODELS.get(model_key, {}).get("display", model_key)
    color   = MODELS.get(model_key, {}).get("color", "#6b7280")
    avatar  = MODEL_AVATARS.get(model_key, "🤖")

    if not picks:
        body = '<p style="color:#9ca3af;font-style:italic;padding:12px 16px;margin:0;">No picks returned.</p>'
    else:
        rows = ""
        for pick in sorted(picks, key=lambda p: p["rank"]):
            direction = pick.get("direction", "LONG").upper()
            conf      = pick.get("confidence", "Medium")
            alloc     = float(pick.get("allocation_pct", 20.0))
            conf_bg, conf_fg = CONFIDENCE_COLORS.get(conf, ("#f3f4f6", "#374151"))
            dir_bg  = "#dcfce7" if direction == "LONG" else "#fee2e2"
            dir_fg  = "#166534" if direction == "LONG" else "#991b1b"
            arrow   = "▲ LONG" if direction == "LONG" else "▼ SHORT"

            rows += f"""
            <tr>
              <td style="padding:12px 16px;border-bottom:1px solid #f1f5f9;
                         font-family:system-ui,sans-serif;vertical-align:top;">
                <div style="margin-bottom:6px;">
                  <strong style="font-size:16px;letter-spacing:0.05em;color:#0f172a;">
                    #{pick['rank']} {pick['ticker']}
                  </strong>
                  &nbsp;
                  <span style="background:{dir_bg};color:{dir_fg};font-size:10px;
                               font-weight:700;padding:2px 8px;border-radius:999px;">{arrow}</span>
                  &nbsp;
                  <span style="background:{conf_bg};color:{conf_fg};font-size:10px;
                               font-weight:700;padding:2px 8px;border-radius:999px;">{conf}</span>
                  &nbsp;
                  <span style="background:#ede9fe;color:#5b21b6;font-size:10px;
                               font-weight:700;padding:2px 8px;border-radius:999px;">{alloc:.0f}% alloc</span>
                </div>
                <div style="color:#4b5563;font-size:13px;line-height:1.6;">
                  {pick.get('reasoning', '—')}
                </div>
              </td>
            </tr>"""

        body = f"<table width='100%' cellpadding='0' cellspacing='0'>{rows}</table>"

    return f"""
    <div style="margin-bottom:24px;border-radius:12px;overflow:hidden;
                border:1px solid #e2e8f0;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <div style="background:{color};padding:12px 16px;">
        <span style="color:#fff;font-size:15px;font-weight:800;
                     font-family:system-ui,sans-serif;">{avatar} {display}</span>
      </div>
      {body}
    </div>"""


# ── Main HTML builder ─────────────────────────────────────────────────────────

def _build_html(all_picks: dict[str, list[dict]], today: str,
                session: str = "day", dashboard_url: str = "") -> str:
    model_keys = list(all_picks.keys())
    session_label = "🌙 Overnight Holds" if session == "overnight" else "☀️ Day Session Picks"
    session_sub   = ("Close → Tomorrow's Open" if session == "overnight"
                     else "Market Open → Close Today")

    # ── Snapshot grid (2×2 table) ──────────────────────────────────────────
    def _pair_row(key1, key2=None) -> str:
        c1 = _snapshot_card(key1, all_picks.get(key1, []))
        c2 = _snapshot_card(key2, all_picks.get(key2, [])) if key2 else ""
        td2 = f'<td width="50%" valign="top" style="padding:0 0 12px 6px;">{c2}</td>' if key2 else \
              '<td width="50%"></td>'
        return f"""
        <tr>
          <td width="50%" valign="top" style="padding:0 6px 12px 0;">{c1}</td>
          {td2}
        </tr>"""

    pairs = []
    keys  = model_keys[:]
    while keys:
        k1 = keys.pop(0)
        k2 = keys.pop(0) if keys else None
        pairs.append(_pair_row(k1, k2))

    snapshot_rows = "\n".join(pairs)

    # ── Full analysis sections ─────────────────────────────────────────────
    full_analysis = "\n".join(
        _full_analysis_section(k, all_picks.get(k, []))
        for k in model_keys
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    @media only screen and (max-width:600px) {{
      .col-half {{
        display:block !important;
        width:100% !important;
        padding:0 0 12px 0 !important;
      }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:system-ui,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:16px;">

  <!-- ── Header ── -->
  <div style="background:linear-gradient(135deg,#0f172a,#1d4ed8);border-radius:14px;
              padding:18px 24px;margin-bottom:16px;text-align:center;">
    <div style="font-size:11px;font-weight:700;letter-spacing:0.15em;color:#93c5fd;
                text-transform:uppercase;margin-bottom:4px;">AI Stock Analyst</div>
    <div style="font-size:22px;font-weight:900;color:#fff;margin-bottom:4px;">
      {session_label}
    </div>
    <div style="font-size:12px;color:#bfdbfe;margin-bottom:6px;">{session_sub} &bull; {today}</div>
    {f'<a href="{dashboard_url}" style="display:inline-block;margin-top:6px;background:rgba(255,255,255,0.15);color:#fff;text-decoration:none;font-size:12px;font-weight:700;padding:6px 18px;border-radius:999px;border:1px solid rgba(255,255,255,0.3);">📊 View Live Dashboard →</a>' if dashboard_url else ''}
  </div>

  <!-- ── Snapshot grid (above the fold) ── -->
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:4px;">
    {snapshot_rows}
  </table>

  <!-- ── Divider ── -->
  <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
    <tr>
      <td style="border-top:1px solid #cbd5e1;"></td>
      <td style="white-space:nowrap;padding:0 16px;color:#64748b;font-size:12px;
                 font-weight:600;text-transform:uppercase;letter-spacing:0.08em;">
        Full Analysis ↓
      </td>
      <td style="border-top:1px solid #cbd5e1;"></td>
    </tr>
  </table>

  <!-- ── Full analysis ── -->
  {full_analysis}

  <!-- ── Footer ── -->
  <div style="text-align:center;padding:16px 0 24px;color:#94a3b8;font-size:11px;
              line-height:1.6;">
    <strong style="color:#64748b;font-size:12px;">AI Stock Analyst Agent</strong>
    &mdash; Built by Pranav Akshat<br>
    Not financial advice &bull; Past performance does not guarantee future results
  </div>

</div>
</body>
</html>"""


def _build_plain_text(all_picks: dict[str, list[dict]], today: str) -> str:
    lines = [f"AI STOCK ANALYST — Daily Picks — {today}", "=" * 50, ""]
    for model_key, picks in all_picks.items():
        display = MODELS.get(model_key, {}).get("display", model_key)
        lines.append(f">> {display}")
        if not picks:
            lines.append("  (No picks — API unavailable)")
        else:
            for p in sorted(picks, key=lambda x: x["rank"]):
                direction = p.get("direction", "LONG").upper()
                lines.append(f"  #{p['rank']} {p['ticker']} [{direction}] [{p.get('confidence','?')}]")
                lines.append(f"     {p.get('reasoning','')}")
        lines.append("")
    lines.append("Not financial advice.")
    return "\n".join(lines)


# ── Send ──────────────────────────────────────────────────────────────────────

def send_daily_digest(all_picks: dict[str, list[dict]], today: str | None = None,
                      session: str = "day"):
    """Send the daily picks email via Resend."""
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY not configured — skipping email.")
        return

    if today is None:
        today = date.today().strftime("%A, %B %d, %Y")

    resend.api_key = RESEND_API_KEY

    session_label = "🌙 Overnight" if session == "overnight" else "☀️ Day Session"
    subject   = f"AI Stock Picks [{session_label}] — {today}"
    html_body = _build_html(all_picks, today, session=session, dashboard_url=DASHBOARD_URL)
    text_body = _build_plain_text(all_picks, today)

    try:
        params: resend.Emails.SendParams = {
            "from":    EMAIL_FROM,
            "to":      [EMAIL_RECIPIENT],
            "subject": subject,
            "html":    html_body,
            "text":    text_body,
        }
        response = resend.Emails.send(params)
        logger.info("Daily digest sent via Resend. ID: %s", response.get("id", "unknown"))
    except Exception as exc:
        # Log but don't re-raise — email failure must not abort the scheduler job
        # (picks are already saved to DB; dashboard still works without the email)
        logger.error("Failed to send email via Resend: %s", exc)
