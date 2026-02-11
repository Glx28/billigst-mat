"""Email notification sender.

Builds a rich HTML digest email with:
  - Hero section showing the best deal per category (with product images)
  - Full leaderboard tables per category
  - Special offers section
  - Plain-text fallback
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from src.config import EMAIL_TO, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from src.constants import UNIT_SHORT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unit label helpers
# ---------------------------------------------------------------------------


def _unit_label(item: dict[str, Any]) -> str:
    tu = item.get("target_unit", "")
    return f"kr/{UNIT_SHORT.get(tu, '?')}"


# ---------------------------------------------------------------------------
# Plain-text email
# ---------------------------------------------------------------------------


def build_email(
    leaderboards: list[str],
    triggers: list[dict[str, str]],
) -> tuple[str, str]:
    """Build subject + plain-text body for the digest email."""
    trigger_count = len(triggers)
    if trigger_count > 0:
        subject = f"🛒 Matpris-oppdatering — {trigger_count} varsler"
    else:
        subject = "🛒 Matpris-oppdatering"

    sections: list[str] = []

    if triggers:
        sections.append("🔔 VARSLER:")
        for t in triggers:
            sections.append(f"  • [{t['type']}] {t['message']}")
        sections.append("")

    sections.append("=" * 50)
    sections.append("LEADERBOARD – Billigste per enhet")
    sections.append("=" * 50)
    sections.append("")
    for lb in leaderboards:
        sections.append(lb)

    return subject, "\n".join(sections)


# ---------------------------------------------------------------------------
# HTML email
# ---------------------------------------------------------------------------

# Color palette
_BG = "#f4f6f8"
_CARD_BG = "#ffffff"
_ACCENT = "#2d7d46"
_ACCENT_LIGHT = "#e8f5e9"
_TEXT = "#333333"
_TEXT_MUTED = "#888888"
_BORDER = "#e0e0e0"
_LINK = "#1a73e8"
_WARN_BG = "#fff8e1"
_WARN_BORDER = "#ffca28"


def _css_reset() -> str:
    """Email-client-safe wrapper styles."""
    return (
        f"<div style=\"font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
        f"width:100%;max-width:900px;margin:0 auto;padding:0;"
        f'background:{_BG};color:{_TEXT}">'
    )


def _hero_section(best_items: list[dict[str, Any]]) -> str:
    """Top banner with the #1 item from each category — table-based 3-col grid."""
    if not best_items:
        return ""

    cols = 2  # max columns per row

    html = (
        f'<div style="background:{_ACCENT};padding:24px 2px 8px;'
        f'border-radius:0 0 12px 12px">'
        f'<h1 style="color:#fff;margin:0 0 4px;font-size:22px;text-align:center">'
        f"🛒 Matpris-oppdatering</h1>"
        f'<p style="color:rgba(255,255,255,0.8);margin:0 0 16px;font-size:13px;text-align:center">'
        f"Beste pris per kategori</p>"
    )

    # Build card HTML for each item
    cards: list[str] = []
    for item in best_items:
        unit = _unit_label(item)
        display_name = item.get("_group_display", "")
        img_url = item.get("image", "")
        price = item.get("price", 0)
        unit_price = item.get("normalized_unit_price", 0)
        store = item.get("store", "?")
        name = item.get("name", "")
        url = item.get("url", "")

        img_html = ""
        if img_url:
            img_html = (
                f'<img src="{img_url}" alt="" '
                f'style="width:90px;height:90px;object-fit:contain;'
                f'border-radius:5px;display:block">'
            )
        else:
            emoji = display_name.split(" ")[0] if display_name else "🛒"
            img_html = (
                f'<div style="font-size:48px;line-height:90px;'
                f'width:90px;height:90px;text-align:center">{emoji}</div>'
            )

        name_linked = name
        if url:
            name_linked = (
                f'<a href="{url}" style="color:{_LINK};text-decoration:none">'
                f"{name}</a>"
            )

        card = (
            f'<div style="background:{_CARD_BG};border-radius:6px;'
            f'padding:4px;box-shadow:0 1px 2px rgba(0,0,0,0.08)">'
            f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%">'
            f"<tr>"
            f'<td style="width:90px;vertical-align:middle;padding-right:6px">{img_html}</td>'
            f'<td style="vertical-align:middle;padding:2px">'
            f'<div style="font-size:11px;font-weight:600;line-height:1.3;'
            f'margin-bottom:3px;word-wrap:break-word">{name_linked}</div>'
            f'<div style="font-size:8px;color:{_TEXT_MUTED};line-height:1.3">'
            f'<span style="font-weight:700;color:{_ACCENT}">{unit_price:.2f} {unit}</span>'
            f" · {price:.2f} kr @ {store}</div>"
            f"</td></tr></table></div>"
        )
        cards.append(card)

    # Render as <table> rows of 3 columns (email-client safe)
    html += (
        '<table cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;margin:0 auto;padding-bottom:8px">'
    )
    for row_start in range(0, len(cards), cols):
        row_cards = cards[row_start : row_start + cols]
        html += "<tr>"
        for card in row_cards:
            html += (
                f'<td style="width:{100 // cols}%;padding:3px;'
                f'vertical-align:top">{card}</td>'
            )
        # Fill remaining cells if row is incomplete
        for _ in range(cols - len(row_cards)):
            html += f'<td style="width:{100 // cols}%;padding:3px"></td>'
        html += "</tr>"
    html += "</table></div>"
    return html


