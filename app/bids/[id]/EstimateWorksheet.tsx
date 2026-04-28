'use client'

import { useState, useMemo, useTransition } from 'react'
import { saveEstimate, recalculateEstimate, type LineItem } from '../../actions/estimates'
import { sendRFQEmails } from '../../actions/rfq'
import type { Rates } from '../../actions/settings'

type Spec = {
  flooring_types: string[] | null
  total_sqft: number | null
  prevailing_wage: boolean | null
} | null

type Estimate = {
  id: string
  line_items: LineItem[] | null
  selected_markup: number | null
  status: string | null
  is_stale: boolean | null
  rates_snapshot: Omit<Rates, 'updatedAt'> | null
  rates_version: string | null
} | null

type Props = {
  bidId: string
  spec: Spec
  estimate: Estimate
  rates: Rates
  isStale: boolean
}

function newId() {
  return Math.random().toString(36).slice(2)
}

function buildDefaultLines(spec: Spec, rates: Rates): LineItem[] {
  const usesPrevailing = spec?.prevailing_wage === true
  const sqft = spec?.total_sqft ?? 0
  const types = spec?.flooring_types ?? []

  const laborLines: LineItem[] = [
    {
      id: newId(), type: 'labor',
      description: usesPrevailing ? 'Journeyman Prevailing Wage' : 'Journeyman Standard',
      qty: 0, unit: 'hrs',
      rate: usesPrevailing ? rates.prevailing : rates.standard,
      total: 0,
      rate_key: usesPrevailing ? 'prevailing' : 'standard',
    },
    {
      id: newId(), type: 'labor',
      description: 'Apprentice',
      qty: 0, unit: 'hrs',
      rate: rates.apprentice, total: 0,
      rate_key: 'apprentice',
    },
  ]

  const materialLines: LineItem[] = types.length > 0
    ? types.map(t => ({
        id: newId(), type: 'material' as const,
        description: t.charAt(0).toUpperCase() + t.slice(1),
        qty: types.length > 1 ? Math.round(sqft / types.length) : sqft,
        unit: 'SF', rate: 0, total: 0, rate_key: null,
      }))
    : [{
        id: newId(), type: 'material' as const,
        description: 'Materials (rep quote)',
        qty: 0, unit: 'SF', rate: 0, total: 0, rate_key: null,
      }]

  return [...laborLines, ...materialLines]
}

const fmt = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 })

