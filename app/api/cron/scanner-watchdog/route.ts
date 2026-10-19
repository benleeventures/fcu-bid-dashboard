import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// Off-machine dead-man's switch for the scheduled scraper.
//
// The scraper runs on the Mac mini via launchd. When that machine reboots
// unattended (power cut, macOS update), FileVault holds it at the unlock
// screen and every job silently stops — nothing on the Mac can report that.
// Vercel Cron hits this route each weekday after the 06:00 PT scan should
// have finished; if no full scan has started yet today (Pacific), email admin.

const PACIFIC = 'America/Los_Angeles'

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

  const { data, error } = await createClient(url, key)
    .from('scan_run')
    .select('started_at')
    .eq('mode', 'full')
    .order('started_at', { ascending: false })
    .limit(1)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })

  const now = new Date()
  const lastRun = data?.[0]?.started_at ? new Date(data[0].started_at) : null
  const healthy = !!lastRun && lastRun >= pacificMidnightUtc(now)
  if (healthy) return NextResponse.json({ ok: true, lastRun })

  const to = (process.env.ADMIN_EMAIL ?? '').split(',').map(s => s.trim()).filter(Boolean)
  if (!to.length) return NextResponse.json({ error: 'ADMIN_EMAIL not set', lastRun }, { status: 500 })

  const last = lastRun
    ? lastRun.toLocaleString('en-US', { timeZone: PACIFIC, dateStyle: 'medium', timeStyle: 'short' }) + ' PT'
    : 'never'
  await sendResend(
    to,
    `⚠ FCU scraper did not run today (last scan: ${last})`,
    `<p>No full bid scan has been logged today. Last scan started <b>${last}</b>.</p>
     <p>Most likely the Mac mini rebooted and is waiting at the FileVault unlock screen —
     the scheduled jobs only run once someone logs in. Log in on the Mac; the scan
     catches up automatically within 5 minutes.</p>
     <p>If the Mac is logged in, check <code>~/fcu-cron/bid-scanner/logs/scraper.log</code>.</p>`,
  )
  return NextResponse.json({ ok: false, alerted: to, lastRun })
}
