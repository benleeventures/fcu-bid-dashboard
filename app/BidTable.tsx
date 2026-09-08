'use client'

import { useState, useMemo } from 'react'
import type { Bid, BidSpec, BidStatus } from './page'
import { scoreGoNoGo, verdictConfig } from './lib/scoring'
import { updateBidStatus, updateBidFavorite } from './actions/bids'

type Props = {
  bids: Bid[]
  sources: string[]
  today: string
  in3: string
  in7: string
}

type SortField = 'due_date' | 'published_date' | 'walk_date'
type SortDir   = 'asc' | 'desc'

export default function BidTable({ bids, sources, today, in3, in7 }: Props) {
  const [filterSource, setFilterSource] = useState('')
  const [filterDue, setFilterDue] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterRelevant, setFilterRelevant] = useState('')
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [localStatus, setLocalStatus] = useState<Map<string, string>>(new Map())
  const [localFavorite, setLocalFavorite] = useState<Map<string, boolean>>(new Map())
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  function archiveBid(e: React.MouseEvent, bidId: string) {
    e.stopPropagation()
    setLocalStatus(m => new Map(m).set(bidId, 'no_bid'))
    updateBidStatus(bidId, 'no_bid')
  }

  function restoreBid(e: React.MouseEvent, bidId: string) {
    e.stopPropagation()
    setLocalStatus(m => new Map(m).set(bidId, 'active'))
    updateBidStatus(bidId, 'active')
  }

  function handleFavorite(e: React.MouseEvent, bidId: string) {
    e.stopPropagation()
    const current = localFavorite.has(bidId)
      ? localFavorite.get(bidId)!
      : (bids.find(b => b.bid_id === bidId)?.is_favorite ?? false)
    const next = !current
    setLocalFavorite(m => new Map(m).set(bidId, next))
    updateBidFavorite(bidId, next)
  }

  function toggleSort(field: SortField) {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('asc') }
  }

  function sortIndicator(field: SortField) {
    if (sortField !== field) return ' ↕'
    return sortDir === 'asc' ? ' ↑' : ' ↓'
  }

  const t  = new Date(today)
  const d3 = new Date(in3)
  const d7 = new Date(in7)

  const archivedCount = useMemo(
    () => bids.filter(b => {
      const s = localStatus.get(b.bid_id) ?? b.bid_status
      return s === 'no_bid' || s === 'expired'
    }).length,
    [bids, localStatus],
  )

  const displayBids = useMemo(() => {
    const filtered = bids.filter(b => {
      const status = localStatus.get(b.bid_id) ?? b.bid_status
      const isArchived = status === 'no_bid' || status === 'expired'
      if (showArchived && !isArchived) return false
      if (!showArchived && isArchived) return false
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
      if (filterRelevant === 'yes' && !b.is_relevant) return false
      if (filterRelevant === 'no' && b.is_relevant) return false
      return true
    })

    // Sort by selected column (nulls to bottom)
    if (sortField) {
      filtered.sort((a, b) => {
        const av = sortField === 'walk_date' ? (a.spec?.walk_date ?? null) : (a[sortField as 'due_date' | 'published_date'] ?? null)
        const bv = sortField === 'walk_date' ? (b.spec?.walk_date ?? null) : (b[sortField as 'due_date' | 'published_date'] ?? null)
        if (!av && !bv) return 0
        if (!av) return 1
        if (!bv) return -1
        const cmp = av < bv ? -1 : av > bv ? 1 : 0
        return sortDir === 'asc' ? cmp : -cmp
      })
    }

    // Pin favorites to top, preserving sort order within each group
    const isFav = (b: Bid) => localFavorite.get(b.bid_id) ?? b.is_favorite
    const favs = filtered.filter(isFav)
    const rest = filtered.filter(b => !isFav(b))
    return [...favs, ...rest]
  }, [bids, showArchived, filterSource, filterDue, search, filterStatus, filterRelevant, sortField, sortDir, localStatus, localFavorite, t, d3, d7])

  function urgencyBadge(due_date: string | null): { label: string; color: string } | null {
    if (!due_date) return null
    const d = new Date(due_date)
    const diffDays = Math.ceil((d.getTime() - t.getTime()) / 86400000)
    if (d < t)        return { label: 'Overdue', color: 'var(--gray)' }
    if (diffDays <= 1) return { label: 'Tomorrow', color: 'var(--red)' }
    if (diffDays <= 3) return { label: `${diffDays}d left`, color: 'var(--red)' }
    if (diffDays <= 7) return { label: `${diffDays}d left`, color: 'var(--orange)' }
    return null
  }

  function formatDate(s: string | null): string {
    if (!s) return '—'
    const d = new Date(s)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  // Prefer the human "raw" due string, but fall back to a clean formatted date
  // when the raw value is just a machine timestamp (e.g. "2026-09-22T15:00:00").
  function prettyDue(raw: string | null, iso: string | null): string {
    if (raw && !/^\d{4}-\d{2}-\d{2}([T ]|$)/.test(raw.trim())) return raw
    return formatDate(iso ?? raw)
  }

  return (
    <div>
      {/* Filters */}
      <div className="toolbar" style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="Search bids…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="field"
          style={{ flex: '1 1 200px', minWidth: 160 }}
        />
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)} className="field">
          <option value="">All sources</option>
          {sources.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={filterDue} onChange={e => setFilterDue(e.target.value)} className="field">
          <option value="">Any due date</option>
          <option value="week">Due this week</option>
          <option value="urgent">Due in 3 days</option>
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="field">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="submitted">Submitted</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
          <option value="no_bid">No Bid</option>
        </select>
        <select value={filterRelevant} onChange={e => setFilterRelevant(e.target.value)} className="field">
          <option value="">All bids</option>
          <option value="yes">Flooring relevant</option>
          <option value="no">Not relevant</option>
        </select>
        <span style={{ color: 'var(--ink-dim)', fontSize: 12, marginLeft: 'auto', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
          {displayBids.length} bids
        </span>
      </div>

      {/* Archive toggle */}
      {archivedCount > 0 && (
        <div style={{ marginBottom: 10 }}>
          <button
            onClick={() => setShowArchived(v => !v)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--ink-dim)', fontSize: 11, fontFamily: 'var(--font-mono)',
              padding: 0, textDecoration: 'underline', textUnderlineOffset: 3,
            }}
          >
            {showArchived ? '← Back to active bids' : `Show ${archivedCount} archived (no bid / expired)`}
          </button>
        </div>
      )}

      {/* Legend */}
      <div className="legend" style={{ marginBottom: 12 }}>
        <span><span className="legend__dot" style={{ background: 'var(--red)' }} />Due &lt;3 days</span>
        <span><span className="legend__dot" style={{ background: 'var(--orange)' }} />Due this week</span>
        <span><span className="legend__dot" style={{ background: 'var(--green)' }} />Flooring relevant</span>
        <span><span style={{ color: 'var(--star)' }}>★</span> Pinned favorite</span>
      </div>

      {/* Table */}
      <div className="table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 26 }} />
              <th style={{ width: 118 }}>Bid ID</th>
              <th style={{ width: 250 }}>Title</th>
              <th style={{ width: 148 }}>Agency</th>
              <th style={{ width: 120 }}>Source</th>
              <th className="is-sortable" onClick={() => toggleSort('published_date')} style={{ width: 92 }}>
                Published{sortIndicator('published_date')}
              </th>
              <th className="is-sortable" onClick={() => toggleSort('due_date')} style={{ width: 108 }}>
                Due Date{sortIndicator('due_date')}
              </th>
              <th className="is-sortable" onClick={() => toggleSort('walk_date')} style={{ width: 96 }}>
                Job Walk{sortIndicator('walk_date')}
              </th>
              <th style={{ width: 78 }}>Status</th>
              <th style={{ width: 58 }} />
            </tr>
          </thead>
          <tbody>
            {displayBids.length === 0 ? (
              <tr>
                <td colSpan={10} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-dim)' }}>
                  No bids match your filters.
                </td>
              </tr>
            ) : displayBids.flatMap((b, i) => {
              const badge = urgencyBadge(b.due_date)
              const isExpanded = expandedId === b.bid_id
              const hasSpec = !!b.spec
              const isFav = localFavorite.get(b.bid_id) ?? b.is_favorite
              return [
                <tr
                  key={b.id}
                  onClick={() => setExpandedId(isExpanded ? null : b.bid_id)}
                  className={`row${b.is_relevant ? ' row--relevant' : ''}${isExpanded ? ' row--expanded' : ''}`}
                  style={isExpanded ? { borderBottom: 'none' } : undefined}
                >
                  <td style={{ width: 24, textAlign: 'center' }}>
                    <span
                      onClick={e => handleFavorite(e, b.bid_id)}
                      title={isFav ? 'Unpin from top' : 'Pin to top'}
                      style={{
                        cursor: 'pointer',
                        color: isFav ? 'var(--star)' : 'var(--border-strong)',
                        fontSize: 14,
                        transition: 'color 0.15s',
                        display: 'inline-block',
                      }}
                    >★</span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-dim)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    <a
                      href={`/bids/${encodeURIComponent(b.bid_id)}`}
                      onClick={e => e.stopPropagation()}
                      style={{ color: 'var(--gold-strong)', textDecoration: 'none' }}
                    >
                      {b.bid_id}
                    </a>
                  </td>
                  <td style={{ overflow: 'hidden' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{ color: 'var(--ink)', fontWeight: 500 }}>{b.title}</span>
                      {b.search_keyword && <span className="chip">{b.search_keyword}</span>}
                      {!hasSpec && <span className="chip">No docs</span>}
                      <ScorePill bid={b} spec={b.spec ?? null} />
                    </div>
                  </td>
                  <td style={{ color: 'var(--ink-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.agency || '—'}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap' }}>
                    <span style={{
                      padding: '2px 7px', borderRadius: 5,
                      background: sourceColor(b.source) + '1F',
                      color: sourceColor(b.source),
                    }}>{b.source || '—'}</span>
                  </td>
                  <td style={{ color: 'var(--ink-dim)', fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap' }}>
                    {formatDate(b.published_date)}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap' }}>
                    {badge && (
                      <div style={{
                        display: 'inline-block', padding: '1px 6px', borderRadius: 5, marginBottom: 3,
                        background: badge.color + '26', color: badge.color,
                        fontSize: 10, fontWeight: 700,
                      }}>{badge.label}</div>
                    )}
                    <div style={{ color: badge ? badge.color : 'var(--ink)' }}>
                      {prettyDue(b.due_date_raw, b.due_date)}
                    </div>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, whiteSpace: 'nowrap', color: 'var(--ink-dim)' }}>
                    {formatDate(b.spec?.walk_date ?? null)}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <StatusBadge status={b.bid_status ?? 'active'} />
                  </td>
                  <td style={{ width: 64, fontSize: 11, whiteSpace: 'nowrap', textAlign: 'right', paddingRight: 16 }}>
                    {b.url && (
                      <a href={b.url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} style={{ color: 'var(--gold-strong)', marginRight: 10 }}>↗</a>
                    )}
                    <button
                      onClick={e => showArchived ? restoreBid(e, b.bid_id) : archiveBid(e, b.bid_id)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        color: showArchived ? 'var(--green)' : 'var(--red)',
                        fontSize: 15, lineHeight: 1,
                        padding: '0 2px', opacity: 0.6,
                      }}
                      title={showArchived ? 'Restore to active' : 'Archive (no bid)'}
                    >
                      {showArchived ? '↩' : '×'}
                    </button>
                  </td>
                </tr>,
                isExpanded && (
                  <tr key={`${b.id}-detail`} className="row--expanded">
                    <td colSpan={10} style={{ padding: '0 14px 16px 14px' }}>
                      {hasSpec ? <SpecPanel spec={b.spec!} /> : (
                        <div style={{ color: 'var(--ink-dim)', fontSize: 12, fontFamily: 'var(--font-mono)', padding: '8px 0' }}>
                          No spec parsed yet. Run <code style={{ background: 'var(--surface)', padding: '1px 5px', borderRadius: 3 }}>python parser.py --bid-id={b.bid_id}</code> to extract.
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
  const cfg = result.needsReview ? verdictConfig.review : verdictConfig[result.verdict!]
  return (
    <span
      title={result.needsReview ? result.reviewReasons.map(r => r.label).join('; ') : undefined}
      style={{
        fontSize: 10, padding: '1px 6px', borderRadius: 4,
        background: cfg.bg, color: cfg.color,
        fontFamily: 'IBM Plex Mono', fontWeight: 700,
        letterSpacing: '0.04em',
      }}
    >
      {result.needsReview ? cfg.label : `${cfg.label} ${result.score}`}
    </span>
  )
}

function StatusBadge({ status }: { status: BidStatus | 'active' }) {
  const cfg: Record<string, { label: string; color: string }> = {
    active:    { label: 'Active',     color: 'var(--ink-dim)' },
    submitted: { label: 'Submitted',  color: 'var(--gold-strong)' },
    won:       { label: 'Won',        color: 'var(--green)' },
    lost:      { label: 'Lost',       color: 'var(--red)' },
    no_bid:    { label: 'No Bid',     color: '#8B8578' },
    expired:   { label: 'Expired',    color: '#A79F8D' },
  }
  const { label, color } = cfg[status] ?? cfg.active
  if (status === 'active') return null
  return (
    <span style={{
      padding: '2px 7px', borderRadius: 5, fontSize: 10,
      fontFamily: 'var(--font-mono)', fontWeight: 600,
      background: color + '1F', color,
    }}>{label}</span>
  )
}

function sourceColor(source: string | null): string {
  switch (source) {
    case 'PlanetBids': return '#A9761A'
    case 'SAM.gov':    return '#2A8A3E'
    default:           return '#8B8578'
  }
}

function SpecPanel({ spec }: { spec: BidSpec }) {
  const tri = (val: boolean | null) => val === true ? '✓' : val === false ? '✗' : '?'
  const triColor = (val: boolean | null) => val === true ? 'var(--green)' : val === false ? 'var(--red)' : 'var(--ink-dim)'

  return (
    <div style={{
      marginTop: 10,
      padding: '14px 16px',
      background: 'var(--surface)',
      borderRadius: 10,
      border: '1px solid var(--border)',
      boxShadow: 'var(--shadow-sm)',
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
      gap: '10px 20px',
      fontSize: 12,
    }}>
      {spec.summary && (
        <div style={{ gridColumn: '1 / -1', color: 'var(--ink)', marginBottom: 4, lineHeight: 1.5 }}>
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
      <div style={{ fontSize: 10, color: 'var(--ink-dim)', fontFamily: 'var(--font-mono)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ color: color || 'var(--ink)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{value}</div>
    </div>
  )
}
