"""
FCU Supervisor — Ollama health check + auto-restart
Runs every 2 minutes via launchd (com.fcu.supervisor).
If Ollama is down, attempts brew restart. If it stays down, sends email alert.
"""

import logging
import os
import subprocess
import time
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

LOG_FILE = Path(__file__).parent / "logs" / "supervisor.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ALERT_COOLDOWN_FILE = Path(__file__).parent / "logs" / "supervisor_alert.flag"
ALERT_COOLDOWN_SECS = 3600  # only send one alert email per hour


def check_ollama() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def restart_ollama() -> bool:
    log.warning("Attempting brew services restart ollama...")
    result = subprocess.run(
        ["brew", "services", "restart", "ollama"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        log.info("brew restart OK")
        return True
    log.error(f"brew restart failed: {result.stderr.strip()}")
    return False


def _alert_cooldown_active() -> bool:
    if not ALERT_COOLDOWN_FILE.exists():
        return False
    age = time.time() - ALERT_COOLDOWN_FILE.stat().st_mtime
    return age < ALERT_COOLDOWN_SECS


def send_alert():
    if _alert_cooldown_active():
        log.info("Alert suppressed — cooldown active")
        return
    ALERT_COOLDOWN_FILE.touch()
    try:
        from notify import _send_resend, _admin_recipients
        recipients = _admin_recipients()
        if not recipients:
            return
        _send_resend(
            recipients,
            "[FCU Supervisor] Ollama down — manual restart needed",
            """<div style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,sans-serif;padding:28px;border-radius:8px;max-width:480px;">
  <div style="border-left:3px solid #FF9F0A;padding-left:14px;margin-bottom:16px;">
    <p style="margin:0;font-size:11px;color:#8E8E93;text-transform:uppercase;letter-spacing:.08em;">FCU Supervisor</p>
    <h2 style="margin:6px 0 0;font-size:18px;">Ollama is down</h2>
  </div>
  <p style="color:#8E8E93;font-size:14px;">Auto-restart failed. PDF parsing will not run until Ollama is back up.</p>
  <p style="color:#8E8E93;font-size:14px;"><strong style="color:#F5F5F0;">Fix:</strong><br>
  SSH into the Mac mini and run:<br>
  <code style="background:#2C2C2E;padding:4px 8px;border-radius:4px;display:inline-block;margin-top:4px;">brew services restart ollama</code></p>
</div>""",
        )
        log.info("Alert email sent")
    except Exception as e:
        log.error(f"Alert send failed: {e}")


def main():
    if check_ollama():
        log.info("Ollama OK")
        return

    log.warning("Ollama not responding")
    restart_ollama()
    time.sleep(20)

    if check_ollama():
        log.info("Ollama recovered after restart")
        return

    log.error("Ollama still down after restart")
    send_alert()


if __name__ == "__main__":
    main()
