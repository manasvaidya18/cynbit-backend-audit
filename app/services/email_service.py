"""
Email Notification Service.
Handles transactional dispatch for double opt-in verification and welcome notices.
Records dispatched events for auditability and automated testing inspection.
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
from app.config import settings


class EmailMessage:
    """Represents a structured transactional email message."""
    def __init__(
        self,
        recipient: str,
        subject: str,
        text_body: str,
        html_body: str,
        headers: Optional[Dict[str, str]] = None
    ):
        self.recipient = recipient
        self.subject = subject
        self.text_body = text_body
        self.html_body = html_body
        self.headers = headers or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict:
        return {
            "recipient": self.recipient,
            "subject": self.subject,
            "text_body": self.text_body,
            "headers": self.headers,
            "timestamp": self.timestamp.isoformat(),
        }


class EmailService:
    """
    Mock/Pluggable Transactional Email Delivery Service.
    In production, this delegates to AWS SES, Postmark, or SendGrid.
    In testing/demonstration, it logs to memory for automated assertions.
    """
    def __init__(self):
        self.outbox: List[EmailMessage] = []

    def send_verification_email(self, recipient: str, raw_token: str) -> EmailMessage:
        """
        Send Double Opt-In confirmation email with time-limited verification link.
        """
        verify_url = f"{settings.BASE_URL}/api/v1/newsletter/verify?token={raw_token}"
        subject = "Confirm Your Subscription - Cynbit Intelligence Network"
        
        text_body = (
            f"Hello,\n\n"
            f"Thank you for requesting to join the Cynbit Intelligence Network.\n"
            f"To complete your subscription and verify that you own this email address, "
            f"please click the link below (valid for {settings.TOKEN_EXPIRATION_HOURS} hours):\n\n"
            f"{verify_url}\n\n"
            f"If you did not request this subscription, please ignore this email. "
            f"You will not be subscribed without completing verification.\n\n"
            f"— The Cynbit Security Team"
        )

        html_body = (
            f"<html><body>"
            f"<h2>Confirm Your Subscription</h2>"
            f"<p>Thank you for requesting to join the Cynbit Intelligence Network.</p>"
            f"<p><a href='{verify_url}' style='padding: 10px 20px; background: #0066cc; color: #fff; text-decoration: none; border-radius: 4px;'>"
            f"Verify My Email Address</a></p>"
            f"<p>This link expires in {settings.TOKEN_EXPIRATION_HOURS} hours.</p>"
            f"<p><em>If you did not make this request, no action is needed.</em></p>"
            f"</body></html>"
        )

        headers = {
            "X-Entity-Ref-ID": f"verify-{recipient}",
        }

        message = EmailMessage(recipient, subject, text_body, html_body, headers)
        self.outbox.append(message)
        return message

    def send_welcome_email(self, recipient: str, unsubscribe_token: str) -> EmailMessage:
        """
        Send Welcome email upon successful verification.
        Includes mandatory RFC 8058 compliant unsubscribe links and headers.
        """
        unsubscribe_url = f"{settings.BASE_URL}/api/v1/newsletter/unsubscribe?token={unsubscribe_token}"
        subject = "Welcome to Cynbit Intelligence Network"

        text_body = (
            f"Welcome to the Cynbit Intelligence Network.\n\n"
            f"Your email ({recipient}) has been successfully verified. You will receive "
            f"our threat intelligence briefings and technical updates.\n\n"
            f"----------------------------------------\n"
            f"Manage your preferences or unsubscribe at any time:\n"
            f"{unsubscribe_url}\n"
            f"----------------------------------------\n"
        )

        html_body = (
            f"<html><body>"
            f"<h2>Welcome to Cynbit</h2>"
            f"<p>Your email has been successfully verified. You are now subscribed to our network.</p>"
            f"<hr/>"
            f"<p style='font-size: 12px; color: #666;'>"
            f"You received this email because you opted in at cynbit.in. "
            f"<a href='{unsubscribe_url}'>Click here to Unsubscribe</a> at any time."
            f"</p>"
            f"</body></html>"
        )

        headers = {
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

        message = EmailMessage(recipient, subject, text_body, html_body, headers)
        self.outbox.append(message)
        return message

    def get_last_email_for(self, recipient: str) -> Optional[EmailMessage]:
        """Fetch latest message sent to a specific recipient."""
        for msg in reversed(self.outbox):
            if msg.recipient == recipient:
                return msg
        return None

    def clear(self) -> None:
        """Clear outbox."""
        self.outbox.clear()


# Global singleton instance for injection
email_service = EmailService()
