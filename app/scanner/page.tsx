import { createClient } from '@supabase/supabase-js'
import {
  ScanRun, SourceStat, PortalStat, BidParseRow,
  funnelSteps, dailySeries, windowTotals, sourceMatrix, latestPortalRun,
  docPull, STATUS_COLOR, STATUS_WORD, pct,
} from './lib'
import { Funnel, DocPullChart, VolumeChart, FilteredOutBars } from './Charts'
import Nav from '../Nav'

export const revalidate = 300
const MONO = 'IBM Plex Mono, monospace'

const DOC_PULL_WINDOW_DAYS = 90

async function getData(): Promise<{
  runs: ScanRun[]; sources: SourceStat[]; portals: PortalStat[]; parseRows: BidParseRow[]
}> {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return { runs: [], sources: [], portals: [], parseRows: [] }

  const sb = createClient(url, key)

  const { data: runData, error } = await sb
    .from('scan_run')
    .select('*')
    .order('started_at', { ascending: false })
    .limit(120)
  if (error) {
    console.error('scan_run fetch error:', error.message)
    return { runs: [], sources: [], portals: [], parseRows: [] }
  }

  const runs = (runData ?? []) as ScanRun[]
  const ids = runs.map(r => r.id)
  if (!ids.length) return { runs, sources: [], portals: [], parseRows: [] }

  const { data: sourceData } = await sb
    .from('scan_source_stat').select('*').in('scan_run_id', ids)

  const { data: portalData } = await sb
    .from('scan_portal_stat').select('*').in('scan_run_id', ids.slice(0, 15))

  // Document-pull cohort: relevant bids first seen in the last N days, with
  // their current parse_status. Tolerates the add_parse_status migration not
  // being applied (the select just errors and we render nothing).
  let parseRows: BidParseRow[] = []
  const since = new Date(Date.now() - DOC_PULL_WINDOW_DAYS * 86400000).toISOString()
  const { data: bidData, error: bidErr } = await sb
    .from('bids')
    .select('parse_status, parse_attempts, first_seen_at, source')
    .eq('is_relevant', true)
    .gte('first_seen_at', since)
    .order('first_seen_at', { ascending: false })
    .limit(5000)
  if (bidErr) console.error('bids parse_status fetch error:', bidErr.message)
  else parseRows = (bidData ?? []) as BidParseRow[]

  return {
    runs,
    sources: (sourceData ?? []) as SourceStat[],
    portals: (portalData ?? []) as PortalStat[],
    parseRows,
  }
}

function Card({ title, children, sub }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section style={{
      background: 'var(--charcoal-soft)', border: '1px solid var(--charcoal-mid)',
      borderRadius: 12, padding: '18px 20px', marginBottom: 20,
    }}>
      <h2 style={{ fontSize: 17, fontWeight: 600, marginBottom: sub ? 3 : 14 }}>{title}</h2>
      {sub && <p style={{ fontSize: 12, color: 'var(--ink-dim)', marginBottom: 14, lineHeight: 1.5 }}>{sub}</p>}
      {children}
    </section>
  )
}

