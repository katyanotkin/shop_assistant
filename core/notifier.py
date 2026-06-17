import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import models
from .settings import Settings


def _format_match(m: models.ProductMatch) -> str:
    lines = [f"  Score {m.score}/10  {'[NEW]' if m.is_new else ''}"]
    lines.append(f"  {m.title or '(no title)'}")
    lines.append(f"  {m.url}")
    if m.price:
        lines.append(f"  Price: {m.price}")
    if m.matched:
        lines.append(f"  Matched: {', '.join(m.matched)}")
    if m.unmatched:
        lines.append(f"  Missing: {', '.join(m.unmatched)}")
    if m.notes:
        lines.append(f"  Notes: {m.notes}")
    return "\n".join(lines)


def send_run_notification(result: models.RunResult, settings: Settings) -> None:
    if not settings.notify_email or not settings.gmail_app_password:
        return
    new_matches = [m for m in result.matches if m.is_new]
    new_partials = [m for m in result.partial_matches if m.is_new]
    if not new_matches and not new_partials:
        return

    subject = f"Shop Assistant: {len(new_matches)} new match(es) for '{result.search_name}'"

    body_lines = [
        f"Search: {result.search_name}",
        f"Date: {result.run_date}",
        f"Candidates checked: {result.total_candidates}",
        "",
    ]

    if new_matches:
        body_lines.append(f"=== {len(new_matches)} NEW MATCH(ES) ===")
        for m in new_matches:
            body_lines.append(_format_match(m))
            body_lines.append("")

    if new_partials:
        body_lines.append(f"=== {len(new_partials)} NEW PARTIAL MATCH(ES) ===")
        for m in new_partials:
            body_lines.append(_format_match(m))
            body_lines.append("")

    if result.matches:
        body_lines.append(f"--- All matches ({len(result.matches)}) ---")
        for m in result.matches:
            body_lines.append(_format_match(m))
            body_lines.append("")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    from_addr = settings.gmail_from or settings.notify_email
    msg["From"] = from_addr
    msg["To"] = settings.notify_email
    msg.attach(MIMEText("\n".join(body_lines), "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(from_addr, settings.gmail_app_password)
        smtp.send_message(msg)
    print(f"  Notification sent to {settings.notify_email}")
