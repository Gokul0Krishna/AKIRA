def generate_summary(letter_text):
    # For now, just take the first 100 characters as a summary
    return letter_text[:100] + "..."

def send_email(to, subject, body):
    print(f"[EMAIL] To: {to}\nSubject: {subject}\n{body}")
    # Later integrate real email service (SMTP/SendGrid)
