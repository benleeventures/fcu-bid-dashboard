"""
Shared heartbeat writer used by all agents.
Each agent calls heartbeat() every loop iteration so supervisor.py can detect stalls.
"""

import os
from datetime import datetime, timezone

try:
    from supabase import create_client
except ImportError:
    create_client = None


def _client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key or create_client is None:
        return None
    return create_client(url, key)


def heartbeat(agent: str, status: str = "running", pid: int | None = None, error: str | None = None):
    """Write/update this agent's heartbeat row in agent_run_state."""
    sb = _client()
    if not sb:
        return

    row = {
        "agent": agent,
        "status": status,
        "heartbeat": datetime.now(timezone.utc).isoformat(),
    }
    if pid is not None:
        row["pid"] = pid
    if error is not None:
        row["last_error"] = error

    sb.table("agent_run_state").upsert(row, on_conflict="agent").execute()


def set_idle(agent: str):
    heartbeat(agent, status="idle")


def set_error(agent: str, error: str):
    heartbeat(agent, status="error", error=error)


def set_captcha_wait(agent: str):
    heartbeat(agent, status="paused_captcha")
