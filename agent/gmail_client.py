"""
Gmail API client — sends the morning digest email.
Uses OAuth2 with credentials stored in gmail_credentials.json.
On first run, opens a browser to authorize. Token is saved to gmail_token.json.
"""
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import GMAIL_SENDER, GMAIL_RECIPIENTS, GMAIL_CREDENTIALS_FILE, GMAIL_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _get_service():
    creds = None

    try:
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, SCOPES)
    except Exception:
        pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_digest(subject: str, html_body: str, plain_body: str) -> None:
    service = _get_service()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = ", ".join(GMAIL_RECIPIENTS)

    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
