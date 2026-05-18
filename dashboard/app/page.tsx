import { createClient } from '@supabase/supabase-js'
import BidTable from './BidTable'

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
  search_keyword: string | null
  first_seen_at: string
  last_seen_at: string
  bid_status: BidStatus | null
  submitted_amount: number | null
  award_amount: number | null
  spec?: BidSpec | null
}

async function getBids(): Promise<Bid[]> {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return []

  const sb = createClient(url, key)
  const { data, error } = await sb
    .from('bids')
    .select('*, spec:bid_specs(flooring_types,total_sqft,rooms,prevailing_wage,bid_bond,bid_bond_pct,walk_required,walk_date,walk_date_raw,summary)')
    .order('due_date', { ascending: true, nullsFirst: false })
    .limit(500)

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

  return (
    <main style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 32 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8,
              background: 'var(--gold)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: 'IBM Plex Mono', fontWeight: 500, fontSize: 14, color: 'var(--charcoal)'
            }}>FCU</div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.3px' }}>Bid Dashboard</h1>
          </div>
          <p style={{ color: 'var(--gray)', marginTop: 4, fontFamily: 'IBM Plex Mono', fontSize: 11 }}>
            Floor Covering Unlimited — Government Contracts
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 20, flexDirection: 'column' }}>
          <a href="/intel" style={{
            color: 'var(--gold-light)', textDecoration: 'none',
            fontSize: 13, fontFamily: 'IBM Plex Mono',
          }}>Intel →</a>
          {lastScan && (
            <div style={{ textAlign: 'right', color: 'var(--gray)', fontSize: 11, fontFamily: 'IBM Plex Mono' }}>
              Last scan: {new Date(lastScan.scanned_at).toLocaleString('en-US', { timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} PT
              <br />{lastScan.duration_secs}s · {lastScan.new_bids} new bids
            </div>
          )}
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28, gridAutoRows: 'auto' }}>
        {[
          { label: 'Total Bids', value: bids.length, accent: 'var(--gold)' },
          { label: 'Flooring Relevant', value: relevant.length, accent: 'var(--green)' },
          { label: 'Due This Week', value: dueThisWeek.length, accent: dueThisWeek.length > 0 ? 'var(--orange)' : 'var(--gray)' },
          { label: 'Submitted', value: submitted.length, accent: 'var(--gold)' },
          { label: 'Won', value: won.length, accent: 'var(--green)' },
          { label: 'Lost', value: lost.length, accent: lost.length > 0 ? 'var(--red)' : 'var(--gray)' },
          { label: 'Win Rate', value: (won.length + lost.length) > 0 ? `${Math.round(won.length / (won.length + lost.length) * 100)}%` : '—', accent: 'var(--gold)' },
          { label: 'Sources', value: sources.length, accent: 'var(--gray)' },
        ].map(stat => (
          <div key={stat.label} style={{
            background: 'var(--charcoal-soft)', borderRadius: 12,
            padding: '16px 20px', border: '1px solid var(--charcoal-mid)'
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: stat.accent, fontFamily: 'IBM Plex Mono' }}>
              {stat.value}
            </div>
            <div style={{ fontSize: 12, color: 'var(--gray)', marginTop: 2 }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Table (client component for filtering) */}
      <BidTable bids={bids} sources={sources} today={today.toISOString()} in3={in3.toISOString()} in7={in7.toISOString()} />
    </main>
  )
}