def _triggers_section(triggers: list[dict[str, str]]) -> str:
    """Alert banner with trigger notifications."""
    if not triggers:
        return ""

    html = (
        f'<div style="background:{_WARN_BG};border:1px solid {_WARN_BORDER};'
        f'border-radius:8px;padding:14px 16px;margin:16px">'
        f'<h3 style="margin:0 0 8px;font-size:15px">🔔 Varsler ({len(triggers)})</h3>'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px">'
    )
    for t in triggers:
        badge_bg = {
            "new_best": "#c8e6c9",
            "below_threshold": "#bbdefb",
            "enters_top_n": "#fff9c4",
            "price_drop": "#ffccbc",
        }.get(t["type"], "#e0e0e0")

        html += (
            f"<tr>"
            f'<td style="padding:3px 6px 3px 0;vertical-align:top;white-space:nowrap">'
            f'<span style="background:{badge_bg};border-radius:4px;'
            f'padding:1px 6px;font-size:11px;font-weight:600">{t["type"]}</span></td>'
            f'<td style="padding:3px 0">{t["message"]}</td>'
            f"</tr>"
        )
    html += "</table></div>"
    return html


def _leaderboard_table(
    display_name: str,
    items: list[dict[str, Any]],
) -> str:
    """One category leaderboard as an HTML table."""
    if not items:
        return (
            f'<div style="margin:0 8px 12px">'
            f'<h3 style="margin:0 0 6px;font-size:15px">{display_name}</h3>'
            f'<p style="color:{_TEXT_MUTED};font-size:13px">Ingen resultater</p>'
            f"</div>"
        )

    unit = _unit_label(items[0])

    html = (
        f'<div style="margin:0 8px 12px;overflow-x:auto">'
        f'<h3 style="margin:0 0 6px;font-size:15px">{display_name}'
        f'<span style="font-weight:400;color:{_TEXT_MUTED};font-size:12px">'
        f" — sortert etter {unit}</span></h3>"
        f'<table style="width:100%;min-width:500px;border-collapse:collapse;font-size:12px;'
        f'border:1px solid {_BORDER};border-radius:6px;overflow:hidden">'
        f'<tr style="background:{_ACCENT_LIGHT}">'
        f'<th style="padding:4px;text-align:left;border-bottom:1px solid {_BORDER};font-size:11px">#</th>'
        f'<th style="padding:4px;text-align:left;border-bottom:1px solid {_BORDER}"></th>'
        f'<th style="padding:4px;text-align:left;border-bottom:1px solid {_BORDER};font-size:11px">Produkt</th>'
        f'<th style="padding:4px;text-align:right;border-bottom:1px solid {_BORDER};font-size:11px">Enhetspris</th>'
        f'<th style="padding:4px;text-align:right;border-bottom:1px solid {_BORDER};font-size:11px">Pris</th>'
        f'<th style="padding:4px;text-align:left;border-bottom:1px solid {_BORDER};font-size:11px">Butikk</th>'
        f"</tr>"
    )

    for i, item in enumerate(items, 1):
        bg = _CARD_BG if i % 2 == 1 else "#f9fafb"
        # Highlight #1
        if i == 1:
            bg = _ACCENT_LIGHT

        img_html = ""
        if item.get("image"):
            img_html = (
                f'<img src="{item["image"]}" alt="" '
                f'style="width:32px;height:32px;object-fit:contain;border-radius:3px">'
            )

        name = item["name"]
        if item.get("url"):
            name = f'<a href="{item["url"]}" style="color:{_LINK};text-decoration:none">{name}</a>'

        alt_links = ""
        for alt_url in item.get("alt_urls", []):
            alt_links += (
                f' · <a href="{alt_url}" style="color:{_TEXT_MUTED};'
                f'text-decoration:none;font-size:11px">🔗</a>'
            )

        validity = ""
        if item.get("valid_until"):
            validity = (
                f'<br><span style="color:{_TEXT_MUTED};font-size:11px">'
                f'Til {item["valid_until"][:10]}</span>'
            )

        promos = item.get("promos", [])
        promo_badge = ""
        if promos:
            promo_badge = (
                f'<br><span style="background:#ffecb3;border-radius:3px;'
                f'padding:1px 4px;font-size:10px;font-weight:600">'
                f"🏷️ {promos[0]}</span>"
            )

        source_tag = "📰" if item.get("source") == "etilbudsavis" else "🛒"
        unit_price = item.get("normalized_unit_price", 0)
        price = item.get("price", 0)
        store = item.get("store", "?")

        # Bold the best price
        price_weight = "700" if i == 1 else "600"

        html += (
            f'<tr style="background:{bg};border-bottom:1px solid {_BORDER}">'
            f'<td style="padding:3px 4px;text-align:center;color:{_TEXT_MUTED};font-size:11px">{i}</td>'
            f'<td style="padding:3px 4px">{img_html}</td>'
            f'<td style="padding:3px 4px;font-size:11px">{source_tag} {name}{alt_links}{validity}{promo_badge}</td>'
            f'<td style="padding:3px 4px;text-align:right;font-weight:{price_weight};'
            f'color:{_ACCENT if i == 1 else _TEXT};font-size:11px">{unit_price:.2f} {unit}</td>'
            f'<td style="padding:3px 4px;text-align:right;font-size:11px">{price:.2f} kr</td>'
            f'<td style="padding:3px 4px;font-size:11px">{store}</td>'
            f"</tr>"
        )

    html += "</table></div>"
    return html


