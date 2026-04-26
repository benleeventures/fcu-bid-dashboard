import os
from dotenv import load_dotenv

load_dotenv()

# Notion
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_CONTACTS_DB = os.environ["NOTION_CONTACTS_DB"]
NOTION_BIDS_DB = os.environ["NOTION_BIDS_DB"]
NOTION_FOLLOWUP_DB = os.environ["NOTION_FOLLOWUP_DB"]

# Claude
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL = "claude-sonnet-4-6"

# Gmail
GMAIL_SENDER = os.environ["GMAIL_SENDER"]
GMAIL_RECIPIENTS = os.environ["GMAIL_RECIPIENTS"].split(",")  # comma-separated
GMAIL_CREDENTIALS_FILE = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
GMAIL_TOKEN_FILE = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")

# Follow-up thresholds (days)
FOLLOWUP_WARNING_DAYS = 5   # flag contact if no touch in X days
FOLLOWUP_URGENT_DAYS = 10   # mark urgent if no touch in X days
BID_DEADLINE_WARN_DAYS = 7  # warn about bids due within X days
