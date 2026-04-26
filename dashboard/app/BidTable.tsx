'use client'

import { useState, useMemo } from 'react'
import type { Bid, BidSpec, BidStatus } from './page'
import { scoreGoNoGo, verdictConfig } from './lib/scoring'

type Props = {
  bids: Bid[]
  sources: string[]
  today: string
  in3: string
  in7: string
}

export default function BidTable({ bids, sources, today, in3, in7 }: Props) {
  const [filterRelevant, setFilterRelevant] = useState(false)
  const [filterSource, setFilterSource] = useState('')
  const [filterDue, setFilterDue] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)

  const t = new Date(today)
  const d3 = new Date(in3)
  const d7 = new Date(in7)

  const archivedCount = useMemo(
    () => bids.filter(b => b.bid_status === 'no_bid').length,
    [bids],
  )

  const filtered = useMemo(() => {
    return bids.filter(b => {
      if (showArchived) {
        if (b.bid_status !== 'no_bid') return false
      } else {
        if (b.bid_status === 'no_bid') return false
      }
      if (filterRelevant && !b.is_relevant) return false
      if (filterSource && b.source !== filterSource) return false
      if (search) {
        const q = search.toLowerCase()
        if (
          !b.title.toLowerCase().includes(q) &&
          !(b.agency || '').toLowerCase().includes(q) &&
          !(b.search_keyword || '').toLowerCase().includes(q)
        ) return false
      }
      if (filterDue === 'week') {
        if (!b.due_date) return false
        const d = new Date(b.due_date)
        if (d < t || d > d7) return false
      }
      if (filterDue === 'urgent') {
        if (!b.due_date) return false
        const d = new Date(b.due_date)
        if (d < t || d > d3) return false
      }
      if (filterStatus && (b.bid_status ?? 'active') !== filterStatus) return false
      return true
    })
  }, [bids, showArchived, filterRelevant, filterSource, filterDue, search, t, d3, d7])

  function urgencyColor(due_date: string | null): string {
    if (!due_date) return 'transparent'
    const d = new Date(due_date)
    if (d < t) return 'var(--gray)'
    if (d <= d3) return 'var(--red)'
    if (d <= d7) return 'var(--orange)'
    return 'transparent'
  }

  function formatDate(s: string | null): string {
    if (!s) return '—'
    const d = new Date(s)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search bids…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={inputStyle}
        />
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)} style={inputStyle}>
          <option value="">All sources</option>
          {sources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filterDue} onChange={e => setFilterDue(e.target.value)} style={inputStyle}>
          <option value="">Any due date</option>
          <option value="week">Due this week</option>
          <option value="urgent">Due in 3 days</option>
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={inputStyle}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="submitted">Submitted</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
          <option value="no_bid">No Bid</option>
        </select>
        <button
          onClick={() => setFilterRelevant(r => !r)}
          style={{
            ...inputStyle,
            background: filterRelevant ? 'var(--gold)' : 'var(--charcoal-soft)',
            color: filterRelevant ? 'var(--charcoal)' : 'var(--white)',
            cursor: 'pointer',
            fontWeight: filterRelevant ? 600 : 400,
          }}
        >
          {filterRelevant ? '★ Flooring only' : '☆ Flooring only'}
        </button>
        <span style={{ color: 'var(--gray)', fontSize: 12, marginLeft: 'auto', fontFamily: 'IBM Plex Mono' }}>
          {filtered.length} bids
        </span>
      </div>

      {/* Archive toggle */}
      {archivedCount > 0 && (
        <div style={{ marginBottom: 10 }}>
          <button
            onClick={() => setShowArchived(v => !v)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--gray)', fontSize: 11, fontFamily: 'IBM Plex Mono',
              padding: 0, textDecoration: 'underline', textUnderlineOffset: 3,
            }}
          >
            {showArchived ? '← Back to active bids' : `Show ${archivedCount} archived (no bid)`}
          </button>
        </div>
      )}

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 11, fontFamily: 'IBM Plex Mono', color: 'var(--gray)' }}>
        <span><span style={{ color: 'var(--red)' }}>●</span> Due &lt;3 days</span>
        <span><span style={{ color: 'var(--orange)' }}>●</span> Due this week</span>
        <span><span style={{ color: 'var(--gold)' }}>★</span> Flooring relevant</span>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid var(--charcoal-mid)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <thead>
            <tr style={{ background: 'var(--charcoal-soft)', borderBottom: '1px solid var(--charcoal-mid)' }}>
              <th style={{ ...thStyle, width: 28 }} />
              <th style={{ ...thStyle, width: 140 }}>Bid ID</th>
              <th style={thStyle}>Title</th>
              <th style={{ ...thStyle, width: 170 }}>Agency</th>
              <th style={{ ...thStyle, width: 110 }}>Source</th>
              <th style={{ ...thStyle, width: 100 }}>Published</th>
              <th style={{ ...thStyle, width: 100 }}>Due Date</th>
              <th style={{ ...thStyle, width: 80 }}>Status</th>
              <th style={{ ...thStyle, width: 28 }} />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--gray)' }}>
                  No bids match your filters.
                </td>
              </tr>
            ) : filtered.flatMap((b, i) => {
              const urg = urgencyColor(b.due_date)
              const isExpanded = expandedId === b.bid_id
              const hasSpec = !!b.spec
              const rowBg = i % 2 === 0 ? 'var(--charcoal)' : 'var(--charcoal-soft)'
              return [
                <tr
                  key={b.id}
                  onClick={() => setExpandedId(isExpanded ? null : b.bid_id)}
                  style={{
                    background: isExpanded ? 'var(--charcoal-mid)' : rowBg,
                    borderBottom: isExpanded ? 'none' : '1px solid var(--charcoal-mid)',
                    borderLeft: urg !== 'transparent' ? `3px solid ${urg}` : '3px solid transparent',
                    cursor: 'pointer',
                  }}
                >
                  <td style={{ ...tdStyle, width: 24, textAlign: 'center' }}>
                    {b.is_relevant && <span style={{ color: 'var(--gold)', fontSize: 13 }}>★</span>}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: 'IBM Plex Mono', fontSize: 11, color: 'var(--gray)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    <a
                      href={`/bids/${encodeURIComponent(b.bid_id)}`}
                      onClick={e => e.stopPropagation()}
                      style={{ color: 'var(--gold-light)', textDecoration: 'none' }}
                    >
                      {b.bid_id}
                    </a>
                  </td>
                  <td style={{ ...tdStyle, maxWidth: 340 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{ color: 'var(--white)' }}>{b.title}</span>
                      {b.search_keyword && (
                        <span style={{
                          fontSize: 10, padding: '1px 5px', borderRadius: 4,
                          background: 'var(--charcoal-mid)', color: 'var(--gray)', fontFamily: 'IBM Plex Mono'
                        }}>{b.search_keyword}</span>
                      )}
                      {!hasSpec && (
                        <span style={{
                          fontSize: 10, padding: '1px 5px', borderRadius: 4,
                          background: 'var(--charcoal-mid)', color: 'var(--gray)', fontFamily: 'IBM Plex Mono'
                        }}>No docs</span>
                      )}
                      <ScorePill bid={b} spec={b.spec ?? null} />
                    </div>
                  </td>
                  <td style={{ ...tdStyle, color: 'var(--gray)', maxWidth: 180 }}>{b.agency || '—'}</td>
                  <td style={{ ...tdStyle, fontFamily: 'IBM Plex Mono', fontSize: 11, whiteSpace: 'nowrap' }}>
                    <span style={{
                      padding: '2px 7px', borderRadius: 4,
                      background: sourceColor(b.source) + '22',
                      color: sourceColor(b.source),
                    }}>{b.source || '—'}</span>
                  </td>
                  <td style={{ ...tdStyle, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', fontSize: 11, whiteSpace: 'nowrap' }}>
                    {formatDate(b.published_date)}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: 'IBM Plex Mono', fontSize: 11, whiteSpace: 'nowrap', color: urg !== 'transparent' ? urg : 'var(--white)' }}>
                    {b.due_date_raw || formatDate(b.due_date)}
                  </td>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                    <StatusBadge status={b.bid_status ?? 'active'} />
                  </td>
                  <td style={{ ...tdStyle, width: 20, color: 'var(--gray)', fontSize: 11 }}>
                    {b.url && <a href={b.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} style={{ color: 'var(--gold-light)' }}>↗</a>}
                  </td>
                </tr>,
                isExpanded && (
                  <tr key={`${b.id}-detail`} style={{ background: 'var(--charcoal-mid)', borderBottom: '1px solid var(--charcoal-mid)' }}>
                    <td colSpan={9} style={{ padding: '0 14px 16px 14px' }}>
                      {hasSpec ? <SpecPanel spec={b.spec!} /> : (
                        <div style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono', padding: '8px 0' }}>
                          No spec parsed yet. Run <code style={{ background: 'var(--charcoal-soft)', padding: '1px 5px', borderRadius: 3 }}>python parser.py --bid-id={b.bid_id}</code> to extract.
                        </div>
                      )}
                    </td>
                  </tr>
                ),
              ].filter(Boolean)
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ScorePill({ bid, spec }: { bid: Bid; spec: BidSpec | null }) {
  if (!spec) return null
  const result = scoreGoNoGo(bid, spec)
  const cfg = verdictConfig[result.verdict]
  return (
    <span style={{
      fontSize: 10, padding: '1px 6px', borderRadius: 4,
      background: cfg.bg, color: cfg.color,
      fontFamily: 'IBM Plex Mono', fontWeight: 700,
      letterSpacing: '0.04em',
    }}>
      {cfg.label} {result.score}
    </span>
  )
}

function StatusBadge({ status }: { status: BidStatus | 'active' }) {
  const cfg: Record<string, { label: string; color: string }> = {
    active:    { label: 'Active',     color: 'var(--gray)' },
    submitted: { label: 'Submitted',  color: 'var(--gold)' },
    won:       { label: 'Won',        color: 'var(--green)' },
    lost:      { label: 'Lost',       color: 'var(--red)' },
    no_bid:    { label: 'No Bid',     color: '#636366' },
  }
  const { label, color } = cfg[status] ?? cfg.active
  if (status === 'active') return null
  return (
    <span style={{
      padding: '2px 7px', borderRadius: 4, fontSize: 10,
      fontFamily: 'IBM Plex Mono', fontWeight: 600,
      background: color + '22', color,
    }}>{label}</span>
  )
}

function sourceColor(source: string | null): string {
  switch (source) {
    case 'PlanetBids': return '#C8922A'
    case 'SAM.gov':    return '#30D158'
    default:           return '#8E8E93'
  }
}

const inputStyle: React.CSSProperties = {
  background: 'var(--charcoal-soft)',
  border: '1px solid var(--charcoal-mid)',
  borderRadius: 8,
  color: 'var(--white)',
  padding: '7px 12px',
  fontSize: 13,
  outline: 'none',
  fontFamily: 'Plus Jakarta Sans, sans-serif',
}

const thStyle: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--gray)',
  fontFamily: 'IBM Plex Mono',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '10px 14px',
  verticalAlign: 'top',
  lineHeight: 1.4,
}

function SpecPanel({ spec }: { spec: BidSpec }) {
  const tri = (val: boolean | null) => val === true ? '✓' : val === false ? '✗' : '?'
  const triColor = (val: boolean | null) => val === true ? 'var(--green)' : val === false ? 'var(--red)' : 'var(--gray)'

  return (
    <div style={{
      marginTop: 10,
      padding: '14px 16px',
      background: 'var(--charcoal-soft)',
      borderRadius: 8,
      border: '1px solid var(--charcoal-mid)',
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
      gap: '10px 20px',
      fontSize: 12,
    }}>
      {spec.summary && (
        <div style={{ gridColumn: '1 / -1', color: 'var(--white)', marginBottom: 4, lineHeight: 1.5 }}>
          {spec.summary}
        </div>
      )}
      <SpecItem label="Flooring types" value={(spec.flooring_types || []).join(', ') || '—'} />
      <SpecItem label="Total sqft" value={spec.total_sqft ? spec.total_sqft.toLocaleString() + ' SF' : '—'} />
      <SpecItem label="Rooms" value={spec.rooms || '—'} />
      <SpecItem label="Prevailing wage" value={tri(spec.prevailing_wage)} color={triColor(spec.prevailing_wage)} />
      <SpecItem label="Bid bond" value={spec.bid_bond ? `✓ ${spec.bid_bond_pct ? spec.bid_bond_pct + '%' : ''}` : tri(spec.bid_bond)} color={triColor(spec.bid_bond)} />
      <SpecItem label="Job walk" value={spec.walk_required ? `✓ ${spec.walk_date_raw || spec.walk_date || ''}` : tri(spec.walk_required)} color={triColor(spec.walk_required)} />
    </div>
  )
}

function SpecItem({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ color: color || 'var(--white)', fontFamily: 'IBM Plex Mono', fontSize: 12 }}>{value}</div>
    </div>
  )
}
