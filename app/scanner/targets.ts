// Ben's Phase 2 target agencies — coverage panel on /scanner.
// The list lives in bid-scanner/data/target_agencies.json so the scanner side
// can read the same file later.
import targetData from '../../bid-scanner/data/target_agencies.json'

export type Coverage = 'covered' | 'partial' | 'gap'

export type Target = {
  name: string
  region: string
  match: string
  platform: string
  coverage: Coverage
  note?: string
}

export type TargetBidRow = {
  agency: string | null
  title: string
  source: string
  first_seen_at: string
  last_seen_at: string
  is_relevant: boolean
  relevance_reason: string | null
}

export type TargetRow = Target & {
  lastSeen: string | null     // newest last_seen_at of any matching bid
  seen90: number              // matching bids first seen in the window
  flooring90: number          // …of which flagged flooring-relevant at scan time
  sources: string[]
}

// First scan that wrote bids.relevance_reason (add_relevance_reason.sql).
const RELEVANCE_REASON_SINCE = '2026-09-14'

export const TARGETS: Target[] = (targetData as { targets: Target[] }).targets

export function targetCoverage(bids: TargetBidRow[], windowStartMs: number): TargetRow[] {
  return TARGETS.map(t => {
    const re = new RegExp(t.match, 'i')
    const hits = bids.filter(b => re.test(`${b.agency ?? ''} — ${b.title}`))
    const inWindow = hits.filter(b => Date.parse(b.first_seen_at) >= windowStartMs)
    const lastSeen = hits.reduce<string | null>(
      (max, b) => (!max || b.last_seen_at > max ? b.last_seen_at : max), null)
    return {
      ...t,
      lastSeen,
      seen90: inWindow.length,
      // is_relevant flips to false when the expirer retires a past-due bid, so
      // also count bids the filter kept (relevance_reason NULL) — but only from
      // when that column started being written; earlier rows are NULL either way.
      flooring90: inWindow.filter(b => b.is_relevant
        || (b.relevance_reason === null && b.first_seen_at >= RELEVANCE_REASON_SINCE)).length,
      sources: Array.from(new Set(hits.map(b => b.source))).sort(),
    }
  })
}