def _promo_section(promo_items: list[dict[str, Any]]) -> str:
    """Special offers / promotions section."""
    if not promo_items:
        return ""

    sorted_promos = sorted(
        promo_items,
        key=lambda x: x.get("unit_price") or float("inf"),
    )

    html = (
        f'<div style="margin:16px">'
        f'<h2 style="font-size:17px;margin:0 0 8px">🏷️ Spesialtilbud</h2>'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;'
        f'border:1px solid {_BORDER};border-radius:6px;overflow:hidden">'
        f'<tr style="background:{_ACCENT_LIGHT}">'
        f'<th style="padding:6px;text-align:left;border-bottom:1px solid {_BORDER}">Tilbud</th>'
        f'<th style="padding:6px;text-align:left;border-bottom:1px solid {_BORDER}">Produkt</th>'
        f'<th style="padding:6px;text-align:right;border-bottom:1px solid {_BORDER}">Enhetspris</th>'
        f'<th style="padding:6px;text-align:right;border-bottom:1px solid {_BORDER}">Pris</th>'
        f'<th style="padding:6px;text-align:left;border-bottom:1px solid {_BORDER}">Butikk</th>'
        f"</tr>"
    )

    for i, item in enumerate(sorted_promos, 1):
        bg = _CARD_BG if i % 2 == 1 else "#f9fafb"
        promos = item.get("promos", [])
        promo_str = " | ".join(promos)
        bu = item.get("base_unit", "")
        bu_short = _UNIT_SHORT.get(bu, bu)
        up = item.get("unit_price", 0)
        price = item.get("price", 0)
        store = item.get("store", "?")
        name = item.get("name", "")
        url = item.get("url", "")

        if url:
            name = (
                f'<a href="{url}" style="color:{_LINK};text-decoration:none">{name}</a>'
            )

        html += (
            f'<tr style="background:{bg};border-bottom:1px solid {_BORDER}">'
            f'<td style="padding:6px"><span style="background:#ffecb3;'
            f"border-radius:3px;padding:2px 6px;font-size:11px;"
            f'font-weight:600">{promo_str}</span></td>'
            f'<td style="padding:6px">{name}</td>'
            f'<td style="padding:6px;text-align:right;font-weight:600">'
            f"{up:.2f} kr/{bu_short}</td>"
            f'<td style="padding:6px;text-align:right">{price:.2f} kr</td>'
            f'<td style="padding:6px">{store}</td>'
            f"</tr>"
        )

    html += "</table></div>"
    return html


