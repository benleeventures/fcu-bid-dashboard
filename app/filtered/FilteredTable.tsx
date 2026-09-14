'use client'

import { useMemo, useState } from 'react'
import { promoteBid } from '../actions/bids'

export type FilteredBid = {
  id: string
  bid_id: string
  title: string
  agency: string | null
  source: string | null
  due_date: string | null
  due_date_raw: string | null
  url: string | null
  first_seen_at: string
  relevance_reason: string | null
}

type Group = {
  key: string
  title: string
  sub: string
  reasons: (string | null)[]
  collapsedByDefault: boolean
}

const GROUPS: Group[] = [
  {
    key: 'claude_rejected',
    title: 'Claude said no',
    sub: 'Construction-adjacent title, but the second-pass check rejected it. Most likely to be a real miss — check these first.',
    reasons: ['claude_rejected'],
    collapsedByDefault: false,
  },
  {
    key: 'no_keyword',
    title: 'No flooring keyword in the title',
    sub: 'Nothing flooring-related in the title at all. Worth a skim in case the scope is buried (e.g. a generic "renovation" or "modernization" listing).',
    reasons: ['no_keyword'],
    collapsedByDefault: false,
  },
  {
    key: 'other_noise',
    title: 'Other trades',
    sub: 'Roofing, HVAC, paving, janitorial, and similar — no floor scope. Mostly genuine noise.',
    reasons: ['other_trade', 'non_flooring_service'],
    collapsedByDefault: true,
  },
  {
    key: 'uncategorised',
    title: 'Uncategorised',
    sub: 'Rejected before this tracking existed, or not re-scanned since. Not sortable into a bucket yet.',
    reasons: [null],
    collapsedByDefault: true,
  },
]

function formatDate(s: string | null): string {
  if (!s) return '—'
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function prettyDue(raw: string | null, iso: string | null): string {
  if (raw && !/^\d{4}-\d{2}-\d{2}([T ]|$)/.test(raw.trim())) return raw
  return formatDate(iso ?? raw)
}

export default function FilteredTable({ bids }: { bids: FilteredBid[] }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(GROUPS.map(g => [g.key, g.collapsedByDefault])),
  )
  const [promoted, setPromoted] = useState<Set<string>>(new Set())
  const [promoting, setPromoting] = useState<Set<string>>(new Set())

  const grouped = useMemo(() => {
    return GROUPS.map(g => ({
      group: g,
      rows: bids.filter(b => g.reasons.includes(b.relevance_reason) && !promoted.has(b.bid_id)),
    }))
  }, [bids, promoted])

  async function handlePromote(bidId: string) {
    setPromoting(s => new Set(s).add(bidId))
    const res = await promoteBid(bidId)
    if (res.ok) {
      setPromoted(s => new Set(s).add(bidId))
    } else {
      setPromoting(s => { const n = new Set(s); n.delete(bidId); return n })
      alert(`Couldn't promote this bid: ${res.error ?? 'unknown error'}`)
    }
  }

  return (
    <div>
      {grouped.map(({ group, rows }) => (
        <section key={group.key} style={{ marginBottom: 20 }}>
          <button
            onClick={() => setCollapsed(c => ({ ...c, [group.key]: !c[group.key] }))}
            style={{
              display: 'flex', alignItems: 'baseline', gap: 10, width: '100%',
              background: 'none', border: 'none', padding: '10px 2px', cursor: 'pointer',
              borderBottom: '1px solid var(--border)', textAlign: 'left',
            }}
          >
            <span style={{ fontSize: 11, color: 'var(--ink-dim)', width: 14 }}>
              {collapsed[group.key] ? '▸' : '▾'}
            </span>
            <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>{group.title}</span>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-dim)',
              background: 'var(--surface-sunken)', padding: '1px 7px', borderRadius: 10,
            }}>{rows.length}</span>
            <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--ink-dim)', fontWeight: 400 }}>
              {group.sub}
            </span>
          </button>

          {!collapsed[group.key] && (
            rows.length === 0 ? (
              <div style={{ padding: '16px 4px', color: 'var(--ink-dim)', fontSize: 13 }}>
                None in the last 30 days.
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 320 }}>Project</th>
                      <th style={{ width: 160 }}>Agency</th>
                      <th style={{ width: 110 }}>Found on</th>
                      <th style={{ width: 100 }}>Found</th>
                      <th style={{ width: 110 }}>Due date</th>
                      <th style={{ width: 70 }} />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(b => (
                      <tr key={b.id}>
                        <td style={{ overflow: 'hidden' }}>
                          {b.url ? (
                            <a href={b.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--ink)', fontWeight: 500 }}>
                              {b.title}
                            </a>
                          ) : (
                            <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{b.title}</span>
                          )}
                        </td>
                        <td style={{ color: 'var(--ink-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {b.agency || '—'}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap', color: 'var(--ink-dim)' }}>
                          {b.source || '—'}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap', color: 'var(--ink-dim)' }}>
                          {formatDate(b.first_seen_at)}
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap', color: 'var(--ink-dim)' }}>
                          {prettyDue(b.due_date_raw, b.due_date)}
                        </td>
                        <td style={{ whiteSpace: 'nowrap', textAlign: 'center' }}>
                          <button
                            onClick={() => handlePromote(b.bid_id)}
                            disabled={promoting.has(b.bid_id)}
                            className="row-action row-action--restore"
                            title="This is actually relevant — move it to the main dashboard"
                            aria-label="Promote to relevant"
                            style={{ opacity: promoting.has(b.bid_id) ? 0.5 : 1 }}
                          >
                            {promoting.has(b.bid_id) ? '…' : '↑'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}
        </section>
      ))}
    </div>
  )
}