export default function EstimateWorksheet({ bidId, spec, estimate, rates, isStale }: Props) {
  const savedLines = estimate?.line_items
  const [lines, setLines] = useState<LineItem[]>(
    savedLines?.length ? savedLines : buildDefaultLines(spec, rates)
  )
  const [markup, setMarkup] = useState<25 | 30>((estimate?.selected_markup as 25 | 30) ?? 30)
  const [isPending, startTransition] = useTransition()
  const [savedMsg, setSavedMsg] = useState<string | null>(null)
  const [rfqMsg, setRfqMsg] = useState<string | null>(null)
  const [rfqTo, setRfqTo] = useState('')
  const [rfqCc, setRfqCc] = useState('')
  const [rfqHover, setRfqHover] = useState(false)
  const [status, setStatus] = useState(estimate?.status ?? 'draft')

  const subtotal = useMemo(() => lines.reduce((s, l) => s + l.total, 0), [lines])
  const bid30 = subtotal * 1.30
  const bid25 = subtotal * 1.25

  function updateLine(id: string, field: keyof LineItem, raw: string) {
    setLines(prev => prev.map(l => {
      if (l.id !== id) return l
      const val = parseFloat(raw) || 0
      if (field === 'qty')  return { ...l, qty:  val, total: val * l.rate }
      if (field === 'rate') return { ...l, rate: val, total: l.qty * val }
      return { ...l, [field]: raw }
    }))
  }

  function addLine(type: 'labor' | 'material') {
    setLines(prev => [...prev, {
      id: newId(), type,
      description: type === 'labor' ? 'Journeyman Standard' : 'Material',
      qty: 0, unit: type === 'labor' ? 'hrs' : 'SF',
      rate: type === 'labor' ? rates.standard : 0,
      total: 0,
      rate_key: type === 'labor' ? 'standard' : null,
    }])
  }

  function removeLine(id: string) {
    setLines(prev => prev.filter(l => l.id !== id))
  }

  function handleSave(nextStatus: 'draft' | 'approved') {
    startTransition(async () => {
      await saveEstimate(bidId, lines, markup, {
        standard:   rates.standard,
        prevailing: rates.prevailing,
        apprentice: rates.apprentice,
      }, nextStatus)
      setStatus(nextStatus)
      setSavedMsg(nextStatus === 'approved' ? '✓ Approved' : '✓ Saved')
      setTimeout(() => setSavedMsg(null), 3000)
    })
  }

  function handleSendRFQ() {
    startTransition(async () => {
      await saveEstimate(bidId, lines, markup, {
        standard: rates.standard, prevailing: rates.prevailing, apprentice: rates.apprentice,
      }, 'draft')
      const result = await sendRFQEmails(bidId, rfqTo, rfqCc)
      setRfqMsg(result.ok ? `✓ RFQ sent to ${rfqTo}` : `⚠ ${result.error}`)
      setTimeout(() => setRfqMsg(null), 5000)
    })
  }

  function handleRecalculate() {
    startTransition(async () => {
      await recalculateEstimate(bidId, {
        standard:   rates.standard,
        prevailing: rates.prevailing,
        apprentice: rates.apprentice,
      })
      // Reload page to get updated data from server
      window.location.reload()
    })
  }

  const isApproved = status === 'approved'
  const laborLines = lines.filter(l => l.type === 'labor')
  const materialLines = lines.filter(l => l.type === 'material')

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700 }}>Estimate Worksheet</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {status === 'approved' && (
            <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono', color: 'var(--green)', padding: '3px 8px', background: '#30D15822', borderRadius: 4 }}>
              ✓ Approved
            </span>
          )}
          {status === 'draft' && estimate && (
            <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', padding: '3px 8px', background: 'var(--charcoal-soft)', borderRadius: 4 }}>
              Draft
            </span>
          )}
        </div>
      </div>

      {/* Stale banner */}
      {isStale && (
        <div style={{
          marginBottom: 16, padding: '12px 16px',
          background: '#FF9F0A18', border: '1px solid var(--orange)',
          borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: 13, color: 'var(--orange)' }}>
            ⚠ Labor rates were updated since this estimate was created.
          </span>
          <button
            onClick={handleRecalculate}
            disabled={isPending}
            style={{
              background: 'var(--orange)', color: 'var(--charcoal)',
              border: 'none', borderRadius: 6, padding: '6px 14px',
              fontSize: 12, fontWeight: 700, cursor: 'pointer',
            }}
          >
            Recalculate
          </button>
        </div>
      )}

      {/* Labor lines */}
      <SectionHeader label="Labor" />
      <LineTable
        lines={laborLines}
        disabled={isApproved}
        onUpdate={updateLine}
        onRemove={removeLine}
        showRateKey
      />
      {!isApproved && (
        <AddLineButton onClick={() => addLine('labor')} label="+ Add labor line" />
      )}

      {/* Material lines */}
      <SectionHeader label="Materials" note="Enter costs from rep quotes" />
      <LineTable
        lines={materialLines}
        disabled={isApproved}
        onUpdate={updateLine}
        onRemove={removeLine}
      />
      {!isApproved && (
        <AddLineButton onClick={() => addLine('material')} label="+ Add material line" />
      )}

      {/* Summary */}
      <div style={{
        marginTop: 24, background: 'var(--charcoal-soft)',
        borderRadius: 10, border: '1px solid var(--charcoal-mid)',
        padding: '20px 24px',
      }}>
        <SummaryRow label="Subtotal" value={fmt(subtotal)} bold />
        <div style={{ borderTop: '1px solid var(--charcoal-mid)', margin: '12px 0' }} />

        {/* 30% markup */}
        <div
          onClick={() => !isApproved && setMarkup(30)}
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 14px', borderRadius: 8, marginBottom: 8,
            background: markup === 30 ? '#30D15815' : 'transparent',
            border: `1px solid ${markup === 30 ? 'var(--green)' : 'var(--charcoal-mid)'}`,
            cursor: isApproved ? 'default' : 'pointer',
          }}
        >
          <span style={{ fontSize: 13, fontFamily: 'IBM Plex Mono', color: 'var(--gray)' }}>
            {markup === 30 ? '✓ ' : ''}30% markup
          </span>
          <span style={{ fontSize: 18, fontWeight: 700, fontFamily: 'IBM Plex Mono', color: markup === 30 ? 'var(--green)' : 'var(--white)' }}>
            {fmt(bid30)}
          </span>
        </div>

        {/* 25% markup */}
        <div
          onClick={() => !isApproved && setMarkup(25)}
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 14px', borderRadius: 8,
            background: markup === 25 ? '#C8922A15' : 'transparent',
            border: `1px solid ${markup === 25 ? 'var(--gold)' : 'var(--charcoal-mid)'}`,
            cursor: isApproved ? 'default' : 'pointer',
          }}
        >
          <span style={{ fontSize: 13, fontFamily: 'IBM Plex Mono', color: 'var(--gray)' }}>
            {markup === 25 ? '✓ ' : ''}25% markup
          </span>
          <span style={{ fontSize: 18, fontWeight: 700, fontFamily: 'IBM Plex Mono', color: markup === 25 ? 'var(--gold)' : 'var(--white)' }}>
            {fmt(bid25)}
          </span>
        </div>

        {markup === 25 && (
          <p style={{ marginTop: 8, fontSize: 11, color: 'var(--orange)', fontFamily: 'IBM Plex Mono' }}>
            ⚠ 25% markup — owner approval required before submitting
          </p>
        )}
      </div>

      {/* RFQ email fields */}
      {!isApproved && materialLines.some(l => l.qty > 0) && (
        <div style={{ marginTop: 20, padding: '14px 16px', background: 'var(--charcoal-soft)', borderRadius: 8, border: '1px solid var(--charcoal-mid)' }}>
          <div style={{ fontSize: 10, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
            RFQ Recipients
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ fontSize: 10, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', display: 'block', marginBottom: 4 }}>To (rep email)</label>
              <input
                type="email"
                placeholder="rep@supplier.com"
                value={rfqTo}
                onChange={e => setRfqTo(e.target.value)}
                style={{ ...rfqInputStyle, width: '100%' }}
              />
            </div>
            <div style={{ flex: 1, minWidth: 200 }}>
              <label style={{ fontSize: 10, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', display: 'block', marginBottom: 4 }}>
                Additional CC <span style={{ opacity: 0.5 }}>(optional)</span>
              </label>
              <input
                type="email"
                placeholder="another@email.com"
                value={rfqCc}
                onChange={e => setRfqCc(e.target.value)}
                style={{ ...rfqInputStyle, width: '100%' }}
              />
              <div style={{ fontSize: 10, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', marginTop: 4, opacity: 0.6 }}>
                Joanne always CC'd automatically
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!isApproved && (
        <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            onClick={() => handleSave('draft')}
            disabled={isPending}
            style={{
              background: savedMsg ? 'var(--green)' : 'var(--charcoal-soft)',
              color: savedMsg ? 'var(--charcoal)' : 'var(--white)',
              border: '1px solid var(--charcoal-mid)',
              borderRadius: 8, padding: '10px 20px', fontSize: 13,
              fontWeight: 600, cursor: isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {savedMsg ?? (isPending ? 'Saving…' : 'Save Draft')}
          </button>
          <button
            onClick={() => handleSave('approved')}
            disabled={isPending}
            style={{
              background: 'var(--gold)', color: 'var(--charcoal)',
              border: 'none', borderRadius: 8, padding: '10px 20px',
              fontSize: 13, fontWeight: 700, cursor: isPending ? 'not-allowed' : 'pointer',
            }}
          >
            Approve →
          </button>
          {materialLines.some(l => l.qty > 0) && (() => {
            const disabled = isPending || !rfqTo.trim()
            const isSuccess = rfqMsg?.startsWith('✓')
            const isError   = rfqMsg?.startsWith('⚠')
            return (
              <button
                onClick={handleSendRFQ}
                disabled={disabled}
                onMouseEnter={() => setRfqHover(true)}
                onMouseLeave={() => setRfqHover(false)}
                style={{
                  borderRadius: 8, padding: '10px 20px', fontSize: 13,
                  fontWeight: 700, fontFamily: 'IBM Plex Mono',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  transition: 'background 0.15s, border-color 0.15s',
                  ...(isSuccess ? {
                    background: 'var(--green)', color: 'var(--charcoal)', border: '1px solid var(--green)',
                  } : isError ? {
                    background: '#FF453A18', color: 'var(--red)', border: '1px solid var(--red)',
                  } : disabled ? {
                    background: 'transparent', color: '#555', border: '1px solid #333',
                  } : {
                    background: rfqHover ? '#C8922A28' : '#C8922A14',
                    color: 'var(--gold)',
                    border: '1px solid var(--gold)',
                  }),
                }}
              >
                {isPending ? 'Sending…' : (rfqMsg ?? '↑ Send RFQ')}
              </button>
            )
          })()}
        </div>
      )}
    </div>
  )
}

function SectionHeader({ label, note }: { label: string; note?: string }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', marginTop: 24, marginBottom: 8 }}>
      <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--gray)' }}>
        {label}
      </span>
      {note && <span style={{ fontSize: 11, color: 'var(--gray)', opacity: 0.6 }}>{note}</span>}
    </div>
  )
}

function SummaryRow({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
      <span style={{ fontSize: 13, color: 'var(--gray)', fontFamily: 'IBM Plex Mono' }}>{label}</span>
      <span style={{ fontSize: bold ? 16 : 13, fontFamily: 'IBM Plex Mono', fontWeight: bold ? 700 : 400, color: 'var(--white)' }}>{value}</span>
    </div>
  )
}

function AddLineButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} style={{
      marginTop: 8, background: 'transparent', border: '1px dashed var(--charcoal-mid)',
      borderRadius: 6, padding: '6px 14px', fontSize: 12, color: 'var(--gray)',
      cursor: 'pointer', fontFamily: 'IBM Plex Mono',
    }}>
      {label}
    </button>
  )
}

function LineTable({
  lines, disabled, onUpdate, onRemove, showRateKey,
}: {
  lines: LineItem[]
  disabled: boolean
  onUpdate: (id: string, field: keyof LineItem, val: string) => void
  onRemove: (id: string) => void
  showRateKey?: boolean
}) {
  if (lines.length === 0) return null

  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: '1px solid var(--charcoal-mid)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ background: 'var(--charcoal-soft)' }}>
            {['Description', 'Qty', 'Unit', 'Rate', 'Total', ''].map(h => (
              <th key={h} style={{
                padding: '8px 12px', textAlign: h === 'Total' ? 'right' : 'left',
                fontSize: 10, fontWeight: 600, color: 'var(--gray)',
                fontFamily: 'IBM Plex Mono', textTransform: 'uppercase', letterSpacing: '0.05em',
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={l.id} style={{ background: i % 2 === 0 ? 'var(--charcoal)' : 'var(--charcoal-soft)', borderTop: '1px solid var(--charcoal-mid)' }}>
              <td style={{ padding: '8px 12px' }}>
                {disabled
                  ? <span style={{ fontSize: 13, color: 'var(--white)' }}>{l.description}</span>
                  : <input
                      value={l.description}
                      onChange={e => onUpdate(l.id, 'description', e.target.value)}
                      style={cellInput}
                    />
                }
              </td>
              <td style={{ padding: '8px 12px', width: 80 }}>
                {disabled
                  ? <span style={monoCell}>{l.qty}</span>
                  : <input type="number" value={l.qty || ''} placeholder="0"
                      onChange={e => onUpdate(l.id, 'qty', e.target.value)}
                      style={{ ...cellInput, width: 70, fontFamily: 'IBM Plex Mono' }}
                    />
                }
              </td>
              <td style={{ padding: '8px 12px', width: 70 }}>
                {disabled
                  ? <span style={monoCell}>{l.unit}</span>
                  : <input value={l.unit}
                      onChange={e => onUpdate(l.id, 'unit', e.target.value)}
                      style={{ ...cellInput, width: 60, fontFamily: 'IBM Plex Mono' }}
                    />
                }
              </td>
              <td style={{ padding: '8px 12px', width: 100 }}>
                {disabled || (l.type === 'labor')
                  ? <span style={{ ...monoCell, color: l.type === 'labor' ? 'var(--gray)' : 'var(--white)' }}>
                      ${l.rate}/hr
                      {l.type === 'labor' && <span style={{ fontSize: 9, color: 'var(--charcoal-mid)', marginLeft: 4 }}>fixed</span>}
                    </span>
                  : <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                      <span style={{ color: 'var(--gray)', fontFamily: 'IBM Plex Mono', fontSize: 12 }}>$</span>
                      <input type="number" value={l.rate || ''} placeholder="0"
                        onChange={e => onUpdate(l.id, 'rate', e.target.value)}
                        style={{ ...cellInput, width: 70, fontFamily: 'IBM Plex Mono' }}
                      />
                    </div>
                }
                {l.type === 'material' && l.rate === 0 && (
                  <div style={{ fontSize: 10, color: 'var(--orange)', fontFamily: 'IBM Plex Mono', marginTop: 2 }}>
                    Pending quote
                  </div>
                )}
              </td>
              <td style={{ padding: '8px 12px', textAlign: 'right', width: 100 }}>
                <span style={{ fontFamily: 'IBM Plex Mono', fontSize: 13, fontWeight: 600, color: 'var(--white)' }}>
                  {l.total > 0 ? '$' + l.total.toLocaleString() : '—'}
                </span>
              </td>
              <td style={{ padding: '8px 12px', width: 30 }}>
                {!disabled && (
                  <button onClick={() => onRemove(l.id)} style={{
                    background: 'transparent', border: 'none', color: 'var(--gray)',
                    cursor: 'pointer', fontSize: 14, padding: 2,
                  }}>×</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const cellInput: React.CSSProperties = {
  background: 'transparent', border: '1px solid transparent',
  borderRadius: 4, color: 'var(--white)', padding: '4px 6px',
  fontSize: 13, outline: 'none', width: '100%',
  transition: 'border-color 0.15s',
}

const monoCell: React.CSSProperties = {
  fontFamily: 'IBM Plex Mono', fontSize: 12, color: 'var(--white)',
}

const rfqInputStyle: React.CSSProperties = {
  background: 'var(--charcoal)', border: '1px solid var(--charcoal-mid)',
  borderRadius: 6, color: 'var(--white)', padding: '7px 10px',
  fontSize: 12, outline: 'none', fontFamily: 'IBM Plex Mono', boxSizing: 'border-box',
}
