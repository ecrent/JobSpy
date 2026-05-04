"""Send pipeline results via Gmail SMTP with PDF attachments (zipped)."""

import io
import logging
import os
import smtplib
import zipfile
from datetime import date
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

_SMTP_TIMEOUT = 30  # seconds per connection attempt


def _zip_pdfs(pdf_paths: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in pdf_paths:
            if os.path.isfile(path):
                zf.write(path, os.path.basename(path))
    return buf.getvalue()


def _smtp_send(gmail_user: str, gmail_password: str, notify_email: str, msg: MIMEMultipart) -> None:
    """Send via STARTTLS on port 587 (port 465 is blocked on this VPS)."""
    raw = msg.as_string()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=_SMTP_TIMEOUT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, notify_email, raw)


def send_results_email(jobs: list, pdf_paths: list[str]) -> bool:
    """Send an email with tailored CV PDFs zipped into one attachment.

    Returns True if the email was sent successfully.
    """
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD", "").strip().strip('"')
    notify_email = os.getenv("NOTIFY_EMAIL")

    if not all([gmail_user, gmail_password, notify_email]):
        log.error("Missing GMAIL_USER, GMAIL_APP_PASSWORD, or NOTIFY_EMAIL in environment")
        return False

    today = date.today().strftime("%Y-%m-%d")
    n = len(pdf_paths)
    subject = f"JobSpy Pipeline Results - {today} - {n} CV(s) Generated"

    lines = [
        f"JobSpy ran on {today} and generated {n} tailored CV(s).\n",
        "Job List",
        "=" * 60,
    ]
    for job in jobs:
        lines.append(f"  {job.company or 'Unknown'} | {job.title or 'Unknown'}")
        lines.append(f"  {job.job_url}")
        lines.append("")
    lines.append("=" * 60)
    lines.append("\nPDFs zipped and attached. Good luck!")

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = notify_email
    msg["Subject"] = subject
    msg.attach(MIMEText("\n".join(lines), "plain"))

    existing = [p for p in pdf_paths if os.path.isfile(p)]
    skipped = len(pdf_paths) - len(existing)
    if skipped:
        log.warning("Skipping %d missing PDF(s)", skipped)

    if existing:
        zip_bytes = _zip_pdfs(existing)
        zip_name = f"CVs_{today}.zip"
        part = MIMEBase("application", "zip")
        part.set_payload(zip_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{zip_name}"')
        msg.attach(part)
        log.info("Zipped %d PDF(s) into %s (%.1f KB)", len(existing), zip_name, len(zip_bytes) / 1024)

    try:
        _smtp_send(gmail_user, gmail_password, notify_email, msg)
        log.info("Email sent to %s", notify_email)
        return True
    except smtplib.SMTPAuthenticationError as e:
        log.error("Gmail authentication failed: %s", e)
    except Exception as e:
        log.error("Failed to send email: %s", e, exc_info=True)
    return False
