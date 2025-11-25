from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.config import settings


def _send_email(to_email: str, subject: str, html_content: str):
    """
    Internal helper to send an email using SendGrid.
    """
    message = Mail(
        from_email=settings.app_sender_email,
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )

    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        response = sg.send(message)
        print(f"Email sent to {to_email}, status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email to {to_email}: {e}")


def send_reset_email(to_email: str, token: str):
    subject = "Reset Your Sentry AI Password"
    reset_link = f"{settings.backend_base_url}/api/auth/reset-password?token={token}"  
    
    html_content = f"<p>Click <a href='{reset_link}'>here</a> to reset your password.</p>"
    _send_email(to_email, subject, html_content)


def send_verification_email(to_email: str, token: str):

    verification_link = f"{settings.backend_base_url}/api/auth/verify-email?token={token}"
    subject = "Verify Your Email"
    html_content = f"<p>Click <a href='{verification_link}'>here</a> to verify your email address.</p>"
    _send_email(to_email, subject, html_content)
