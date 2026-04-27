# FCU Mac Mini Setup Runbook
**Machine:** Mac Mini M1 8GB · macOS Sonoma · Clean install

All commands are copy/paste ready. Run them in order.

---

## 1. Remote Access

```bash
# Enable SSH (also do this in System Settings → General → Sharing → Remote Login)
sudo systemsetup -setremotelogin on

# Install Tailscale for remote SSH from anywhere
brew install tailscale
sudo tailscale up
# Follow the browser prompt to join Leo's Tailnet
# After joining: ssh leo@mac-mini from any device on your Tailnet
```

---

## 2. Homebrew + Core Tools

```bash
/bin/bash -c "$(curl -fsSL https://brew.sh/install.sh)"
# Follow the post-install steps it prints (add Homebrew to PATH)

brew install git pyenv ollama
```

---

## 3. Python 3.11

```bash
pyenv install 3.11.9
pyenv global 3.11.9

# Verify
python --version   # should print Python 3.11.9

# Install Python dependencies
pip install playwright anthropic supabase resend python-dotenv requests
playwright install chromium
```

---

## 4. Ollama (local LLM supervisor)

```bash
# Start Ollama as a background service (auto-restarts on reboot)
brew services start ollama

# Pull the supervisor model (~2GB download)
ollama pull llama3.2:3b

# Test it
curl http://localhost:11434/api/generate \
  -d '{"model":"llama3.2:3b","prompt":"Reply with: ok","stream":false}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['response'])"
# Should print: ok
```

---

## 5. Clone the Project

```bash
git clone https://github.com/benleeventures/fcu-bid-scanner ~/fcu
cd ~/fcu
pip install -r bid-scanner/requirements.txt

# Set up environment
cp bid-scanner/.env.example bid-scanner/.env
nano bid-scanner/.env   # fill in all values (see .env.example comments)
```

**Required env vars to fill:**
- `SUPABASE_URL` + `SUPABASE_KEY`
- `ANTHROPIC_API_KEY` (Mac Mini dedicated key)
- `RESEND_API_KEY`
- `JOANNE_EMAIL`, `BEN_EMAIL`, `LENIN_EMAIL`, `ADMIN_EMAIL`
- `PLANETBIDS_EMAIL` + `PLANETBIDS_PASSWORD`
- `SAM_GOV_API_KEY`

---

## 6. Supabase Schema — One-time Setup

Run this in the Supabase SQL editor (Dashboard → SQL Editor):

```sql
-- Agent heartbeat table (supervisor reads this)
CREATE TABLE IF NOT EXISTS agent_run_state (
  agent       TEXT PRIMARY KEY,
  status      TEXT DEFAULT 'idle',
  started_at  TIMESTAMPTZ,
  heartbeat   TIMESTAMPTZ,
  last_error  TEXT,
  pid         INTEGER
);

-- Track which bids have had job walk emails sent to Lenin
ALTER TABLE bids ADD COLUMN IF NOT EXISTS walk_notified BOOLEAN DEFAULT FALSE;
```

---

## 7. Test Each Agent Manually

```bash
cd ~/fcu/bid-scanner

# Test scraper (SAM.gov only, headless)
python main.py --source sam --headless

# Test parser (processes any unprocessed PDFs)
python parser.py --pending

# Test expirer (dry run — check output before it runs for real)
python expirer.py

# Test job walk notifier
python jobwalk.py

# Test daily digest
python digest.py

# Test supervisor (Ollama must be running)
python supervisor.py
```

---

## 8. Install launchd Services

```bash
# Copy plist files to LaunchAgents directory
cp ~/fcu/setup/launchd/*.plist ~/Library/LaunchAgents/

# Load all FCU services
launchctl load ~/Library/LaunchAgents/com.fcu.scraper.plist
launchctl load ~/Library/LaunchAgents/com.fcu.parser.plist
launchctl load ~/Library/LaunchAgents/com.fcu.digest.plist
launchctl load ~/Library/LaunchAgents/com.fcu.jobwalk.plist
launchctl load ~/Library/LaunchAgents/com.fcu.expirer.plist
launchctl load ~/Library/LaunchAgents/com.fcu.supervisor.plist

# Verify they're loaded
launchctl list | grep fcu
```

Expected output — one line per service with PID (or 0 if not currently running):
```
-   0   com.fcu.scraper
-   0   com.fcu.parser
-   0   com.fcu.digest
-   0   com.fcu.jobwalk
-   0   com.fcu.expirer
-   0   com.fcu.supervisor
```

---

## 9. Verify Daily Schedule

| Time | Agent | What runs |
|------|-------|-----------|
| 6:00am | scraper | SAM.gov + BidNet headless scan |
| 6:30am | parser | PDF parsing → bid_specs |
| 7:00am | digest | Email Joanne + Ben: new relevant bids |
| 7:15am | jobwalk | Email Lenin: GO-scored bids with upcoming walks |
| 7:30am | expirer | Auto-archive past-due unbid bids |
| Every 2 min | supervisor | Ollama health check → restart/escalate |

---

## 10. PlanetBids — Manual Run

Run this whenever you have 5–10 minutes to be at the Mac Mini:

```bash
cd ~/fcu/bid-scanner
python main.py --source planetbids
```

- A Chrome browser window opens automatically
- When it hits a CAPTCHA or "I am not a robot" checkbox: solve it in the window
- Press **Enter** in the terminal to continue
- Browser closes when done

---

## 11. Pushing Code Fixes

Each launchd agent runs `git -C ~/fcu pull` before executing — so pushing a fix to GitHub propagates automatically on the next scheduled run.

For urgent fixes: SSH in and restart manually.

```bash
# From your laptop (on Tailnet)
ssh leo@mac-mini
cd ~/fcu && git pull
python bid-scanner/supervisor.py   # test supervisor manually
```

---

## 12. Logs

All agent logs write to `~/fcu/bid-scanner/logs/`.

```bash
# Watch supervisor in real time
tail -f ~/fcu/bid-scanner/logs/supervisor.log

# Check all logs
ls ~/fcu/bid-scanner/logs/
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Ollama not responding | `brew services restart ollama` |
| launchd service not starting | `launchctl unload` then `launchctl load` the plist |
| PlanetBids cookies expired | `python setup_cookies.py` — logs in fresh and saves cookies |
| Supabase connection error | Check SUPABASE_URL and SUPABASE_KEY in `.env` |
| Parser failing on a PDF | Check `bid-scanner/logs/parser.log` for the specific error |
