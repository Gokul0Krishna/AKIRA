from google_auth import get_gmail_service
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64

class EmailSender:
    def __init__(self):
        self.service = get_gmail_service()
    
    def send_email(self, to, subject, body_html, body_text=None):
        """Send an email"""
        try:
            message = MIMEMultipart('alternative')
            message['To'] = to
            message['Subject'] = subject
            
            # Add plain text version (fallback)
            if body_text:
                part1 = MIMEText(body_text, 'plain')
                message.attach(part1)
            
            # Add HTML version
            part2 = MIMEText(body_html, 'html')
            message.attach(part2)
            
            # Encode message
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Send
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            
            print(f"✓ Email sent to {to} (Message ID: {result['id']})")
            return result
            
        except Exception as e:
            print(f"✗ Error sending email to {to}: {str(e)}")
            return None