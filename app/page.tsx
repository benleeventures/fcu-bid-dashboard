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
  // PostgREST hard-caps responses at 1000 rows. The bids table has ~2000 rows
  // and the non-expired slice alone (~1000) can blow past that cap, silently
  // truncating the view. Bound the query so it can never approach 1000:
  //   - always include flooring-relevant bids (currently ~115)
  //   - plus any non-relevant bid first seen in the last 30 days (recent scans;
  //     the expirer archives non-relevant bids older than that)
  //   - never include expired (the expirer archives past-due bids daily;
  //     BidTable's archive toggle surfaces them on demand)
  const recentCutoff = new Date(Date.now() - 30 * 86400000).toISOString()
  const { data, error } = await sb
    .from('bids')
    .select('*, spec:bid_specs(flooring_types,total_sqft,rooms,prevailing_wage,bid_bond,bid_bond_pct,walk_required,walk_date,walk_date_raw,summary,flooring_is_primary,award_method,project_city,bid_type)')
    .neq('bid_status', 'expired')
    .or(`is_relevant.eq.true,first_seen_at.gte.${recentCutoff}`)
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

  const sources = Array.from(new Set(bids.map(b => b.source).filter(Boolean))) as string[]

  const lastScanLabel = lastScan
    ? new Date(lastScan.scanned_at).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  const stats: { label: string; value: string | number; accent: string }[] = [
    { label: 'Bids found',       value: bids.length,       accent: 'var(--gold)' },
    { label: 'Flooring jobs',    value: relevant.length,   accent: 'var(--green)' },
    { label: 'Due this week',    value: dueThisWeek.length, accent: dueThisWeek.length > 0 ? 'var(--orange)' : 'var(--ink-faint)' },
    { label: 'Websites checked', value: sources.length,    accent: 'var(--ink-faint)' },
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
              New government and institutional projects out for bid
            </p>
          </div>
          {lastScanLabel && (
            <div style={{ fontSize: 12, color: 'var(--ink-dim)', textAlign: 'right', lineHeight: 1.6 }}>
              Last checked {lastScanLabel}<br />
              {lastScan!.new_bids} new {lastScan!.new_bids === 1 ? 'bid' : 'bids'} since then
            </div>
          )}
        </header>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 28, maxWidth: 720 }}>
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
