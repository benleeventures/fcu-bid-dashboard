import { createClient } from '@supabase/supabase-js'
import Nav from '../../Nav'
import BidOutcomeTracker from './BidOutcomeTracker'
import GoNoGoCard from './GoNoGoCard'
import type { BidStatus } from '../../actions/bids'

export const revalidate = 0

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

function bidTypeLabel(t: string | null | undefined): string | null {
  return {
    furnish_install: 'Furnish + install',
    install_only: 'Install only',
    furnish_only: 'Furnish only',
    maintenance: 'Maintenance',
  }[t ?? ''] ?? null
}

export default async function BidDetailPage({ params }: { params: { id: string } }) {
  const bidId = decodeURIComponent(params.id)
  const client = sb()

  const [{ data: bid }, { data: spec }] = await Promise.all([
    client.from('bids').select('*').eq('bid_id', bidId).single(),
    client.from('bid_specs').select('*').eq('bid_id', bidId).maybeSingle(),
  ])

  if (!bid) {
    return (
      <>
        <Nav />
        <main style={{ maxWidth: 900, margin: '0 auto', padding: '28px 24px 64px' }}>
          <a href="/" className="btn">
            <span aria-hidden style={{ opacity: .6 }}>←</span> All bids
          </a>
          <p style={{ color: 'var(--ink-dim)', marginTop: 32, fontFamily: 'var(--font-mono)' }}>Bid not found: {bidId}</p>
        </main>
      </>
    )
  }

  const formatDate = (s: string | null) => s
    ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '—'

  return (
    <>
      <Nav />

      <main style={{ maxWidth: 900, margin: '0 auto', padding: '28px 24px 64px' }}>
        {/* Back link + portal */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, gap: 12, flexWrap: 'wrap' }}>
          <a href="/" className="btn">
            <span aria-hidden style={{ opacity: .6 }}>←</span> All bids
          </a>
          {bid.url && (
            <a href={bid.url} target="_blank" rel="noopener noreferrer" className="btn">
              Open Portal <span aria-hidden style={{ opacity: .6 }}>↗</span>
            </a>
          )}
        </div>

        {/* Bid header */}
        <header style={{ marginBottom: 24, paddingBottom: 22, borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
            {bid.is_relevant && <span style={{ color: 'var(--star)', fontSize: 18, lineHeight: 1.2 }}>★</span>}
            <h1 style={{ fontSize: 28, letterSpacing: '-0.4px', lineHeight: 1.15 }}>{bid.title}</h1>
          </div>
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--ink-dim)' }}>
            <span style={{ color: 'var(--gold-strong)' }}>{bid.bid_id}</span>
            {bid.agency && <span>{bid.agency}</span>}
            {bid.source && <span>{bid.source}</span>}
            {bid.due_date && <span>Due: <span style={{ color: 'var(--ink)' }}>{bid.due_date_raw || formatDate(bid.due_date)}</span></span>}
            {bid.url && <a href={bid.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold-strong)' }}>Portal ↗</a>}
          </div>

          {/* Spec summary strip */}
          {spec && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 14 }}>
              {spec.total_sqft && <span className="chip">{spec.total_sqft.toLocaleString()} SF</span>}
              {spec.flooring_types?.length && <span className="chip">{spec.flooring_types.join(' · ')}</span>}
              {bidTypeLabel(spec.bid_type ?? spec.raw_extract?.bid_type) && (
                <span className="chip">{bidTypeLabel(spec.bid_type ?? spec.raw_extract?.bid_type)}</span>
              )}
              {(spec.project_city || spec.raw_extract?.project_city) && (
                <span className="chip">{spec.project_city || spec.raw_extract?.project_city}</span>
              )}
              {(spec.flooring_is_primary === false || spec.raw_extract?.flooring_is_primary === false) && (
                <span className="chip" style={{ background: 'var(--red-tint)', color: 'var(--red)' }}>Flooring is minor scope</span>
              )}
              {spec.prevailing_wage === true && <span className="chip" style={{ background: 'var(--orange-tint)', color: 'var(--orange)' }}>Prevailing wage</span>}
              {spec.bid_bond === true && <span className="chip" style={{ background: 'var(--orange-tint)', color: 'var(--orange)' }}>Bid bond {spec.bid_bond_pct ? spec.bid_bond_pct + '%' : ''}</span>}
              {spec.walk_required === true && <span className="chip" style={{ background: 'var(--orange-tint)', color: 'var(--orange)' }}>Job walk {spec.walk_date_raw || spec.walk_date || ''}</span>}
            </div>
          )}
          {spec?.summary && (
            <p style={{ marginTop: 14, fontSize: 13.5, color: 'var(--ink-dim)', lineHeight: 1.6, maxWidth: 720 }}>
              {spec.summary}
            </p>
          )}
        </header>

        {/* Winnability score card — always shown; card handles the review state */}
        <GoNoGoCard
          bid={{ due_date: bid.due_date, county: bid.county, geo_status: bid.geo_status }}
          spec={spec ? {
            flooring_is_primary: spec.flooring_is_primary ?? spec.raw_extract?.flooring_is_primary ?? null,
            award_method: spec.award_method ?? spec.raw_extract?.award_method ?? null,
            project_city: spec.project_city ?? spec.raw_extract?.project_city ?? null,
          } : null}
          bidId={bid.bid_id}
        />

        {/* Bid outcome tracker */}
        <BidOutcomeTracker
          bidId={bidId}
          initialStatus={(bid.bid_status as BidStatus) ?? 'active'}
          initialSubmitted={bid.submitted_amount ?? null}
          initialAward={bid.award_amount ?? null}
          estimateTotal={null}
        />
      </main>
    </>
  )
}
