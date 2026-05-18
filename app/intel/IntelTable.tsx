'use client'

import { Fragment, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { IntelBid, IntelSubmission } from './page'

type Props = {
  bids: IntelBid[]
  agencies: string[]
}

function fmtAmount(v: number | null): string {
  if (v == null) return '—'
  return '$' + v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtDate(s: string | null): string {
  if (!s) return '—'
  try {
    return new Date(s + 'T12:00:00').toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    })
  } catch {
    return s
  }
}

function gapColor(pct: number): string {
  if (pct < 5) return 'var(--green)'
  if (pct < 15) return 'var(--orange)'
  return 'var(--red)'
}

function SubmissionRows({ submissions, winnerAmount }: {
  submissions: IntelSubmission[]
  winnerAmount: number | null
}) {
  return (
    <tr>
      <td colSpan={6} style={{ padding: 0, background: 'var(--charcoal)' }}>
        <div style={{ padding: '0 16px 16px 56px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr>
                {['Rank', 'Vendor', 'Bid Amount', 'Gap from Winner'].map(h => (
                  <th key={h} style={{
                    padding: '6px 12px', textAlign: 'left',
                    color: 'var(--gray)', fontWeight: 500, fontSize: 11,
                    fontFamily: 'IBM Plex Mono', borderBottom: '1px solid var(--charcoal-mid)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {submissions.map((s, i) => {
                const vendorName = s.vendor?.canonical_name ?? s.raw_vendor_name
                const gapAmt = (winnerAmount != null && s.bid_amount != null && !s.is_winner)
                  ? s.bid_amount - winnerAmount
                  : null
                const gapPct = (gapAmt != null && winnerAmount != null && winnerAmount > 0)
                  ? (gapAmt / winnerAmount) * 100
                  : null

                return (
                  <tr key={s.id ?? i} style={{
                    borderBottom: '1px solid var(--charcoal-mid)',
                    background: s.is_winner ? 'rgba(200,146,42,0.08)' : 'transparent',
                  }}>
                    <td style={{ padding: '8px 12px', fontFamily: 'IBM Plex Mono', color: 'var(--gray)' }}>
                      {s.is_winner
                        ? <span style={{ color: 'var(--gold)', fontWeight: 600 }}>★ 1</span>
                        : (s.rank ?? i + 1)}
                    </td>
                    <td style={{ padding: '8px 12px', fontWeight: s.is_winner ? 600 : 400 }}>
                      {vendorName}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'IBM Plex Mono', color: s.is_winner ? 'var(--gold)' : 'var(--white)' }}>
                      {fmtAmount(s.bid_amount)}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'IBM Plex Mono' }}>
                      {s.is_winner
                        ? <span style={{ color: 'var(--gray)' }}>—</span>
                        : gapAmt != null && gapPct != null
                          ? <span style={{ color: gapColor(gapPct) }}>
                              +{fmtAmount(gapAmt)} (+{gapPct.toFixed(1)}%)
                            </span>
                          : <span style={{ color: 'var(--gray)' }}>—</span>
                      }
                    </td>
                  </tr>
                )
              })}
              {submissions.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ padding: '12px', color: 'var(--gray)', textAlign: 'center' }}>
                    No submission data captured
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </td>
    </tr>
  )
}

