"""
Pacific-time trigger gate for the FCU scheduled jobs.

launchd's StartCalendarInterval fires based on whatever timezone the machine
currently thinks it's in. This machine has macOS's "Set time zone
automatically using current location" enabled, which silently overrode a
manually-set America/Los_Angeles timezone back to Europe/Berlin within two
days (observed 2026-09-15 -> 2026-09-17) — so a plain Hour/Minute trigger
drifts by however many hours separate the two zones, with no warning.

FCU is a Chatsworth, CA business; every scheduled job needs to run on Pacific
business hours regardless of what the OS's local-time display currently
says. The system's underlying UTC clock never drifts — only the *rendering*
of local time does — so this computes real Pacific wall time from UTC via
zoneinfo (fixed IANA tzdata) instead of trusting the OS's active zone.

Usage (each plist now fires every few minutes via StartInterval instead of
once via StartCalendarInterval):

    python3 pacific_schedule.py <job_name> <hour> [minute]
    # exit 0  -> proceed, caller should run the real job
    # exit 1  -> not yet time (or already ran today) — caller does nothing

A marker file per job/day ensures it fires at most once per Pacific calendar
day, the first poll at or after hour:minute — so it still runs once per
business day even if the target minute is missed entirely (e.g. the Mac was
asleep), catching up on the next poll instead of silently skipping the day.
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
_MARKER_DIR = Path(__file__).parent / "logs" / ".schedule"
_WEEKDAYS = range(5)  # Mon(0)-Fri(4)


def should_run(name: str, hour: int, minute: int = 0) -> bool:
    now = datetime.now(PACIFIC)
    marker = _MARKER_DIR / f"{name}.last_run"

    if now.weekday() not in _WEEKDAYS:
        return False
    if (now.hour, now.minute) < (hour, minute):
        return False

    today = now.date().isoformat()
    if marker.exists() and marker.read_text().strip() == today:
        return False

    _MARKER_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text(today)
    return True


if __name__ == "__main__":
    job_name = sys.argv[1]
    target_hour = int(sys.argv[2])
    target_minute = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    sys.exit(0 if should_run(job_name, target_hour, target_minute) else 1)
