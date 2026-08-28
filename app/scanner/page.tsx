import { createClient } from '@supabase/supabase-js'
import {
  ScanRun, SourceStat, PortalStat,
  funnelSteps, dailySeries, windowTotals, sourceMatrix, latestPortalRun,
  STATUS_COLOR, pct,
} from './lib'
import { Funnel, VolumeChart, FilteredOutBars } from './Charts'

export const revalidate = 300
const MONO = 'IBM Plex Mono, monospace'

async function getData(): Promise<{ runs: ScanRun[]; sources: SourceStat[]; portals: PortalStat[] }> {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return { runs: [], sources: [], portals: [] }

  const sb = createClient(url, key)

  const { data: runData, error } = await sb
    .from('scan_run')
    .select('*')
    .order('started_at', { ascending: false })
    .limit(120)
  if (error) {
    console.error('scan_run fetch error:', error.message)
    return { runs: [], sources: [], portals: [] }
  }

  const runs = (runData ?? []) as ScanRun[]
  const ids = runs.map(r => r.id)
  if (!ids.length) return { runs, sources: [], portals: [] }

  const { data: sourceData } = await sb
    .from('scan_source_stat').select('*').in('scan_run_id', ids)

  const { data: portalData } = await sb
    .from('scan_portal_stat').select('*').in('scan_run_id', ids.slice(0, 15))

  return {
    runs,
    sources: (sourceData ?? []) as SourceStat[],
    portals: (portalData ?? []) as PortalStat[],
  }
}

