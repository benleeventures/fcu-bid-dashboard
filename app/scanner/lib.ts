// Scanner dashboard — types + pure aggregation helpers.
// No React here; everything is unit-testable.

export type ScanRun = {
  id: string
  mode: string
  started_at: string
  finished_at: string | null
  duration_secs: number | null
  raw_found: number
  geo_in: number
  geo_unknown: number
  geo_out: number
  after_dedup: number
  dedup_removed: number
  relevant: number
  new_bids: number
  updated_bids: number
  digest_sent: boolean
  error_summary: string | null
}

export type SourceStat = {
  id: string
  scan_run_id: string
  source: string
  raw_count: number
  kept_count: number
  relevant_count: number
  new_count: number
  status: SourceStatus
  portals_total: number | null
  portals_ok: number | null
  portals_blocked: number | null
  note: string | null
  duration_secs: number | null
}

export type PortalStat = {
  id: string
  scan_run_id: string
  portal_id: string
  agency: string | null
  county: string | null
  status: PortalStatus
  bid_count: number
  checked_at: string | null
}

export type SourceStatus = 'ok' | 'empty' | 'blocked' | 'partial' | 'error'
export type PortalStatus = 'ok' | 'empty' | 'blocked' | 'error' | 'pending'

export const STATUS_COLOR: Record<string, string> = {
  ok: 'var(--green)',
  empty: 'var(--gray)',
  partial: 'var(--orange)',
  blocked: 'var(--red)',
  error: 'var(--red)',
  pending: 'var(--gold)',
}

// ── Funnel ────────────────────────────────────────────────────────────────

export type FunnelStep = { label: string; value: number; note?: string }

export function funnelSteps(r: ScanRun | null): FunnelStep[] {
  if (!r) return []
  const inArea = r.geo_in + r.geo_unknown
  return [
    { label: 'Raw scraped', value: r.raw_found },
    { label: 'In-area', value: inArea, note: `${r.geo_out} out-of-area dropped` },
    { label: 'After dedup', value: r.after_dedup, note: `${r.dedup_removed} duplicates removed` },
    { label: 'Flooring-relevant', value: r.relevant },
    { label: 'New', value: r.new_bids, note: `${r.updated_bids} already known` },
  ]
}

export function pct(a: number, b: number): string {
  if (!b) return '—'
  return `${Math.round((a / b) * 100)}%`
}

// ── Document pull (parse_status disposition) ──────────────────────────────
// The discovery funnel above only scrapes listing pages. Whether we can
// actually download + parse a bid's documents is decided later, async, by
// parser.py (com.fcu.parser), and recorded per-bid in bids.parse_status.
// This cohort view answers: of the relevant bids we found, how many could
// we fully pull?

export type BidParseRow = {
  parse_status: string | null
  parse_attempts: number | null
  first_seen_at: string
  source: string | null
}

export type DocPullKey = 'parsed' | 'pending' | 'noDocs' | 'unparseable' | 'skipped'

export type DocPull = Record<DocPullKey, number> & { total: number }

export function docPull(bids: BidParseRow[], sinceMs?: number): DocPull {
  const d: DocPull = { total: 0, parsed: 0, pending: 0, noDocs: 0, unparseable: 0, skipped: 0 }
  for (const b of bids) {
    if (sinceMs && new Date(b.first_seen_at).getTime() < sinceMs) continue
    d.total++
    switch (b.parse_status) {
      case 'parsed':      d.parsed++; break
      case 'no_docs':     d.noDocs++; break
      case 'unparseable': d.unparseable++; break
      case 'skipped':     d.skipped++; break
      default:            d.pending++      // null / 'pending'
    }
  }
  return d
}

// ── Time series ───────────────────────────────────────────────────────────

export type DayPoint = {
  day: string           // YYYY-MM-DD in PT
  raw: number
  relevant: number
  new: number
  filteredOut: number   // geo_out + dedup_removed + (after_dedup - relevant)
  runs: number
}

function ptDay(iso: string): string {
  // en-CA gives YYYY-MM-DD
  return new Date(iso).toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' })
}

export function dailySeries(runs: ScanRun[], days = 30): DayPoint[] {
  // Legacy (scan_log backfill) rows are included: raw_found is set to the
  // post-dedup total and the geo/dedup split is 0, so `raw` reads a touch low
  // and `filteredOut` a touch low for historical days — relevant / new are exact.
  const byDay = new Map<string, DayPoint>()
  for (const r of runs) {
    const day = ptDay(r.started_at)
    const p = byDay.get(day) ?? { day, raw: 0, relevant: 0, new: 0, filteredOut: 0, runs: 0 }
    p.raw += r.raw_found
    p.relevant += r.relevant
    p.new += r.new_bids
    p.filteredOut += r.geo_out + r.dedup_removed + Math.max(0, r.after_dedup - r.relevant)
    p.runs += 1
    byDay.set(day, p)
  }
  // Fill the last `days` calendar days so the axis is continuous.
  const out: DayPoint[] = []
  const today = new Date()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const key = d.toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' })
    out.push(byDay.get(key) ?? { day: key, raw: 0, relevant: 0, new: 0, filteredOut: 0, runs: 0 })
  }
  return out
}

