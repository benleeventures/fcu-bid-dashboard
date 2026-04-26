"""
Claude AI integration — generates context-aware follow-up suggestions per contact.
"""
from datetime import date

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def generate_suggestion(contact: dict, followup_log: list[dict]) -> str:
    """
    Returns a 1-3 sentence follow-up suggestion for a contact,
    based on their full interaction history.
    """
    today = date.today()
    days_since = None
    if contact["last_contacted"]:
        days_since = (today - contact["last_contacted"]).days

    # build history summary for the prompt
    history_lines = []
    for entry in followup_log[:10]:  # cap at 10 most recent
        d = entry["date"].isoformat() if entry["date"] else "unknown date"
        history_lines.append(
            f"- {d} | {entry['channel']} | Outcome: {entry['outcome']} | {entry['summary']}"
        )
    history_text = "\n".join(history_lines) if history_lines else "No prior touchpoints recorded."

    prompt = f"""You are a sales intelligence assistant for Floor Covering Unlimited (FCU), a commercial flooring contractor in Southern California. FCU sells to GCs, government agencies, and hospitality developers.

Contact: {contact['name']} at {contact['company']} ({contact['contact_type']})
Status: {contact['status']}
Days since last contact: {days_since if days_since is not None else 'never contacted'}
Rep notes: {contact['notes'] or 'none'}

Interaction history (newest first):
{history_text}

Write a specific, actionable follow-up suggestion for today. 2-3 sentences max. Be direct — no fluff. Recommend a specific channel (call, email, LinkedIn) and angle based on the history. If they haven't responded to emails, say so. If there's a positive signal to build on, reference it."""

    message = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
