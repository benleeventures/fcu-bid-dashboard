"""
Shared logging setup for FCU bid-scanner scheduled jobs.

Every job's real output goes to logs/<name>.log through a size-capped rotating
handler (5 MB x 3 backups). We deliberately do NOT add a StreamHandler: launchd
redirects each job's stdout/stderr to logs/<name>.cron.log already, so a
StreamHandler would write every line twice (this was why supervisor.log grew to
~5 MB of duplicated "Ollama OK" lines).

The chatty HTTP client loggers (httpx / httpcore) are pinned to WARNING — their
per-request INFO lines were the bulk of digest.log / expirer.log volume.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).parent / "logs"

MAX_BYTES = 5_000_000
BACKUP_COUNT = 3
_NOISY = ("httpx", "httpcore", "hpack", "urllib3")


def setup(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure root logging for a scheduled job and return its named logger."""
    LOGS_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()

    handler = RotatingFileHandler(
        LOGS_DIR / f"{name}.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(level)

    for noisy in _NOISY:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger(name)