function fmtPT(iso: string) {
  return new Date(iso).toLocaleString('en-US', {
    timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function StatusDot({ status }: { status: string }) {
  return <span style={{
    display: 'inline-block', width: 8, height: 8, borderRadius: 2,
    background: STATUS_COLOR[status] ?? 'var(--gray)',
  }} />
}

export default async function ScannerPage() {
  const { runs, sources, portals, parseRows } = await getData()

  const dp30 = docPull(parseRows, Date.now() - 30 * 86400000)
  const dp90 = docPull(parseRows)

  const realRuns = runs.filter(r => r.mode !== 'legacy')
  const latestFull: ScanRun | null =
    realRuns.find(r => r.mode === 'full') ?? (realRuns.length ? realRuns[0] : null)
  const steps = funnelSteps(latestFull)
  const series = dailySeries(runs, 30)
  const w7 = windowTotals(runs, 7)
  const w30 = windowTotals(runs, 30)
  const matrix = sourceMatrix(runs, sources, 14)
  const portalRun = latestPortalRun(portals)
  const portalCounts = portalRun.reduce<Record<string, number>>((a, p) => {
    a[p.status] = (a[p.status] ?? 0) + 1; return a
  }, {})

  const hasData = runs.length > 0

  return (
    <>
      <Nav active="scanner" />
      <main style={{ maxWidth: 1000, margin: '0 auto', padding: '28px 24px 64px' }}>
        {/* Header */}
        <header style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 28, letterSpacing: '-0.4px' }}>Bid Finder Status</h1>
          <p style={{ color: 'var(--ink-dim)', marginTop: 4, fontSize: 13 }}>
            Is the bid finder running, and is it missing anything?
          </p>
        </header>

      {!hasData ? (
        <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--ink-dim)', fontSize: 14 }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>📡</div>
          <div style={{ fontWeight: 500, marginBottom: 8 }}>No history yet</div>
          <div>This page fills in after the bid finder runs.</div>
        </div>
      ) : (
        <>
          {/* Window summary */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(165px, 1fr))', gap: 12, marginBottom: 24, maxWidth: 900 }}>
            {[
              { label: 'Checks this week', value: w7.runs, accent: 'var(--ink-faint)' },
              { label: 'Listings this week', value: w7.raw.toLocaleString(), accent: 'var(--gold)' },
              { label: 'Flooring this week', value: w7.relevant.toLocaleString(), accent: 'var(--green)' },
              { label: 'New this week', value: w7.new.toLocaleString(), accent: 'var(--gold-light)' },
              { label: 'Skipped this week', value: w7.filteredOut.toLocaleString(), accent: 'var(--orange)' },
            ].map(s => (
              <div key={s.label} className="stat-card" style={{ ['--_accent' as any]: s.accent }}>
                <div className="stat-card__value">{s.value}</div>
                <div className="stat-card__label">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Funnel */}
          <Card
            title="How the last full check went"
            sub={latestFull ? `Last full check: ${fmtPT(latestFull.started_at)} PT` : undefined}
          >
            <Funnel steps={steps} />
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--charcoal-mid)', display: 'flex', gap: 24, fontSize: 11, fontFamily: MONO, color: 'var(--gray)' }}>
              <span>This week: {w7.raw.toLocaleString()} listings → {w7.relevant} flooring → {w7.new} new</span>
              <span>Past 30 days: {w30.raw.toLocaleString()} listings → {w30.relevant} flooring → {w30.new} new</span>
            </div>
          </Card>

          {/* Document pull — parse_status disposition of the relevant-bid cohort */}
          {dp90.total > 0 && (
            <Card
              title="Bid document downloads"
              sub={`Of the ${dp30.total} flooring jobs found in the last 30 days, how many did we get the full bid packet for? (updates over the ~3 days after a bid is found)`}
            >
              <DocPullChart d={dp30} />
              <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--charcoal-mid)', display: 'flex', gap: 24, fontSize: 11, fontFamily: MONO, color: 'var(--gray)' }}>
                <span>Last 30 days: {dp30.parsed} downloaded · {dp30.noDocs + dp30.unparseable} not available · {dp30.pending} still checking</span>
                <span>Past 90 days: {dp90.parsed} of {dp90.total} downloaded ({pct(dp90.parsed, dp90.total)})</span>
              </div>
            </Card>
          )}

          {/* Volume over time */}
          <Card title="Bids found per day" sub="Last 30 days">
            <VolumeChart data={series} />
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, fontFamily: MONO, color: 'var(--gray)', marginBottom: 6 }}>
                Bids skipped per day (outside our area, duplicates, or other trades)
              </div>
              <FilteredOutBars data={series} />
            </div>
          </Card>

          {/* Source visibility matrix */}
          <Card title="Each website, day by day" sub="Last 14 days · number = listings seen that day">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 11, fontFamily: MONO, minWidth: 640 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--gray)', fontWeight: 500 }}>Website</th>
                    {matrix.columns.map(c => (
                      <th key={c} style={{ padding: '4px 3px', color: 'var(--gray)', fontWeight: 500, writingMode: 'vertical-rl', fontSize: 9 }}>
                        {c.slice(5)}
                      </th>
                    ))}
                    <th style={{ padding: '4px 8px', color: 'var(--gray)', fontWeight: 500 }} title="Days in a row with a problem">⚠</th>
                  </tr>
                </thead>
                <tbody>
                  {matrix.rows.map(row => (
                    <tr key={row.source}>
                      <td style={{ padding: '3px 8px', whiteSpace: 'nowrap', color: row.failStreak >= 2 ? 'var(--red)' : row.dryStreak >= 7 ? 'var(--gray)' : 'var(--white)' }}>
                        {row.source}
                      </td>
                      {row.cells.map((cell, i) => (
                        <td key={i} style={{ padding: 2, textAlign: 'center' }}>
                          {cell ? (
                            <div title={`${STATUS_WORD[cell.status] ?? cell.status} · ${cell.raw} listings`} style={{
                              width: 22, height: 18, borderRadius: 3, margin: '0 auto',
                              background: STATUS_COLOR[cell.status] ?? 'var(--gray)',
                              color: '#fff', fontSize: 9, lineHeight: '18px',
                              opacity: cell.status === 'empty' ? 0.35 : 0.9,
                            }}>{cell.raw || ''}</div>
                          ) : (
                            <div style={{ width: 22, height: 18, margin: '0 auto', background: 'var(--charcoal-mid)', borderRadius: 3, opacity: 0.4 }} />
                          )}
                        </td>
                      ))}
                      <td style={{ padding: '3px 8px', textAlign: 'center', fontWeight: 700, color: row.failStreak >= 2 ? 'var(--red)' : 'var(--gray)' }}>
                        {row.failStreak >= 2 ? `${row.failStreak}d` : row.dryStreak >= 7 ? `${row.dryStreak}d quiet` : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Legend items={['ok', 'partial', 'blocked', 'error', 'empty']} />
          </Card>

          {/* PlanetBids portal grid */}
          {portalRun.length > 0 && (
            <Card
              title="City & agency portals — last check"
              sub={`${portalRun.length} portals · ` + ['ok', 'empty', 'blocked', 'error', 'pending']
                .filter(s => portalCounts[s]).map(s => `${portalCounts[s]} ${STATUS_WORD[s] ?? s}`).join(' · ')}
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6 }}>
                {portalRun.map(p => (
                  <div key={p.portal_id} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px',
                    border: '1px solid var(--charcoal-mid)', borderRadius: 6, fontSize: 11,
                  }}>
                    <StatusDot status={p.status} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${p.agency} (${p.county ?? '?'}) — ${STATUS_WORD[p.status] ?? p.status}`}>
                      {p.agency}
                    </span>
                    {p.bid_count > 0 && <span style={{ marginLeft: 'auto', fontFamily: MONO, color: 'var(--gold-light)' }}>{p.bid_count}</span>}
                  </div>
                ))}
              </div>
              <Legend items={['ok', 'empty', 'blocked', 'error', 'pending']} />
            </Card>
          )}

          {/* Run log */}
          <Card title="Recent checks">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 560 }}>
                <thead>
                  <tr style={{ color: 'var(--gray)', fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>Time (PT)</th>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>Type</th>
                    <th style={{ padding: '6px 8px' }}>Took</th>
                    <th style={{ padding: '6px 8px' }}>Found</th>
                    <th style={{ padding: '6px 8px' }}>After dupes</th>
                    <th style={{ padding: '6px 8px' }}>Flooring</th>
                    <th style={{ padding: '6px 8px' }}>New</th>
                    <th style={{ padding: '6px 8px' }}>Email sent</th>
                  </tr>
                </thead>
                <tbody style={{ fontFamily: MONO }}>
                  {runs.slice(0, 25).map(r => (
                    <tr key={r.id} style={{ borderTop: '1px solid var(--charcoal-mid)', textAlign: 'right' }}>
                      <td style={{ textAlign: 'left', padding: '6px 8px' }}>{fmtPT(r.started_at)}</td>
                      <td style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--gray)' }}>
                        {r.error_summary
                          ? <span style={{ color: 'var(--red)' }} title={r.error_summary}>{runTypeLabel(r.mode)} ⚠</span>
                          : runTypeLabel(r.mode)}
                      </td>
                      <td style={{ padding: '6px 8px', color: 'var(--gray)' }}>{r.duration_secs ?? '—'}s</td>
                      <td style={{ padding: '6px 8px' }}>{r.raw_found}</td>
                      <td style={{ padding: '6px 8px' }}>{r.after_dedup}</td>
                      <td style={{ padding: '6px 8px', color: 'var(--green)' }}>{r.relevant}</td>
                      <td style={{ padding: '6px 8px', color: 'var(--gold-light)', fontWeight: 700 }}>{r.new_bids}</td>
                      <td style={{ padding: '6px 8px' }}>{r.digest_sent ? '✓' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
      </main>
    </>
  )
}

function runTypeLabel(mode: string): string {
  return { full: 'full', quick: 'quick', legacy: 'older', partial: 'partial' }[mode] ?? mode
}

function Legend({ items }: { items: string[] }) {
  return (
    <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 12 }}>
      {items.map(s => (
        <span key={s} style={{ fontSize: 10.5, fontFamily: MONO, color: 'var(--gray)', display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: STATUS_COLOR[s] ?? 'var(--gray)', display: 'inline-block' }} />
          {STATUS_WORD[s] ?? s}
        </span>
      ))}
    </div>
  )
}
