import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import streamlit as st
from config import SMTP_SERVER, SMTP_PORT, SMTP_SENDER_EMAIL, SMTP_USERNAME, SMTP_PASSWORD


def send_email(receiver_email, subject, body_text):
    """Send a plain text email (used for OTP)."""
    try:
        message = MIMEMultipart()
        message["From"] = SMTP_SENDER_EMAIL
        message["To"] = receiver_email
        message["Subject"] = subject
        message.attach(MIMEText(body_text, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_SENDER_EMAIL, receiver_email, message.as_string())
        return True
    except Exception as e:
        st.error(f"SMTP Error: {e}")
        return False


def send_email_with_attachment(receiver_email, subject, body_html, attachments=None):
    """Send an HTML email with optional file attachments.
    
    Args:
        receiver_email: Recipient email address
        subject: Email subject line
        body_html: HTML body content
        attachments: List of dicts with 'bytes', 'filename', 'mime_type' keys
    """
    try:
        message = MIMEMultipart()
        message["From"] = SMTP_SENDER_EMAIL
        message["To"] = receiver_email
        message["Subject"] = subject
        message.attach(MIMEText(body_html, "html"))

        if attachments:
            for att in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(att["bytes"])
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{att["filename"]}"'
                )
                message.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_SENDER_EMAIL, receiver_email, message.as_string())
        return True
    except Exception as e:
        st.error(f"SMTP Error: {e}")
        return False
