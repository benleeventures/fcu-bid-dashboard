import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// Off-machine dead-man's switch for the scheduled jobs on the Mac mini.
//
// The scraper and the email intake run there via launchd. When that machine
// reboots unattended (power cut, macOS update), FileVault holds it at the
// unlock screen and every job silently stops — nothing on the Mac can report
// that. Vercel Cron hits this route each weekday after the 06:00 PT scan
// should have finished and emails admin if either:
//   - no full scan has started yet today (Pacific), or
//   - the email intake (every 15 min) hasn't succeeded in INTAKE_STALE_HOURS,
//     per the heartbeat it uploads to Supabase Storage ops/heartbeat/email_intake.json.

const PACIFIC = 'America/Los_Angeles'
const INTAKE_STALE_HOURS = 2

function pacificMidnightUtc(now: Date): Date {
  // Pacific calendar date for `now`, then find the UTC instant of its 00:00.
  const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: PACIFIC }).format(now)
  const offset = new Intl.DateTimeFormat('en-US', { timeZone: PACIFIC, timeZoneName: 'longOffset' })
    .formatToParts(now).find(p => p.type === 'timeZoneName')!.value.replace('GMT', '') || '+00:00'
  return new Date(`${ymd}T00:00:00${offset}`)
}

async function sendResend(to: string[], subject: string, html: string) {
  const apiKey = process.env.RESEND_API_KEY
  if (!apiKey) throw new Error('RESEND_API_KEY not set')
  const resp = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: 'FCU Bid Agent <agent@bids.benlee.ventures>', to, subject, html }),
  })
  if (!resp.ok) throw new Error(`Resend ${resp.status}: ${await resp.text()}`)
}

export async function GET(req: Request) {
  const secret = process.env.CRON_SECRET
  if (secret && req.headers.get('authorization') !== `Bearer ${secret}`) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return NextResponse.json({ error: 'missing Supabase env' }, { status: 500 })

  const sb = createClient(url, key)
  const { data, error } = await sb
    .from('scan_run')
    .select('started_at')
    .eq('mode', 'full')
    .order('started_at', { ascending: false })
    .limit(1)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  const now = new Date()
  const fmt = (d: Date | null) => d
    ? d.toLocaleString('en-US', { timeZone: PACIFIC, dateStyle: 'medium', timeStyle: 'short' }) + ' PT'
    : 'never'

  const lastRun = data?.[0]?.started_at ? new Date(data[0].started_at) : null
  const scannerOk = !!lastRun && lastRun >= pacificMidnightUtc(now)

  // Email intake heartbeat. Missing file = never reported = stale.
  let intakeOk: Date | null = null
  const hb = await sb.storage.from('ops').download('heartbeat/email_intake.json')
  if (hb.data) {
    try {
      const j = JSON.parse(await hb.data.text())
      if (j.last_ok) intakeOk = new Date(j.last_ok)
    } catch { /* unreadable heartbeat counts as stale */ }
  }
  const intakeHealthy = !!intakeOk && now.getTime() - intakeOk.getTime() < INTAKE_STALE_HOURS * 3600_000

  if (scannerOk && intakeHealthy) return NextResponse.json({ ok: true, lastRun, intakeOk })

  const to = (process.env.ADMIN_EMAIL ?? '').split(',').map(s => s.trim()).filter(Boolean)
  if (!to.length) return NextResponse.json({ error: 'ADMIN_EMAIL not set', lastRun, intakeOk }, { status: 500 })

  const problems: string[] = []
  if (!scannerOk) problems.push(
    `<p><b>Bid scan:</b> no full scan has been logged today. Last scan started <b>${fmt(lastRun)}</b>.
     Check <code>~/fcu-cron/bid-scanner/logs/scraper.log</code>.</p>`)
  if (!intakeHealthy) problems.push(
    `<p><b>Email intake (info@ → Airtable):</b> no successful run since <b>${fmt(intakeOk)}</b>
     (it should run every 15 minutes). Check <code>~/fcu-cron/bid-scanner/logs/email_intake.log</code>
     and <code>emailintake.cron.log</code>. If the log shows a Gmail auth error, re-run
     <code>python email_intake.py --auth</code> signed in as info@.</p>`)
  const subject = !scannerOk && !intakeHealthy
    ? `⚠ FCU Mac jobs stopped — no scan today, email intake down since ${fmt(intakeOk)}`
    : !scannerOk
      ? `⚠ FCU scraper did not run today (last scan: ${fmt(lastRun)})`
      : `⚠ FCU email intake stopped (last success: ${fmt(intakeOk)})`

  await sendResend(
    to,
    subject,
    `${problems.join('\n')}
     <p>If both stopped, the Mac mini most likely rebooted and is waiting at the FileVault
     unlock screen — the scheduled jobs only run once someone logs in. Log in on the Mac;
     the jobs catch up automatically within 15 minutes.</p>`,
  )
  return NextResponse.json({ ok: false, alerted: to, lastRun, intakeOk })
}
