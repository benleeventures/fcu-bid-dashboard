import { createClient } from '@supabase/supabase-js'
import Nav from '../Nav'
import FilteredTable, { FilteredBid } from './FilteredTable'

export const revalidate = 300

const WINDOW_DAYS = 30

async function getData(): Promise<FilteredBid[]> {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return []

  const sb = createClient(url, key)
  const since = new Date(Date.now() - WINDOW_DAYS * 86400000).toISOString()

  const { data, error } = await sb
    .from('bids')
    .select('id, bid_id, title, agency, source, due_date, due_date_raw, url, first_seen_at, relevance_reason')
    .eq('is_relevant', false)
    .gte('first_seen_at', since)
    .order('first_seen_at', { ascending: false })
    .limit(2000)

  if (error) {
    console.error('filtered bids fetch error:', error.message)
    return []
  }
  return (data ?? []) as FilteredBid[]
}

export default async function FilteredPage() {
  const bids = await getData()

  return (
    <>
      <Nav active="filtered" />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 24px 64px' }}>
        <header style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 28, letterSpacing: '-0.4px' }}>Filtered Out</h1>
          <p style={{ color: 'var(--ink-dim)', marginTop: 4, fontSize: 13, maxWidth: 640 }}>
            Bids the relevance filter rejected in the last {WINDOW_DAYS} days. These never hit the
            main dashboard or the daily email — this page exists so the filter can be checked and
            retuned if it's dropping real flooring work. If a bid below is actually worth bidding,
            promote it.
          </p>
        </header>

        {bids.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--ink-dim)', fontSize: 14 }}>
            <div style={{ fontSize: 32, marginBottom: 16 }}>🗂️</div>
            <div style={{ fontWeight: 500, marginBottom: 8 }}>Nothing filtered out recently</div>
            <div>This page fills in as the scanner rejects bids over the next {WINDOW_DAYS} days.</div>
          </div>
        ) : (
          <FilteredTable bids={bids} />
        )}
      </main>
    </>
  )
}