export default function IntelTable({ bids, agencies }: Props) {
  const router = useRouter()
  const [search, setSearch]     = useState('')
  const [agency, setAgency]     = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState<Set<string>>(new Set())

  async function deleteRow(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm('Remove this bid from intel?')) return
    setDeleting(prev => new Set(prev).add(id))
    try {
      const res = await fetch(`/api/intel/${id}`, { method: 'DELETE' })
      const json = await res.json()
      if (!res.ok) {
        alert(`Delete failed: ${json.error ?? res.status}`)
        return
      }
      router.refresh()
    } finally {
      setDeleting(prev => { const s = new Set(prev); s.delete(id); return s })
    }
  }

  const filtered = bids.filter(b => {
    if (agency && b.agency !== agency) return false
    if (search) {
      const q = search.toLowerCase()
      if (
        !b.title.toLowerCase().includes(q) &&
        !(b.agency ?? '').toLowerCase().includes(q) &&
        !(b.winner_vendor?.canonical_name ?? '').toLowerCase().includes(q)
      ) return false
    }
    return true
  })

  function toggle(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
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

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Search title, agency, winner…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ ...inputStyle, flex: 1, minWidth: 220 }}
        />
        <select
          value={agency}
          onChange={e => setAgency(e.target.value)}
          style={{ ...inputStyle, minWidth: 180 }}
        >
          <option value="">All agencies</option>
          {agencies.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <div style={{
          padding: '7px 12px', borderRadius: 8,
          background: 'var(--charcoal-soft)', border: '1px solid var(--charcoal-mid)',
          fontSize: 12, color: 'var(--gray)', fontFamily: 'IBM Plex Mono',
          display: 'flex', alignItems: 'center',
        }}>
          {filtered.length} of {bids.length}
        </div>
      </div>

      {/* Table */}
      <div style={{
        background: 'var(--charcoal-soft)', borderRadius: 12,
        border: '1px solid var(--charcoal-mid)', overflow: 'hidden',
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--charcoal)' }}>
              <th style={{ width: 32 }} />
              {['Agency', 'Title', 'Winner', 'Winning Bid', '# Bidders', 'Award Date', ''].map(h => (
                <th key={h} style={{
                  padding: '10px 14px', textAlign: 'left',
                  color: 'var(--gray)', fontWeight: 500, fontSize: 11,
                  fontFamily: 'IBM Plex Mono', whiteSpace: 'nowrap',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((bid, i) => {
              const isOpen = expanded.has(bid.id)
              const winnerName = bid.winner_vendor?.canonical_name
                ?? bid.submissions.find(s => s.is_winner)?.vendor?.canonical_name
                ?? bid.submissions.find(s => s.rank === 1)?.raw_vendor_name
                ?? '—'

              return (
                <Fragment key={bid.id}>
                  <tr
                    onClick={() => toggle(bid.id)}
                    style={{
                      borderTop: i > 0 ? '1px solid var(--charcoal-mid)' : undefined,
                      cursor: 'pointer',
                      background: isOpen ? 'var(--charcoal)' : i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                    }}
                  >
                    <td style={{ paddingLeft: 16, color: 'var(--gray)', fontSize: 11 }}>
                      {isOpen ? '▾' : '▸'}
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--gray)', fontSize: 12 }}>
                      {bid.agency ?? '—'}
                    </td>
                    <td style={{ padding: '10px 14px', maxWidth: 320 }}>
                      <div style={{
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {bid.title}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px', maxWidth: 220 }}>
                      <div style={{
                        fontWeight: 500,
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}>
                        {winnerName}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px', fontFamily: 'IBM Plex Mono', color: 'var(--gold)' }}>
                      {fmtAmount(bid.winner_amount)}
                    </td>
                    <td style={{ padding: '10px 14px', fontFamily: 'IBM Plex Mono', color: 'var(--gray)' }}>
                      {bid.total_bidders ?? '—'}
                    </td>
                    <td style={{ padding: '10px 14px', fontFamily: 'IBM Plex Mono', fontSize: 12, color: 'var(--gray)' }}>
                      {fmtDate(bid.awarded_at)}
                    </td>
                    <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }} onClick={e => e.stopPropagation()}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        {bid.url && (
                          <a href={bid.url} target="_blank" rel="noopener noreferrer"
                            style={{ color: 'var(--gold-light)', fontSize: 11, fontFamily: 'IBM Plex Mono', textDecoration: 'none' }}>
                            view ↗
                          </a>
                        )}
                        <button
                          onClick={e => deleteRow(bid.id, e)}
                          disabled={deleting.has(bid.id)}
                          style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--gray)', fontSize: 13, padding: '2px 4px',
                            opacity: deleting.has(bid.id) ? 0.4 : 1,
                            lineHeight: 1,
                          }}
                          title="Remove from intel"
                        >
                          ✕
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <SubmissionRows
                      submissions={bid.submissions}
                      winnerAmount={bid.winner_amount}
                    />
                  )}
                </Fragment>
              )
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: 'var(--gray)' }}>
                  No results for current filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
