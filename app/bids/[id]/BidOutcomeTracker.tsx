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
  { key: 'active',    label: 'Active',     color: 'var(--gray)',       bg: 'var(--charcoal-soft)' },
  { key: 'submitted', label: 'Submitted',  color: 'var(--gold)',       bg: '#C8922A22' },
  { key: 'won',       label: 'Won',        color: 'var(--green)',      bg: '#30D15822' },
  { key: 'lost',      label: 'Lost',       color: 'var(--red)',        bg: '#FF453A22' },
  { key: 'no_bid',    label: 'No Bid',     color: '#636366',           bg: 'var(--charcoal-soft)' },
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

  return (
    <div style={{
      marginTop: 28,
      padding: '18px 20px',
      background: 'var(--charcoal-soft)',
      borderRadius: 12,
      border: `1px solid ${currentStatus.color}44`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
          Bid Outcome
        </span>
        {msg && (
          <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono', color: msg.startsWith('Error') ? 'var(--red)' : 'var(--green)' }}>
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
              border: `1px solid ${status === s.key ? s.color : 'var(--charcoal-mid)'}`,
              background: status === s.key ? s.bg : 'transparent',
              color: status === s.key ? s.color : 'var(--gray)',
              fontSize: 12,
              fontFamily: 'IBM Plex Mono',
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
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span style={{ fontSize: 10, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Our Bid Amount
            </span>
            <input
              type="text"
              value={submitted}
              onChange={e => setSubmitted(e.target.value)}
              onBlur={() => save(status)}
              placeholder={estimateTotal ? money(estimateTotal) : '$0'}
              style={{
                background: 'var(--charcoal)',
                border: '1px solid var(--charcoal-mid)',
                borderRadius: 6,
                color: 'var(--white)',
                padding: '6px 10px',
                fontSize: 13,
                fontFamily: 'IBM Plex Mono',
                width: 140,
                outline: 'none',
              }}
            />
          </label>
          {(status === 'won' || status === 'lost') && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 10, fontFamily: 'IBM Plex Mono', color: 'var(--gray)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {status === 'won' ? 'Award Amount' : 'Winning Bid'}
              </span>
              <input
                type="text"
                value={award}
                onChange={e => setAward(e.target.value)}
                onBlur={() => save(status)}
                placeholder="$0"
                style={{
                  background: 'var(--charcoal)',
                  border: '1px solid var(--charcoal-mid)',
                  borderRadius: 6,
                  color: 'var(--white)',
                  padding: '6px 10px',
                  fontSize: 13,
                  fontFamily: 'IBM Plex Mono',
                  width: 140,
                  outline: 'none',
                }}
              />
            </label>
          )}
          {status === 'lost' && award && submitted && parseInt(award) < parseInt(submitted) && (
            <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 7 }}>
              <span style={{ fontSize: 11, fontFamily: 'IBM Plex Mono', color: 'var(--red)' }}>
                -{money(parseInt(submitted.replace(/\D/g,'')) - parseInt(award.replace(/\D/g,'')))} gap
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
