'use client'

import { scoreGoNoGo, verdictConfig } from '../../lib/scoring'

type Props = {
  bid: { is_relevant: boolean; due_date: string | null }
  spec: {
    total_sqft: number | null
    prevailing_wage: boolean | null
    bid_bond: boolean | null
    walk_required: boolean | null
    dvbe_required?: boolean | null
    dbe_goal_pct?: number | null
  } | null
}

export default function GoNoGoCard({ bid, spec }: Props) {
  const result = scoreGoNoGo(bid, spec)
  const cfg = verdictConfig[result.verdict]

  return (
    <div style={{
      marginBottom: 24,
      padding: '18px 20px',
      background: 'var(--charcoal-soft)',
      borderRadius: 12,
      border: `1px solid ${cfg.color}55`,
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        {/* Score circle */}
        <div style={{
          width: 64, height: 64, borderRadius: '50%',
          border: `3px solid ${cfg.color}`,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'IBM Plex Mono', color: cfg.color, lineHeight: 1 }}>
            {result.score}
          </span>
          <span style={{ fontSize: 8, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', letterSpacing: '0.05em' }}>
            /100
          </span>
        </div>

        <div>
          <div style={{
            display: 'inline-block',
            padding: '4px 12px', borderRadius: 6,
            background: cfg.bg, color: cfg.color,
            fontSize: 13, fontFamily: 'IBM Plex Mono', fontWeight: 700,
            letterSpacing: '0.08em',
            marginBottom: 4,
          }}>
            {cfg.label}
          </div>
          <div style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono' }}>
            Go/No-Go Score{result.partial ? ' · spec not parsed — estimate only' : ''}
          </div>
        </div>

        {/* Score bar */}
        <div style={{ flex: 1, marginLeft: 8 }}>
          <div style={{ height: 6, borderRadius: 3, background: 'var(--charcoal-mid)', overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${result.score}%`,
              background: cfg.color,
              borderRadius: 3,
              transition: 'width 0.4s ease',
            }} />
          </div>
        </div>
      </div>

      {/* Factor breakdown */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {result.factors.map((f, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
            <span style={{
              fontFamily: 'IBM Plex Mono', fontSize: 11, fontWeight: 700,
              color: f.delta > 0 ? 'var(--green)' : f.delta < 0 ? 'var(--red)' : 'var(--gray)',
              width: 36, textAlign: 'right', flexShrink: 0,
            }}>
              {f.delta > 0 ? `+${f.delta}` : f.delta}
            </span>
            <span style={{ fontSize: 12, fontFamily: 'IBM Plex Mono', color: 'var(--white)', flexShrink: 0 }}>
              {f.label}
            </span>
            <span style={{ fontSize: 11, color: 'var(--gray)', lineHeight: 1.4 }}>
              {f.note}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
