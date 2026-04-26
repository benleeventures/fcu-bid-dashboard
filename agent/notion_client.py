"""
Notion API client — queries Contacts, Bids, and Follow-up Log databases.
"""
from datetime import date, datetime, timedelta
from typing import Any

import requests

from config import (
    NOTION_TOKEN,
    NOTION_CONTACTS_DB,
    NOTION_BIDS_DB,
    NOTION_FOLLOWUP_DB,
    FOLLOWUP_WARNING_DAYS,
    BID_DEADLINE_WARN_DAYS,
)

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def _query(database_id: str, filter_body: dict | None = None) -> list[dict]:
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    payload = {}
    if filter_body:
        payload["filter"] = filter_body

    results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = requests.post(url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data["results"])
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


# ── Property extractors ──────────────────────────────────────────────────────

def _text(prop: dict) -> str:
    if prop["type"] == "title":
        return "".join(t["plain_text"] for t in prop["title"])
    if prop["type"] == "rich_text":
        return "".join(t["plain_text"] for t in prop["rich_text"])
    return ""


def _select(prop: dict) -> str:
    s = prop.get("select")
    return s["name"] if s else ""


def _date(prop: dict) -> date | None:
    d = prop.get("date")
    if not d or not d.get("start"):
        return None
    return datetime.fromisoformat(d["start"]).date()


def _number(prop: dict) -> float | None:
    return prop.get("number")


def _email(prop: dict) -> str:
    return prop.get("email") or ""


def _phone(prop: dict) -> str:
    return prop.get("phone_number") or ""


def _relation_ids(prop: dict) -> list[str]:
    return [r["id"] for r in prop.get("relation", [])]


# ── Public query functions ───────────────────────────────────────────────────

def get_contacts_needing_followup() -> list[dict]:
    """
    Returns contacts where:
    - Status is not Won/Lost
    - Last Contacted is more than FOLLOWUP_WARNING_DAYS ago (or never)
    - OR Next Follow-up Date is today or past
    """
    today = date.today()
    cutoff = (today - timedelta(days=FOLLOWUP_WARNING_DAYS)).isoformat()

    filter_body = {
        "and": [
            {
                "property": "Status",
                "select": {"does_not_equal": "Won"},
            },
            {
                "property": "Status",
                "select": {"does_not_equal": "Lost"},
            },
            {
                "or": [
                    # last contacted is before cutoff
                    {"property": "Last Contacted", "date": {"before": cutoff}},
                    # never contacted
                    {"property": "Last Contacted", "date": {"is_empty": True}},
                    # next follow-up date is today or past
                    {"property": "Next Follow-up Date", "date": {"on_or_before": today.isoformat()}},
                ]
            },
        ]
    }

    rows = _query(NOTION_CONTACTS_DB, filter_body)
    contacts = []
    for r in rows:
        p = r["properties"]
        contacts.append({
            "id": r["id"],
            "name": _text(p["Name"]),
            "company": _text(p.get("Company", {"type": "rich_text", "rich_text": []})),
            "contact_type": _select(p.get("Contact Type", {"type": "select"})),
            "email": _email(p.get("Email", {"type": "email"})),
            "phone": _phone(p.get("Phone", {"type": "phone_number"})),
            "assigned_to": _select(p.get("Assigned To", {"type": "select"})),
            "status": _select(p.get("Status", {"type": "select"})),
            "last_contacted": _date(p.get("Last Contacted", {"type": "date"})),
            "next_followup": _date(p.get("Next Follow-up Date", {"type": "date"})),
            "notes": _text(p.get("Notes", {"type": "rich_text", "rich_text": []})),
        })
    return contacts


def get_new_bids() -> list[dict]:
    """Returns bids with Status = New."""
    filter_body = {"property": "Status", "select": {"equals": "New"}}
    rows = _query(NOTION_BIDS_DB, filter_body)
    return [_parse_bid(r) for r in rows]


def get_bids_due_soon() -> list[dict]:
    """Returns bids with Status != Won/Lost and due within BID_DEADLINE_WARN_DAYS."""
    today = date.today()
    deadline = (today + timedelta(days=BID_DEADLINE_WARN_DAYS)).isoformat()

    filter_body = {
        "and": [
            {"property": "Due Date", "date": {"on_or_before": deadline}},
            {"property": "Due Date", "date": {"on_or_after": today.isoformat()}},
            {"property": "Status", "select": {"does_not_equal": "Won"}},
            {"property": "Status", "select": {"does_not_equal": "Lost"}},
        ]
    }
    rows = _query(NOTION_BIDS_DB, filter_body)
    return [_parse_bid(r) for r in rows]


def _parse_bid(r: dict) -> dict:
    p = r["properties"]
    return {
        "id": r["id"],
        "bid_name": _text(p["Bid Name"]),
        "bid_number": _text(p.get("Bid Number", {"type": "rich_text", "rich_text": []})),
        "agency": _text(p.get("Agency", {"type": "rich_text", "rich_text": []})),
        "estimated_value": _number(p.get("Estimated Value", {"type": "number"})),
        "due_date": _date(p.get("Due Date", {"type": "date"})),
        "status": _select(p.get("Status", {"type": "select"})),
        "assigned_to": _select(p.get("Assigned To", {"type": "select"})),
        "notes": _text(p.get("Notes", {"type": "rich_text", "rich_text": []})),
    }


def get_followup_log_for_contact(contact_id: str) -> list[dict]:
    """Returns all follow-up log entries for a given contact, sorted newest first."""
    filter_body = {
        "property": "Contact",
        "relation": {"contains": contact_id},
    }
    rows = _query(NOTION_FOLLOWUP_DB, filter_body)
    entries = []
    for r in rows:
        p = r["properties"]
        entries.append({
            "date": _date(p.get("Date", {"type": "date"})),
            "channel": _select(p.get("Channel", {"type": "select"})),
            "summary": _text(p.get("Summary", {"type": "rich_text", "rich_text": []})),
            "outcome": _select(p.get("Outcome", {"type": "select"})),
            "next_action": _text(p.get("Next Action", {"type": "rich_text", "rich_text": []})),
            "logged_by": _select(p.get("Logged By", {"type": "select"})),
        })
    # sort newest first
    entries.sort(key=lambda e: e["date"] or date.min, reverse=True)
    return entries
