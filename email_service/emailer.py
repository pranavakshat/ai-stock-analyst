"""
email_service/emailer.py — Compile and send the daily AI stock digest via Resend.
"""

import logging
import resend
from datetime import date

from config import RESEND_API_KEY, EMAIL_RECIPIENT, EMAIL_FROM, MODELS

logger = logging.getLogger(__name__)

# Confidence badge colours
CONFIDENCE_COLORS = {
    "High":   ("#d1fae5", "#065f46"),   # green
    "Medium": ("#fef3c7", "#92400e"),   # amber
    "Low":    ("#fee2e2", "#991b1b"),   # red
}


# ── HTML Template ─────────────────────────────────────────────────────────────

def _build_html(all_picks: dict[str, list[dict]], today: str) -> str:
    model_sections = ""

    for model_key, picks in all_picks.items():
        display_name = MODELS.get(model_key, {}).get("display", model_key)
        color        = MODELS.get(model_key, {}).get("color", "#6b7280")

        if not picks:
            picks_html = (
                '<p style="color:#6b7280;font-style:italic;">'
                "No picks returned — API may be unavailable or key not set.</p>"
            )
        else:
            rows = ""
            for pick in sorted(picks, key=lambda p: p["rank"]):
                conf      = pick.get("confidence", "Medium")
                bg, fg    = CONFIDENCE_COLORS.get(conf, ("#f3f4f6", "#374151"))
                direction = pick.get("direction", "LONG").upper()
                alloc     = pick.get("allocation_pct", 20.0)
                dir_bg    = "#dcfce7" if direction == "LONG" else "#fee2e2"
                dir_fg    = "#166534" if direction == "LONG" else "#991b1b"
                dir_arrow = "&#9650; LONG" if direction == "LONG" else "&#9660; SHORT"
                rows += f"""
                <tr>
                  <td style="padding:10px 12px;font-size:22px;font-weight:700;
                              color:{color};width:30px;">#{pick['rank']}</td>
                  <td style="padding:10px 12px;">
                    <strong style="font-size:16px;letter-spacing:0.05em;">{pick['ticker']}</strong>
                    &nbsp;
                    <span style="background:{dir_bg};color:{dir_fg};font-size:11px;
                                 font-weight:700;padding:2px 8px;border-radius:999px;">
                      {dir_arrow}
                    </span>
                    &nbsp;
                    <span style="background:#ede9fe;color:#5b21b6;font-size:11px;
                                 font-weight:700;padding:2px 8px;border-radius:999px;">
                      {alloc:.0f}% alloc
                    </span>
                    &nbsp;
                    <span style="background:{bg};color:{fg};font-size:11px;
                                 font-weight:600;padding:2px 8px;border-radius:999px;">
                      {conf}
                    </span>
                    <p style="margin:6px 0 0;color:#4b5563;font-size:13px;line-height:1.5;">
                      {pick.get('reasoning','—')}
                    </p>
                  </td>
                </tr>
                <tr><td colspan="2" style="border-bottom:1px solid #e5e7eb;"></td></tr>
                """
            picks_html = f"<table style='width:100%;border-collapse:collapse;'>{rows}</table>"

        model_sections += f"""
        <div style="margin-bottom:32px;border-radius:12px;overflow:hidden;
                    border:1px solid #e5e7eb;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
          <div style="background:{color};padding:14px 20px;">
            <h2 style="margin:0;color:#fff;font-size:16px;font-weight:700;
                       font-family:sans-serif;">
              {display_name}
            </h2>
          </div>
          <div style="padding:4px 0;background:#fff;">
            {picks_html}
          </div>
        </div>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:system-ui,sans-serif;">
  <div style="max-width:680px;margin:32px auto;padding:0 16px;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);
                border-radius:12px;padding:28px 32px;margin-bottom:24px;text-align:center;">
      <h1 style="margin:0 0 4px;color:#fff;font-size:22px;font-weight:800;">
        AI Stock Analyst &mdash; Daily Picks
      </h1>
      <p style="margin:0;color:#bfdbfe;font-size:14px;">{today}</p>
    </div>

    <!-- Intro blurb -->
    <p style="color:#374151;font-size:14px;margin-bottom:24px;line-height:1.6;">
      Below are today's top picks from each AI model, ranked by conviction.
      Results and portfolio performance will be updated this evening after market close.
    </p>

    <!-- Model sections -->
    {model_sections}

    <!-- Footer -->
    <div style="text-align:center;padding:20px 0 32px;color:#9ca3af;font-size:12px;">
      Generated automatically by your AI Stock Analyst Agent &bull;
      Not financial advice &bull; Past performance does not guarantee future results
    </div>
  </div>
</body>
</html>
"""


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

def send_daily_digest(all_picks: dict[str, list[dict]], today: str | None = None):
    """Send the daily picks email via Resend."""
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY not configured — skipping email.")
        return

    if today is None:
        today = date.today().strftime("%A, %B %d, %Y")

    resend.api_key = RESEND_API_KEY

    subject   = f"AI Stock Picks — {today}"
    html_body = _build_html(all_picks, today)
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
        logger.error("Failed to send email via Resend: %s", exc)
        raise