function Card({ title, children, sub }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section style={{
      background: 'var(--charcoal-soft)', border: '1px solid var(--charcoal-mid)',
      borderRadius: 12, padding: '18px 20px', marginBottom: 20,
    }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, marginBottom: sub ? 2 : 14 }}>{title}</h2>
      {sub && <p style={{ fontSize: 11, color: 'var(--gray)', fontFamily: MONO, marginBottom: 14 }}>{sub}</p>}
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
  const { runs, sources, portals } = await getData()

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
    <main style={{ maxWidth: 1000, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 28 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8, background: 'var(--gold)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: MONO, fontWeight: 500, fontSize: 14, color: 'var(--charcoal)',
            }}>◔</div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.3px' }}>Scanner Health</h1>
          </div>
          <p style={{ color: 'var(--gray)', marginTop: 4, fontFamily: MONO, fontSize: 11 }}>
            Funnel throughput · volume trends · per-source visibility
          </p>
        </div>
        <a href="/" style={{ color: 'var(--gold-light)', fontFamily: MONO, fontSize: 11 }}>← Bid Dashboard</a>
      </div>

      {!hasData ? (
        <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--gray)', fontFamily: MONO, fontSize: 13 }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>📡</div>
          <div style={{ fontWeight: 500, marginBottom: 8 }}>No scan telemetry yet</div>
          <div>Apply <code style={{ color: 'var(--gold)' }}>supabase/add_scan_analytics.sql</code>, then run <code style={{ color: 'var(--gold)' }}>python main.py</code>.</div>
        </div>
      ) : (
        <>
          {/* Window summary */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 12, marginBottom: 20 }}>
            {[
              { label: 'Runs (7d)', value: w7.runs, accent: 'var(--gray)' },
              { label: 'Raw scraped (7d)', value: w7.raw.toLocaleString(), accent: 'var(--gold)' },
              { label: 'Relevant (7d)', value: w7.relevant.toLocaleString(), accent: 'var(--green)' },
              { label: 'New (7d)', value: w7.new.toLocaleString(), accent: 'var(--gold-light)' },
              { label: 'Filtered out (7d)', value: w7.filteredOut.toLocaleString(), accent: 'var(--orange)' },
              { label: 'Raw→New (7d)', value: pct(w7.new, w7.raw), accent: 'var(--gray)' },
            ].map(s => (
              <div key={s.label} style={{
                background: 'var(--charcoal-soft)', border: '1px solid var(--charcoal-mid)',
                borderRadius: 12, padding: '14px 16px',
              }}>
                <div style={{ fontSize: 22, fontWeight: 700, color: s.accent, fontFamily: MONO }}>{s.value}</div>
                <div style={{ fontSize: 11, color: 'var(--gray)', marginTop: 2 }}>{s.label}</div>
              </div>
            ))}
          </div>

          {/* Funnel */}
          <Card
            title="Funnel — latest full run"
            sub={latestFull ? `${fmtPT(latestFull.started_at)} PT · ${latestFull.mode} · ${latestFull.duration_secs ?? '?'}s` : undefined}
          >
            <Funnel steps={steps} />
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--charcoal-mid)', display: 'flex', gap: 24, fontSize: 11, fontFamily: MONO, color: 'var(--gray)' }}>
              <span>7-day: {w7.raw.toLocaleString()} raw → {w7.relevant} relevant → {w7.new} new</span>
              <span>30-day: {w30.raw.toLocaleString()} raw → {w30.relevant} relevant → {w30.new} new</span>
            </div>
          </Card>

          {/* Volume over time */}
          <Card title="Volume over time" sub="Per day, all run types · last 30 days">
            <VolumeChart data={series} />
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, fontFamily: MONO, color: 'var(--gray)', marginBottom: 6 }}>
                Bids filtered out per day (out-of-area + duplicates + not-relevant)
              </div>
              <FilteredOutBars data={series} />
            </div>
          </Card>

          {/* Source visibility matrix */}
          <Card title="Source visibility" sub="Status per source per day · last 14 days · number = raw rows">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 11, fontFamily: MONO, minWidth: 640 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--gray)', fontWeight: 500 }}>Source</th>
                    {matrix.columns.map(c => (
                      <th key={c} style={{ padding: '4px 3px', color: 'var(--gray)', fontWeight: 500, writingMode: 'vertical-rl', fontSize: 9 }}>
                        {c.slice(5)}
                      </th>
                    ))}
                    <th style={{ padding: '4px 8px', color: 'var(--gray)', fontWeight: 500 }}>!</th>
                  </tr>
                </thead>
                <tbody>
                  {matrix.rows.map(row => (
                    <tr key={row.source}>
                      <td style={{ padding: '3px 8px', whiteSpace: 'nowrap', color: row.brokenStreak >= 2 ? 'var(--red)' : 'var(--white)' }}>
                        {row.source}
                      </td>
                      {row.cells.map((cell, i) => (
                        <td key={i} style={{ padding: 2, textAlign: 'center' }}>
                          {cell ? (
                            <div title={`${cell.status} · ${cell.raw} raw`} style={{
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
                      <td style={{ padding: '3px 8px', textAlign: 'center', color: 'var(--red)', fontWeight: 700 }}>
                        {row.brokenStreak >= 2 ? `${row.brokenStreak}d` : ''}
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
              title="PlanetBids portals — latest sweep"
              sub={`${portalRun.length} portals · ` + ['ok', 'empty', 'blocked', 'error', 'pending']
                .filter(s => portalCounts[s]).map(s => `${portalCounts[s]} ${s}`).join(' · ')}
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6 }}>
                {portalRun.map(p => (
                  <div key={p.portal_id} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px',
                    border: '1px solid var(--charcoal-mid)', borderRadius: 6, fontSize: 11,
                  }}>
                    <StatusDot status={p.status} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${p.agency} (${p.county ?? '?'}) — ${p.status}`}>
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
          <Card title="Recent runs">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 560 }}>
                <thead>
                  <tr style={{ color: 'var(--gray)', fontFamily: MONO, fontSize: 11, textAlign: 'right' }}>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>Started (PT)</th>
                    <th style={{ textAlign: 'left', padding: '6px 8px' }}>Mode</th>
                    <th style={{ padding: '6px 8px' }}>Dur</th>
                    <th style={{ padding: '6px 8px' }}>Raw</th>
                    <th style={{ padding: '6px 8px' }}>Dedup</th>
                    <th style={{ padding: '6px 8px' }}>Rel</th>
                    <th style={{ padding: '6px 8px' }}>New</th>
                    <th style={{ padding: '6px 8px' }}>Digest</th>
                  </tr>
                </thead>
                <tbody style={{ fontFamily: MONO }}>
                  {realRuns.slice(0, 25).map(r => (
                    <tr key={r.id} style={{ borderTop: '1px solid var(--charcoal-mid)', textAlign: 'right' }}>
                      <td style={{ textAlign: 'left', padding: '6px 8px' }}>{fmtPT(r.started_at)}</td>
                      <td style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--gray)' }}>
                        {r.error_summary ? <span style={{ color: 'var(--red)' }} title={r.error_summary}>{r.mode} ⚠</span> : r.mode}
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
  )
}

function Legend({ items }: { items: string[] }) {
  return (
    <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 12 }}>
      {items.map(s => (
        <span key={s} style={{ fontSize: 10.5, fontFamily: MONO, color: 'var(--gray)', display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: STATUS_COLOR[s] ?? 'var(--gray)', display: 'inline-block' }} />
          {s}
        </span>
      ))}
    </div>
  )
}