def build_email_html(
    group_data: list[dict[str, Any]],
    triggers: list[dict[str, str]],
    promo_items: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Build subject + rich HTML body for the digest email.

    *group_data* is a list of dicts, each with:
      - display_name: str (e.g. "🥚 Egg")
      - top_items: list[dict]  (ranked items for this group)

    Returns (subject, body_html).
    """
    trigger_count = len(triggers)
    if trigger_count > 0:
        subject = f"🛒 Matpris-oppdatering — {trigger_count} varsler"
    else:
        subject = "🛒 Matpris-oppdatering"

    # Collect best item per group for hero section
    best_items: list[dict[str, Any]] = []
    for gd in group_data:
        items = gd.get("top_items", [])
        if items:
            best = items[0].copy()
            best["_group_display"] = gd["display_name"]
            best_items.append(best)

    # Build HTML
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '</head><body style="margin:0;padding:0">'
    )
    html += _css_reset()
    html += _hero_section(best_items)

    # Section header
    html += (
        f'<div style="margin:16px 8px 8px">'
        f'<h2 style="font-size:17px;margin:0;color:{_TEXT}">'
        f"📊 Full oversikt per kategori</h2></div>"
    )

    # Each category table
    for gd in group_data:
        html += _leaderboard_table(
            gd["display_name"],
            gd.get("top_items", []),
        )

    # Promos
    if promo_items:
        html += _promo_section(promo_items)

    # Varsler (alerts) at the bottom
    html += _triggers_section(triggers)

    # Footer
    html += (
        f'<div style="text-align:center;padding:16px;color:{_TEXT_MUTED};'
        f'font-size:11px;border-top:1px solid {_BORDER};margin-top:8px">'
        f"Generert av food-alert 🛒</div>"
        f"</div></body></html>"
    )

    return subject, html


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


def send_email(subject: str, body: str, body_html: str | None = None) -> bool:
    """Send an email via SMTP (HTML + plain-text fallback). Returns True on success."""
    if not all([SMTP_USER, SMTP_PASSWORD, EMAIL_TO]):
        logger.warning("Email not configured — skipping send")
        print("\n--- EMAIL PREVIEW (not sent) ---")
        print(f"Subject: {subject}")
        print(body)
        print("--- END PREVIEW ---\n")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, EMAIL_TO.split(","), msg.as_string())
        logger.info("Email sent to %s", EMAIL_TO)
        return True
    except Exception:
        logger.exception("Failed to send email")
        return False
