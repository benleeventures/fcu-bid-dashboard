import { createClient } from '@supabase/supabase-js'
import { getRates } from '../../actions/settings'
import EstimateWorksheet from './EstimateWorksheet'
import BidOutcomeTracker from './BidOutcomeTracker'
import GoNoGoCard from './GoNoGoCard'
import type { BidStatus } from '../../actions/bids'

export const revalidate = 0

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

export default async function BidDetailPage({ params }: { params: { id: string } }) {
  const bidId = decodeURIComponent(params.id)
  const client = sb()

  const [
    { data: bid },
    { data: spec },
    { data: estimate },
    rates,
  ] = await Promise.all([
    client.from('bids').select('*').eq('bid_id', bidId).single(),
    client.from('bid_specs').select('*').eq('bid_id', bidId).maybeSingle(),
    client.from('estimates').select('*').eq('bid_id', bidId).maybeSingle(),
    getRates(),
  ])

  if (!bid) {
    return (
      <main style={{ maxWidth: 800, margin: '0 auto', padding: '32px 16px' }}>
        <a href="/" style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono', textDecoration: 'none' }}>← Back</a>
        <p style={{ color: 'var(--gray)', marginTop: 32, fontFamily: 'IBM Plex Mono' }}>Bid not found: {bidId}</p>
      </main>
    )
  }

  // Determine if estimate is stale (rates changed after estimate was saved)
  const isStale = !!(
    estimate &&
    estimate.rates_version &&
    rates.updatedAt &&
    new Date(rates.updatedAt) > new Date(estimate.rates_version)
  )

  const formatDate = (s: string | null) => s
    ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '—'

  return (
    <main style={{ maxWidth: 900, margin: '0 auto', padding: '32px 16px' }}>
      {/* Nav */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <a href="/" style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono', textDecoration: 'none' }}>
          ← All bids
        </a>
        <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          {bid.url && (
            <a href={bid.url} target="_blank" rel="noopener noreferrer" style={{
              color: 'var(--gold)', fontSize: 12, fontFamily: 'IBM Plex Mono',
              textDecoration: 'none', border: '1px solid var(--gold)', borderRadius: 6,
              padding: '4px 10px',
            }}>
              Open Portal ↗
            </a>
          )}
          <a href="/settings" style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono', textDecoration: 'none' }}>
            ⚙ Rate settings
          </a>
        </div>
      </div>

      {/* Bid header */}
      <div style={{ marginBottom: 28, paddingBottom: 24, borderBottom: '1px solid var(--charcoal-mid)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 8 }}>
          {bid.is_relevant && <span style={{ color: 'var(--star)', fontSize: 16, marginTop: 3 }}>★</span>}
          <h1 style={{ fontSize: 20, fontWeight: 700, lineHeight: 1.3, letterSpacing: '-0.3px' }}>{bid.title}</h1>
        </div>
        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', fontSize: 12, fontFamily: 'IBM Plex Mono', color: 'var(--gray)' }}>
          <span style={{ color: 'var(--gold-light)' }}>{bid.bid_id}</span>
          {bid.agency && <span>{bid.agency}</span>}
          {bid.source && <span>{bid.source}</span>}
          {bid.due_date && <span>Due: <span style={{ color: 'var(--white)' }}>{bid.due_date_raw || formatDate(bid.due_date)}</span></span>}
          {bid.url && <a href={bid.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold)', textDecoration: 'none' }}>Portal ↗</a>}
        </div>

        {/* Spec summary strip */}
        {spec && (
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 14, fontSize: 11, fontFamily: 'IBM Plex Mono' }}>
            {spec.total_sqft && <span style={{ color: 'var(--white)' }}>{spec.total_sqft.toLocaleString()} SF</span>}
            {spec.flooring_types?.length && <span style={{ color: 'var(--gray)' }}>{spec.flooring_types.join(' · ')}</span>}
            {spec.prevailing_wage === true  && <span style={{ color: 'var(--orange)' }}>Prevailing wage</span>}
            {spec.bid_bond === true         && <span style={{ color: 'var(--orange)' }}>Bid bond {spec.bid_bond_pct ? spec.bid_bond_pct + '%' : ''}</span>}
            {spec.walk_required === true    && <span style={{ color: 'var(--orange)' }}>Job walk {spec.walk_date_raw || spec.walk_date || ''}</span>}
          </div>
        )}
        {spec?.summary && (
          <p style={{ marginTop: 12, fontSize: 13, color: 'var(--gray)', lineHeight: 1.6, maxWidth: 700 }}>
            {spec.summary}
          </p>
        )}
      </div>

      {/* Go/No-Go score card — only when spec is parsed */}
      {spec ? (
        <GoNoGoCard
          bid={{ is_relevant: bid.is_relevant, due_date: bid.due_date }}
          spec={spec}
        />
      ) : (
        <div style={{
          marginBottom: 24, padding: '16px 20px',
          background: 'var(--charcoal-soft)', borderRadius: 12,
          border: '1px solid var(--charcoal-mid)',
          fontSize: 12, fontFamily: 'IBM Plex Mono', color: 'var(--gray)',
        }}>
          No documents parsed yet — score unavailable.{' '}
          Run <code style={{ background: 'var(--charcoal-mid)', padding: '1px 6px', borderRadius: 3 }}>
            python parser.py --save {bid.bid_id} '...'
          </code> to unlock scoring.
        </div>
      )}

      {/* Download bid package — only when estimate exists */}
      {estimate && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 20 }}>
          <a
            href={`/api/bids/${encodeURIComponent(bidId)}/package`}
            download
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: 'var(--charcoal-soft)', color: 'var(--gold)',
              border: '1px solid var(--gold)', borderRadius: 8,
              padding: '8px 16px', fontSize: 12, fontFamily: 'IBM Plex Mono',
              fontWeight: 600, textDecoration: 'none', letterSpacing: '0.02em',
            }}
          >
            ↓ Download Bid Package PDF
          </a>
        </div>
      )}

      {/* Estimate worksheet */}
      <EstimateWorksheet
        bidId={bidId}
        spec={spec}
        estimate={estimate}
        rates={rates}
        isStale={isStale}
      />

      {/* Bid outcome tracker */}
      <BidOutcomeTracker
        bidId={bidId}
        initialStatus={(bid.bid_status as BidStatus) ?? 'active'}
        initialSubmitted={bid.submitted_amount ?? null}
        initialAward={bid.award_amount ?? null}
        estimateTotal={
          estimate
            ? ((estimate.selected_markup === 30 ? estimate.markup_30 : estimate.markup_25) ?? null)
            : null
        }
      />
    </main>
  )
}
