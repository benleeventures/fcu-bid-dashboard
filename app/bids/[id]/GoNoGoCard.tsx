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
    <div
      className="card"
      style={{
        marginBottom: 24,
        padding: '20px 22px',
        boxShadow: `inset 3px 0 0 ${cfg.color}, var(--shadow-sm)`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
        {!result.needsReview && (
          <div style={{
            width: 64, height: 64, borderRadius: '50%',
            border: `3px solid ${cfg.color}`,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: cfg.color, lineHeight: 1 }}>
              {result.score}
            </span>
            <span style={{ fontSize: 8, color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)', letterSpacing: '0.05em' }}>
              /100
            </span>
          </div>
        )}

        <div>
          <div style={{
            display: 'inline-block',
            padding: '4px 12px', borderRadius: 6,
            background: cfg.bg, color: cfg.color,
            fontSize: 12, fontFamily: 'var(--font-mono)', fontWeight: 700,
            letterSpacing: '0.08em',
            marginBottom: 5,
          }}>
            {cfg.label}
          </div>
          <div style={{ fontSize: 11, color: 'var(--ink-dim)', fontFamily: 'var(--font-mono)' }}>
            {result.needsReview ? 'Needs a human — missing inputs below' : 'Winnability score'}
          </div>
        </div>

        {!result.needsReview && (
          <div style={{ flex: 1, marginLeft: 8 }}>
            <div style={{ height: 6, borderRadius: 3, background: 'var(--surface-sunken)', overflow: 'hidden' }}>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {CHECKLIST.map(item => {
            const isMissing = missing.has(item.code) || (missing.has('no_docs') && item.code !== 'no_docs')
            return (
              <div key={item.code} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700,
                  color: isMissing ? 'var(--red)' : 'var(--green)',
                  width: 14, textAlign: 'center', flexShrink: 0,
                }}>
                  {isMissing ? '✕' : '✓'}
                </span>
                <span style={{ fontSize: 13, color: isMissing ? 'var(--ink)' : 'var(--ink-dim)' }}>
                  {item.label}
                </span>
              </div>
            )
          })}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          {result.factors.map((f, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--ink)', width: 96, flexShrink: 0 }}>
                {f.label}
              </span>
              <span style={{ fontSize: 12.5, color: 'var(--ink-dim)', lineHeight: 1.45 }}>
                {f.detail}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 14, fontSize: 10.5, color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)' }}>
        {result.needsReview
          ? <>Run <code style={{ background: 'var(--surface-sunken)', padding: '1px 5px', borderRadius: 3 }}>cd ~/fcu-cron/bid-scanner &amp;&amp; python parser.py --parse {bidId}</code> to fill the gaps</>
          : 'Scoring method → bid-scanner/docs/scoring.md'}
      </div>
    </div>
  )
}
