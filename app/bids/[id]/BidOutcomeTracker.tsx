'use client'

import { useState, useTransition } from 'react'
import { updateBidStatus, type BidStatus } from '../../actions/bids'

type Props = {
  bidId: string
  initialStatus: BidStatus
  initialSubmitted: number | null
  initialAward: number | null
  estimateTotal: number | null
}

const STATUSES: { key: BidStatus; label: string; color: string; bg: string }[] = [
  { key: 'active',    label: 'Active',    color: 'var(--ink-dim)',    bg: 'var(--surface-sunken)' },
  { key: 'submitted', label: 'Submitted', color: 'var(--gold-strong)', bg: 'var(--gold-tint)' },
  { key: 'won',       label: 'Won',       color: 'var(--green)',      bg: 'var(--green-tint)' },
  { key: 'lost',      label: 'Lost',      color: 'var(--red)',        bg: 'var(--red-tint)' },
  { key: 'no_bid',    label: 'No Bid',    color: 'var(--ink-faint)',  bg: 'var(--surface-sunken)' },
]

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 })

export default function BidOutcomeTracker({ bidId, initialStatus, initialSubmitted, initialAward, estimateTotal }: Props) {
  const [status, setStatus]      = useState<BidStatus>(initialStatus)
  const [submitted, setSubmitted] = useState<string>(initialSubmitted ? String(initialSubmitted) : (estimateTotal ? String(estimateTotal) : ''))
  const [award, setAward]         = useState<string>(initialAward ? String(initialAward) : '')
  const [msg, setMsg]             = useState<string | null>(null)
  const [pending, startTransition] = useTransition()

  async function save(newStatus: BidStatus) {
    setStatus(newStatus)
    startTransition(async () => {
      const sub = submitted ? parseInt(submitted.replace(/\D/g, ''), 10) : null
      const aw  = award    ? parseInt(award.replace(/\D/g, ''),    10) : null
      const res = await updateBidStatus(bidId, newStatus, sub, aw)
      if (res.ok) {
        setMsg('Saved')
        setTimeout(() => setMsg(null), 2500)
      } else {
        setMsg(`Error: ${res.error}`)
      }
    })
  }

  const showAmounts = status === 'submitted' || status === 'won' || status === 'lost'
  const currentStatus = STATUSES.find(s => s.key === status) ?? STATUSES[0]

  const inputStyle: React.CSSProperties = {
    background: 'var(--surface)',
    border: '1px solid var(--border-strong)',
    borderRadius: 9,
    color: 'var(--ink)',
    padding: '7px 10px',
    fontSize: 13,
    fontFamily: 'var(--font-mono)',
    width: 140,
    outline: 'none',
  }

  return (
    <div
      className="card"
      style={{
        marginTop: 24,
        padding: '20px 22px',
        boxShadow: `inset 3px 0 0 ${currentStatus.color}, var(--shadow-sm)`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--ink-dim)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Bid Outcome
        </span>
        {msg && (
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: msg.startsWith('Error') ? 'var(--red)' : 'var(--green)' }}>
            {msg}
          </span>
        )}
      </div>

      {/* Status buttons */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: showAmounts ? 16 : 0 }}>
        {STATUSES.map(s => (
          <button
            key={s.key}
            disabled={pending}
            onClick={() => save(s.key)}
            style={{
              padding: '6px 14px',
              borderRadius: 8,
              border: `1px solid ${status === s.key ? s.color : 'var(--border-strong)'}`,
              background: status === s.key ? s.bg : 'transparent',
              color: status === s.key ? s.color : 'var(--ink-dim)',
              fontSize: 12,
              fontFamily: 'var(--font-mono)',
              fontWeight: status === s.key ? 600 : 400,
              cursor: pending ? 'not-allowed' : 'pointer',
              opacity: pending ? 0.6 : 1,
              transition: 'all 0.15s',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Amount fields */}
      {showAmounts && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 4 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--ink-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Our Bid Amount
            </span>
            <input
              type="text"
              value={submitted}
              onChange={e => setSubmitted(e.target.value)}
              onBlur={() => save(status)}
              placeholder={estimateTotal ? money(estimateTotal) : '$0'}
              style={inputStyle}
            />
          </label>
          {(status === 'won' || status === 'lost') && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--ink-dim)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {status === 'won' ? 'Award Amount' : 'Winning Bid'}
              </span>
              <input
                type="text"
                value={award}
                onChange={e => setAward(e.target.value)}
                onBlur={() => save(status)}
                placeholder="$0"
                style={inputStyle}
              />
            </label>
          )}
          {status === 'lost' && award && submitted && parseInt(award) < parseInt(submitted) && (
            <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 7 }}>
              <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--red)' }}>
                -{money(parseInt(submitted.replace(/\D/g,'')) - parseInt(award.replace(/\D/g,'')))} gap
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
