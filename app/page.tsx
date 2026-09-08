import { createClient } from '@supabase/supabase-js'
import BidTable from './BidTable'
import Nav from './Nav'

export const revalidate = 300 // re-fetch every 5 min

export type BidSpec = {
  flooring_types: string[] | null
  total_sqft: number | null
  rooms: string | null
  prevailing_wage: boolean | null
  bid_bond: boolean | null
  bid_bond_pct: number | null
  walk_required: boolean | null
  walk_date: string | null
  walk_date_raw: string | null
  summary: string | null
  flooring_is_primary: boolean | null
  award_method: string | null
  project_city: string | null
  bid_type: string | null
}

export type BidStatus = 'active' | 'submitted' | 'won' | 'lost' | 'no_bid'

export type Bid = {
  id: string
  bid_id: string
  title: string
  agency: string | null
  state: string | null
  source: string | null
  published_date: string | null
  due_date: string | null
  due_date_raw: string | null
  url: string | null
  is_relevant: boolean
  is_favorite: boolean
  search_keyword: string | null
  first_seen_at: string
  last_seen_at: string
  bid_status: BidStatus | null
  submitted_amount: number | null
  award_amount: number | null
  county: string | null
  geo_status: string | null
  spec?: BidSpec | null
}

async function getBids(): Promise<Bid[]> {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return []

  const sb = createClient(url, key)
  // The table is dominated by ~900 past-due "expired" rows. The old query
  // ordered by due_date asc + limit 500, so those expired rows filled the
  // entire window and starved the view of every current bid. Exclude expired
  // at the query level (BidTable's archive toggle covered them anyway) and
  // order by recency. PostgREST hard-caps responses at 1000 rows.
  const { data, error } = await sb
    .from('bids')
    .select('*, spec:bid_specs(flooring_types,total_sqft,rooms,prevailing_wage,bid_bond,bid_bond_pct,walk_required,walk_date,walk_date_raw,summary,flooring_is_primary,award_method,project_city,bid_type)')
    .neq('bid_status', 'expired')
    .order('first_seen_at', { ascending: false })
    .limit(1000)

  if (error) {
    console.error('Supabase error:', error.message)
    return []
  }

  // Supabase returns spec as array for one-to-one joins — flatten it
  return ((data ?? []) as any[]).map(b => ({
    ...b,
    spec: Array.isArray(b.spec) ? (b.spec[0] ?? null) : b.spec,
  })) as Bid[]
}

async function getLastScan() {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return null

  const sb = createClient(url, key)
  const { data } = await sb
    .from('scan_log')
    .select('scanned_at, total_found, relevant_found, new_bids, duration_secs')
    .order('scanned_at', { ascending: false })
    .limit(1)
    .single()
  return data
}

export default async function Home() {
  const [bids, lastScan] = await Promise.all([getBids(), getLastScan()])

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const in7 = new Date(today); in7.setDate(today.getDate() + 7)
  const in3 = new Date(today); in3.setDate(today.getDate() + 3)

  const relevant    = bids.filter(b => b.is_relevant)
  const dueThisWeek = bids.filter(b => {
    if (!b.due_date) return false
    const d = new Date(b.due_date)
    return d >= today && d <= in7
  })
  const submitted = bids.filter(b => b.bid_status === 'submitted')
  const won       = bids.filter(b => b.bid_status === 'won')
  const lost      = bids.filter(b => b.bid_status === 'lost')

  const sources = Array.from(new Set(bids.map(b => b.source).filter(Boolean))) as string[]

  const lastScanLabel = lastScan
    ? new Date(lastScan.scanned_at).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  const stats: { label: string; value: string | number; accent: string }[] = [
    { label: 'Total Bids',       value: bids.length,      accent: 'var(--gold)' },
    { label: 'Flooring Relevant', value: relevant.length,  accent: 'var(--green)' },
    { label: 'Due This Week',    value: dueThisWeek.length, accent: dueThisWeek.length > 0 ? 'var(--orange)' : 'var(--ink-faint)' },
    { label: 'Submitted',        value: submitted.length,  accent: 'var(--gold)' },
    { label: 'Won',              value: won.length,        accent: 'var(--green)' },
    { label: 'Lost',             value: lost.length,       accent: lost.length > 0 ? 'var(--red)' : 'var(--ink-faint)' },
    { label: 'Win Rate',         value: (won.length + lost.length) > 0 ? `${Math.round(won.length / (won.length + lost.length) * 100)}%` : '—', accent: 'var(--gold)' },
    { label: 'Sources',          value: sources.length,    accent: 'var(--ink-faint)' },
  ]

  return (
    <>
      <Nav active="bids" />

      <main style={{ maxWidth: 1240, margin: '0 auto', padding: '28px 24px 64px' }}>
        {/* Page heading */}
        <header style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 30, letterSpacing: '-0.5px' }}>Government Bid Tracker</h1>
            <p style={{ color: 'var(--ink-dim)', marginTop: 4, fontSize: 13 }}>
              Floor Covering Unlimited — public-works & institutional opportunities
            </p>
          </div>
          {lastScanLabel && (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-dim)', textAlign: 'right', lineHeight: 1.5 }}>
              Last scan {lastScanLabel} PT<br />
              {lastScan!.duration_secs}s · {lastScan!.new_bids} new bids
            </div>
          )}
        </header>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12, marginBottom: 28 }}>
          {stats.map(stat => (
            <div key={stat.label} className="stat-card" style={{ ['--_accent' as any]: stat.accent }}>
              <div className="stat-card__value">{stat.value}</div>
              <div className="stat-card__label">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Table (client component for filtering) */}
        <BidTable bids={bids} sources={sources} today={today.toISOString()} in3={in3.toISOString()} in7={in7.toISOString()} />
      </main>
    </>
  )
}
