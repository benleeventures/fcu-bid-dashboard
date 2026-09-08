'use client'

import { scoreGoNoGo, verdictConfig } from '../../lib/scoring'

type Props = {
  bid: { due_date: string | null; county?: string | null; geo_status?: string | null }
  spec: {
    flooring_is_primary?: boolean | null
    award_method?: string | null
    project_city?: string | null
  } | null
  bidId: string
}

const CHECKLIST: { code: string; label: string }[] = [
  { code: 'no_docs', label: 'Bid documents parsed' },
  { code: 'no_location', label: 'Job location identified' },
  { code: 'no_due_date', label: 'Bid due date on file' },
  { code: 'no_scope_read', label: 'Scope assessed by parser' },
]

export default function GoNoGoCard({ bid, spec, bidId }: Props) {
  const result = scoreGoNoGo(bid, spec)
  const cfg = result.needsReview ? verdictConfig.review : verdictConfig[result.verdict!]
  const missing = new Set(result.reviewReasons.map(r => r.code))

  return (
    <div style={{
      marginBottom: 24,
      padding: '18px 20px',
      background: 'var(--charcoal-soft)',
      borderRadius: 12,
      border: `1px solid ${cfg.color}55`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
        {!result.needsReview && (
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
        )}

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
            {result.needsReview ? 'Needs a human — missing inputs below' : 'Winnability score'}
          </div>
        </div>

        {!result.needsReview && (
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
        )}
      </div>

      {result.needsReview ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {CHECKLIST.map(item => {
            // no_docs blocks everything downstream from being assessable
            const isMissing = missing.has(item.code) || (missing.has('no_docs') && item.code !== 'no_docs')
            return (
              <div key={item.code} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{
                  fontFamily: 'IBM Plex Mono', fontSize: 12, fontWeight: 700,
                  color: isMissing ? 'var(--red)' : 'var(--green)',
                  width: 14, textAlign: 'center', flexShrink: 0,
                }}>
                  {isMissing ? '✕' : '✓'}
                </span>
                <span style={{ fontSize: 12, color: isMissing ? 'var(--white)' : 'var(--gray)' }}>
                  {item.label}
                </span>
              </div>
            )
          })}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {result.factors.map((f, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
              <span style={{ fontSize: 12, fontFamily: 'IBM Plex Mono', color: 'var(--white)', width: 96, flexShrink: 0 }}>
                {f.label}
              </span>
              <span style={{ fontSize: 11, color: 'var(--gray)', lineHeight: 1.4 }}>
                {f.detail}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 12, fontSize: 10, color: 'var(--gray)', fontFamily: 'IBM Plex Mono' }}>
        {result.needsReview
          ? <>Run <code style={{ background: 'var(--charcoal-mid)', padding: '1px 5px', borderRadius: 3 }}>python parser.py --save {bidId} &apos;…&apos;</code> to fill the gaps</>
          : 'Scoring method → bid-scanner/docs/scoring.md'}
      </div>
    </div>
  )
}