export function windowTotals(runs: ScanRun[], days: number) {
  const cutoff = Date.now() - days * 86400000
  const inWin = runs.filter(r => new Date(r.started_at).getTime() >= cutoff)
  const sum = (f: (r: ScanRun) => number) => inWin.reduce((a, r) => a + f(r), 0)
  return {
    runs: inWin.length,
    raw: sum(r => r.raw_found),
    relevant: sum(r => r.relevant),
    new: sum(r => r.new_bids),
    filteredOut: sum(r => r.geo_out + r.dedup_removed + Math.max(0, r.after_dedup - r.relevant)),
  }
}

// ── Source visibility matrix (source × day) ───────────────────────────────

export type MatrixCell = { status: SourceStatus; raw: number } | null

export type SourceRow = {
  source: string
  cells: MatrixCell[]           // one per day column, oldest → newest
  lastRaw: number
  brokenStreak: number          // consecutive most-recent days with 0 raw / blocked / error
}

const STATUS_RANK: Record<SourceStatus, number> = {
  error: 5, blocked: 4, partial: 3, empty: 2, ok: 1,
}

export function sourceMatrix(
  runs: ScanRun[],
  stats: SourceStat[],
  days = 14,
): { columns: string[]; rows: SourceRow[] } {
  const runDay = new Map<string, string>(
    runs.map(r => [r.id, ptDay(r.started_at)] as [string, string]),
  )

  // Day columns
  const columns: string[] = []
  const today = new Date()
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    columns.push(d.toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' }))
  }
  const colIdx = new Map<string, number>(columns.map((c, i) => [c, i] as [string, number]))

  // source -> day -> aggregated cell (worst status that day, summed raw)
  const grid = new Map<string, Map<number, { status: SourceStatus; raw: number }>>()
  for (const s of stats) {
    const day = runDay.get(s.scan_run_id)
    if (day === undefined) continue
    const ci = colIdx.get(day)
    if (ci === undefined) continue
    if (!grid.has(s.source)) grid.set(s.source, new Map())
    const row = grid.get(s.source)!
    const cur = row.get(ci)
    if (!cur) {
      row.set(ci, { status: s.status, raw: s.raw_count })
    } else {
      cur.raw += s.raw_count
      if (STATUS_RANK[s.status] > STATUS_RANK[cur.status]) cur.status = s.status
    }
  }

  const rows: SourceRow[] = Array.from(grid.entries()).map(([source, row]: [string, Map<number, { status: SourceStatus; raw: number }>]) => {
    const cells: MatrixCell[] = columns.map((_, i) => row.get(i) ?? null)
    let brokenStreak = 0
    for (let i = cells.length - 1; i >= 0; i--) {
      const c = cells[i]
      if (c === null) continue                 // not scanned that day — skip, don't break
      if (c.raw === 0 || c.status === 'blocked' || c.status === 'error') brokenStreak++
      else break
    }
    const lastCell = cells.slice().reverse().find(c => c !== null) as MatrixCell
    return { source, cells, lastRaw: lastCell?.raw ?? 0, brokenStreak }
  })

  rows.sort((a, b) => b.brokenStreak - a.brokenStreak || a.source.localeCompare(b.source))
  return { columns, rows }
}

// ── PlanetBids portal grid (latest run that has portal rows) ──────────────

export function latestPortalRun(portals: PortalStat[]): PortalStat[] {
  if (!portals.length) return []
  // pick the scan_run_id whose rows are newest by checked_at
  const byRun = new Map<string, PortalStat[]>()
  for (const p of portals) {
    if (!byRun.has(p.scan_run_id)) byRun.set(p.scan_run_id, [])
    byRun.get(p.scan_run_id)!.push(p)
  }
  let best: PortalStat[] = []
  let bestTs = -1
  Array.from(byRun.values()).forEach(rows => {
    const ts = Math.max(...rows.map(r => (r.checked_at ? new Date(r.checked_at).getTime() : 0)))
    if (ts > bestTs) { bestTs = ts; best = rows }
  })
  return best.sort(
    (a, b) => (a.county ?? '').localeCompare(b.county ?? '') ||
              (a.agency ?? '').localeCompare(b.agency ?? ''),
  )
}
