"""
FCU Sales Intelligence Agent — daily digest runner.

Run manually:   python main.py
Run on cron:    0 7 * * 1-5 cd /path/to/agent && python main.py
"""
import logging
from datetime import date

from ai_suggestions import generate_suggestion
from digest import build_html, build_plain
from gmail_client import send_digest
from notion_client import (
    get_bids_due_soon,
    get_contacts_needing_followup,
    get_followup_log_for_contact,
    get_new_bids,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run():
    log.info("Starting FCU digest run")

    # 1. Fetch data from Notion
    log.info("Fetching new bids...")
    new_bids = get_new_bids()
    log.info(f"  {len(new_bids)} new bids")

    log.info("Fetching bids due soon...")
    bids_due = get_bids_due_soon()
    log.info(f"  {len(bids_due)} bids due this week")

    log.info("Fetching contacts needing follow-up...")
    contacts = get_contacts_needing_followup()
    log.info(f"  {len(contacts)} contacts flagged")

    # 2. For each contact, fetch their log history and generate AI suggestion
    followups = []
    for contact in contacts:
        log.info(f"  Processing {contact['name']} ({contact['company']})...")
        followup_log = get_followup_log_for_contact(contact["id"])
        suggestion = generate_suggestion(contact, followup_log)
        followups.append((contact, followup_log, suggestion))

    # 3. Build and send digest
    today_str = date.today().strftime("%a %b %-d")
    subject = f"FCU Sales Digest — {today_str}"

    plain = build_plain(new_bids, bids_due, followups)
    html = build_html(new_bids, bids_due, followups)

    log.info("Sending digest email...")
    send_digest(subject, html, plain)
    log.info("Done.")


if __name__ == "__main__":
    run()
