"""
FCU Agent Supervisor — Ollama first-line watchdog with Claude API escalation.

Runs every 2 minutes via launchd.
Reads agent heartbeats from Supabase, tails log files, asks Ollama what to do.
Restarts stalled agents locally. Escalates to Claude API + emails Leo on ambiguous failures.

Usage:
  python supervisor.py
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
STALE_MINS   = 10   # heartbeat older than this = stall (unless captcha)

AGENT_CMDS = {
    "parser":   [sys.executable, str(BASE_DIR / "parser.py"),  "--auto"],
    "digest":   [sys.executable, str(BASE_DIR / "digest.py")],
    "jobwalk":  [sys.executable, str(BASE_DIR / "jobwalk.py")],
    "expirer":  [sys.executable, str(BASE_DIR / "expirer.py")],
    "scraper":  [sys.executable, str(BASE_DIR / "main.py"), "--source", "sam", "--headless"],
}

# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def get_agent_states() -> list[dict]:
    try:
        rows = _sb().table("agent_run_state").select("*").execute().data or []
        return rows
    except Exception as e:
        return [{"agent": "supabase", "status": "error", "last_error": str(e)}]

# ── Log tailing ───────────────────────────────────────────────────────────────

def tail_logs(lines: int = 100) -> str:
    parts = []
    for log_file in sorted(LOG_DIR.glob("*.log")):
        try:
            all_lines = log_file.read_text(errors="replace").splitlines()
            tail = "\n".join(all_lines[-lines:])
            parts.append(f"=== {log_file.name} ===\n{tail}")
        except Exception:
            pass
    return "\n\n".join(parts) or "(no logs)"

# ── Ollama ────────────────────────────────────────────────────────────────────

def ask_ollama(statuses: list[dict], logs: str) -> str:
    prompt = f"""You are a system supervisor for an automated bid scraping pipeline running on a Mac Mini.

Agent statuses (JSON):
{json.dumps(statuses, indent=2, default=str)}

Recent log tail:
{logs[:4000]}

Analyze the above. Respond with EXACTLY ONE of these options:
  ok
  restart:<agent_name>
  escalate:<short_reason>
  captcha_wait

Rules:
- "ok" if all agents are healthy or idle
- "restart:X" if a specific agent is stuck/errored and restarting it is safe
- "escalate:reason" if the situation is ambiguous, multiple agents failed, or you see a pattern change
- "captcha_wait" if the only non-idle agent has status paused_captcha

Reply with ONE LINE only, no explanation."""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        }, timeout=30)
        resp.raise_for_status()
        return resp.json().get("response", "").strip().lower().splitlines()[0]
    except Exception as e:
        return f"escalate:ollama_unreachable_{e}"

# ── Actions ───────────────────────────────────────────────────────────────────

def restart_agent(name: str):
    cmd = AGENT_CMDS.get(name)
    if not cmd:
        log(f"[supervisor] Unknown agent '{name}' — cannot restart")
        return
    log(f"[supervisor] Restarting {name}...")
    subprocess.Popen(cmd, cwd=str(BASE_DIR))


def escalate_to_claude(reason: str, statuses: list[dict], logs: str):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log("[supervisor] ANTHROPIC_API_KEY not set — cannot escalate")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": f"""FCU bid agent supervisor escalation.

Reason flagged by Ollama: {reason}

Agent statuses:
{json.dumps(statuses, indent=2, default=str)}

Recent logs:
{logs[:3000]}

Provide:
1. Diagnosis (1-2 sentences)
2. Suggested fix (1 concrete action or command)
Keep it short — this goes in an email to the system admin."""
        }]
    )

    diagnosis = msg.content[0].text if msg.content else "No diagnosis returned."
    send_escalation_email(reason, diagnosis, statuses)


def send_escalation_email(reason: str, diagnosis: str, statuses: list[dict]):
    api_key = os.getenv("RESEND_API_KEY")
    admin   = os.getenv("ADMIN_EMAIL")
    if not api_key or not admin:
        log(f"[supervisor] Cannot send escalation email — RESEND_API_KEY or ADMIN_EMAIL missing")
        return

    status_rows = "".join(
        f"<tr><td style='padding:4px 8px'>{s.get('agent','?')}</td>"
        f"<td style='padding:4px 8px;color:{'red' if s.get('status') == 'error' else 'inherit'}'>"
        f"{s.get('status','?')}</td>"
        f"<td style='padding:4px 8px;font-size:11px;color:#888'>{s.get('last_error') or ''}</td></tr>"
        for s in statuses
    )

    html = f"""
<body style="font-family:monospace;background:#FAF7F2;padding:24px">
  <h2 style="color:#C8922A">[FCU Agent] ⚠ {reason}</h2>
  <p><strong>Diagnosis:</strong> {diagnosis}</p>
  <table border="1" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:16px">
    <tr style="background:#E5DDD0"><th style="padding:4px 8px">Agent</th><th>Status</th><th>Error</th></tr>
    {status_rows}
  </table>
  <p style="margin-top:16px;color:#888;font-size:12px">
    SSH: <code>ssh mac-mini "cd ~/fcu && cat bid-scanner/logs/*.log | tail -50"</code>
  </p>
</body>"""

    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": "FCU Supervisor <agent@bids.benlee.ventures>",
            "to": [admin],
            "subject": f"[FCU Agent] ⚠ {reason}",
            "html": html,
        },
        timeout=10,
    )
    log(f"[supervisor] Escalation email sent to {admin}")

# ── Logging ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}  {msg}"
    print(line)
    (LOG_DIR / "supervisor.log").open("a").write(line + "\n")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("[supervisor] Starting check...")

    statuses = get_agent_states()
    logs     = tail_logs(100)

    # Pre-check: mark stale heartbeats as error before asking Ollama
    now = datetime.now(timezone.utc)
    for s in statuses:
        if s.get("status") in ("running",) and s.get("heartbeat"):
            try:
                hb = datetime.fromisoformat(s["heartbeat"].replace("Z", "+00:00"))
                if (now - hb) > timedelta(minutes=STALE_MINS):
                    s["status"] = "stale"
                    s["last_error"] = f"No heartbeat for >{STALE_MINS} min"
            except Exception:
                pass

    decision = ask_ollama(statuses, logs)
    log(f"[supervisor] Ollama decision: {decision}")

    if decision == "ok":
        log("[supervisor] All clear.")

    elif decision == "captcha_wait":
        log("[supervisor] Scraper paused for CAPTCHA — no action needed.")

    elif decision.startswith("restart:"):
        agent = decision.split(":", 1)[1].strip()
        restart_agent(agent)

    elif decision.startswith("escalate:"):
        reason = decision.split(":", 1)[1].strip()
        log(f"[supervisor] Escalating to Claude API: {reason}")
        escalate_to_claude(reason, statuses, logs)

    else:
        log(f"[supervisor] Unrecognized Ollama response: '{decision}' — escalating")
        escalate_to_claude(f"unrecognized_ollama_response: {decision}", statuses, logs)

    log("[supervisor] Done.")


if __name__ == "__main__":
    main()
