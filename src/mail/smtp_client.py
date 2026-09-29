import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

class EmailClient:
    """
    Sends professional emails with attachments via SMTP (Gmail, Outlook, etc.)
    """

    def __init__(self):
        self.smtp_user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or os.getenv("SENDER_EMAIL") or "").strip()
        self.smtp_host = (os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER") or ("smtp.gmail.com" if "@gmail.com" in self.smtp_user else "")).strip()
        port_raw = (os.getenv("SMTP_PORT") or "").strip()
        try:
            self.smtp_port = int(port_raw) if port_raw else 587
        except ValueError:
            self.smtp_port = 587

        self.smtp_password = (os.getenv("SMTP_PASSWORD") or "").strip().replace(" ", "")
        self.sender_name = (os.getenv("SENDER_NAME") or "Job Automation Agent").strip()

        if not all([self.smtp_host, self.smtp_port, self.smtp_user, self.smtp_password]):
            print("[INFO] Email credentials not fully set in .env. Email sending disabled.")
            self.enabled = False
        else:
            self.enabled = True

    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        attachment_path: str = None,
        cc_emails: list = None,
        bcc_emails: list = None
    ) -> bool:
        """
        Sends an email with optional CC/BCC and resume attachment.

        Returns True on success, False on failure.
        """
        if not self.enabled:
            print("Email sending disabled. Check your .env file for SMTP settings.")
            return False

        # Create the email message
        msg = MIMEMultipart()
        msg["From"] = f"{self.sender_name} <{self.smtp_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        if cc_emails:
            msg["Cc"] = ", ".join(cc_emails)

        # Combine To + CC for actual recipients
        recipients = [to_email]
        if cc_emails:
            recipients.extend(cc_emails)
        if bcc_emails:
            recipients.extend(bcc_emails)

        # Add body
        msg.attach(MIMEText(body, "html" if "<html>" in body.lower() else "plain", "utf-8"))

        # Add attachment (e.g., tailored resume PDF)
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())
                encoders.encode_base64(part)
                filename = os.path.basename(attachment_path)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={filename}",
                )
                msg.attach(part)
                print(f"📎 Attachment added: {filename}")
            except Exception as e:
                print(f"⚠️ Could not attach {attachment_path}: {e}")

        # Send via SMTP
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.ehlo()
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.smtp_user, recipients, msg.as_string())
            server.quit()
            print(f"✅ Email sent to {to_email}")
            return True
        except Exception as e:
            print(f"❌ Email send failed: {e}")
            return False
