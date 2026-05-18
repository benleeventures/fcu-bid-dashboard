import { createClient } from '@supabase/supabase-js'
import IntelTable from './IntelTable'
import IntelOverview from './IntelOverview'

export const dynamic = 'force-dynamic'

export type IntelSubmission = {
  id: string
  bid_amount: number | null
  is_winner: boolean
  rank: number | null
  raw_vendor_name: string
  vendor: { canonical_name: string } | null
}

export type IntelBid = {
  id: string
  portal_id: string
  agency: string | null
  title: string
  awarded_at: string | null
  winner_amount: number | null
  total_bidders: number | null
  winner_vendor: { canonical_name: string } | null
  submissions: IntelSubmission[]
}

export type CompetitorStat = {
  vendor_name: string
  wins: number
  avg_win_margin_pct: number | null   // (winner - 2nd) / 2nd × 100, negative = cheaper
  avg_below_field_pct: number | null  // (winner - avg_field) / avg_field × 100
  agencies: string[]
}

export type PricingInsight = {
  avg_gap_pct: number | null            // avg (2nd - winner) / winner
  most_competitive: { agency: string; avg_bidders: number }[]
  least_competitive: { agency: string; avg_bidders: number }[]
}

async function getIntelData(): Promise<IntelBid[]> {
  const url  = process.env.SUPABASE_URL
  const key  = process.env.SUPABASE_KEY
  if (!url || !key) return []

  try {
    const sb = createClient(url, key)
    const { data, error } = await sb
      .from('bid_intel')
      .select(`
        id, portal_id, agency, title, awarded_at, winner_amount, total_bidders,
        winner_vendor:vendors!winner_vendor_id ( canonical_name ),
        submissions:bid_intel_submissions (
          id, bid_amount, is_winner, rank, raw_vendor_name,
          vendor:vendors ( canonical_name )
        )
      `)
      .order('awarded_at', { ascending: false })
      .limit(500)

    if (error) {
      console.error('Intel fetch error:', error.message)
      return []
    }

    return ((data ?? []) as any[]).map(row => ({
      ...row,
      winner_vendor: Array.isArray(row.winner_vendor)
        ? (row.winner_vendor[0] ?? null)
        : row.winner_vendor,
      submissions: (row.submissions ?? []).sort(
        (a: IntelSubmission, b: IntelSubmission) =>
          (a.rank ?? 999) - (b.rank ?? 999)
      ),
    })) as IntelBid[]
  } catch (e) {
    console.error('Intel page error:', e)
    return []
  }
}

function computeCompetitors(intel: IntelBid[]): CompetitorStat[] {
  const map = new Map<string, {
    wins: number
    winMargins: number[]
    belowField: number[]
    agencies: Set<string>
  }>()

  for (const bid of intel) {
    const winnerName =
      bid.winner_vendor?.canonical_name ??
      bid.submissions.find(s => s.is_winner)?.vendor?.canonical_name ??
      bid.submissions.find(s => s.rank === 1)?.raw_vendor_name

    if (!winnerName || bid.winner_amount == null) continue

    if (!map.has(winnerName)) {
      map.set(winnerName, { wins: 0, winMargins: [], belowField: [], agencies: new Set() })
    }
    const stat = map.get(winnerName)!
    stat.wins++
    if (bid.agency) stat.agencies.add(bid.agency)

    const amounts = bid.submissions
      .filter(s => s.bid_amount != null)
      .map(s => s.bid_amount!)
      .sort((a, b) => a - b)

    if (amounts.length >= 2 && bid.winner_amount != null) {
      const secondPlace = amounts[1]
      stat.winMargins.push(((bid.winner_amount - secondPlace) / secondPlace) * 100)
    }

    if (amounts.length >= 1 && bid.winner_amount != null) {
      const avg = amounts.reduce((a, b) => a + b, 0) / amounts.length
      stat.belowField.push(((bid.winner_amount - avg) / avg) * 100)
    }
  }

  const avg = (arr: number[]) =>
    arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null

  return Array.from(map.entries())
    .map(([vendor_name, s]) => ({
      vendor_name,
      wins: s.wins,
      avg_win_margin_pct: avg(s.winMargins),
      avg_below_field_pct: avg(s.belowField),
      agencies: Array.from(s.agencies),
    }))
    .sort((a, b) => b.wins - a.wins)
    .slice(0, 15)
}

function computePricingInsights(intel: IntelBid[]): PricingInsight {
  const gaps: number[] = []

  for (const bid of intel) {
    if (bid.winner_amount == null) continue
    const amounts = bid.submissions
      .filter(s => s.bid_amount != null)
      .map(s => s.bid_amount!)
      .sort((a, b) => a - b)
    if (amounts.length >= 2) {
      const gap = ((amounts[1] - amounts[0]) / amounts[0]) * 100
      gaps.push(gap)
    }
  }

  const agencyBidders = new Map<string, number[]>()
  for (const bid of intel) {
    if (!bid.agency || !bid.total_bidders) continue
    if (!agencyBidders.has(bid.agency)) agencyBidders.set(bid.agency, [])
    agencyBidders.get(bid.agency)!.push(bid.total_bidders)
  }

  const agencyAvg = Array.from(agencyBidders.entries())
    .map(([agency, counts]) => ({
      agency,
      avg_bidders: Math.round((counts.reduce((a, b) => a + b, 0) / counts.length) * 10) / 10,
    }))
    .sort((a, b) => b.avg_bidders - a.avg_bidders)

  return {
    avg_gap_pct: gaps.length
      ? Math.round((gaps.reduce((a, b) => a + b, 0) / gaps.length) * 10) / 10
      : null,
    most_competitive: agencyAvg.slice(0, 5),
    least_competitive: agencyAvg.slice(-5).reverse(),
  }
}

export default async function IntelPage() {
  const intel = await getIntelData()
  const competitors = computeCompetitors(intel)
  const pricing = computePricingInsights(intel)
  const agencies = Array.from(new Set(intel.map(b => b.agency).filter(Boolean))) as string[]

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
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.3px' }}>Competitive Intel</h1>
          </div>
          <p style={{ color: 'var(--gray)', marginTop: 4, fontFamily: 'IBM Plex Mono', fontSize: 11 }}>
            PlanetBids — awarded bids · submission tabulations · vendor analysis
          </p>
        </div>
        <div style={{ textAlign: 'right', color: 'var(--gray)', fontSize: 11, fontFamily: 'IBM Plex Mono' }}>
          <a href="/" style={{ color: 'var(--gold-light)', textDecoration: 'none' }}>← Bid Dashboard</a>
          {intel.length > 0 && (
            <div style={{ marginTop: 4 }}>
              {intel.length} awarded bids · {agencies.length} agencies
            </div>
          )}
        </div>
      </div>

      {intel.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '80px 20px',
          color: 'var(--gray)', fontFamily: 'IBM Plex Mono', fontSize: 13
        }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>📭</div>
          <div style={{ fontWeight: 500, marginBottom: 8 }}>No intel data yet (rows: {intel.length})</div>
          <div>Run <code style={{ color: 'var(--gold)' }}>python main.py --intel</code> to scan PlanetBids awarded bids</div>
        </div>
      ) : (
        <>
          <IntelOverview competitors={competitors} pricing={pricing} totalBids={intel.length} />
          <IntelTable bids={intel} agencies={agencies} />
        </>
      )}
    </main>
  )
}
