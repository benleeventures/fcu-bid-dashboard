'use client'

import type { CompetitorStat, PricingInsight } from './page'

type Props = {
  competitors: CompetitorStat[]
  pricing: PricingInsight
  totalBids: number
}

function pct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(decimals)}%`
}

function marginColor(v: number | null): string {
  if (v == null) return 'var(--gray)'
  if (v < -10) return 'var(--red)'     // very aggressive pricer
  if (v < -5)  return 'var(--orange)'  // moderately aggressive
  return 'var(--green)'                // close to the pack
}

export default function IntelOverview({ competitors, pricing, totalBids }: Props) {
  return (
    <div style={{ marginBottom: 32, display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Top Competitors */}
      <div style={{
        background: 'var(--charcoal-soft)', borderRadius: 12,
        border: '1px solid var(--charcoal-mid)', overflow: 'hidden',
      }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--charcoal-mid)' }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Top Competitors</h2>
          <p style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono' }}>
            Win margin = (winner − 2nd place) / 2nd place · Below field = (winner − avg bids) / avg bids
          </p>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: 'var(--charcoal)' }}>
                {['#', 'Vendor', 'Wins', 'Avg Win Margin', 'Avg % Below Field', 'Agencies'].map(h => (
                  <th key={h} style={{
                    padding: '8px 16px', textAlign: 'left',
                    color: 'var(--gray)', fontWeight: 500, fontSize: 11,
                    fontFamily: 'IBM Plex Mono', whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {competitors.map((c, i) => (
                <tr key={c.vendor_name} style={{
                  borderTop: '1px solid var(--charcoal-mid)',
                  background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
                }}>
                  <td style={{ padding: '10px 16px', color: 'var(--gray)', fontFamily: 'IBM Plex Mono', fontSize: 12 }}>
                    {i + 1}
                  </td>
                  <td style={{ padding: '10px 16px', fontWeight: 500 }}>{c.vendor_name}</td>
                  <td style={{
                    padding: '10px 16px', fontFamily: 'IBM Plex Mono',
                    color: 'var(--gold)', fontWeight: 500,
                  }}>{c.wins}</td>
                  <td style={{ padding: '10px 16px', fontFamily: 'IBM Plex Mono' }}>
                    <span style={{ color: marginColor(c.avg_win_margin_pct) }}>
                      {pct(c.avg_win_margin_pct)}
                    </span>
                  </td>
                  <td style={{ padding: '10px 16px', fontFamily: 'IBM Plex Mono' }}>
                    <span style={{ color: marginColor(c.avg_below_field_pct) }}>
                      {pct(c.avg_below_field_pct)}
                    </span>
                  </td>
                  <td style={{ padding: '10px 16px', color: 'var(--gray)', fontSize: 12, maxWidth: 240 }}>
                    {c.agencies.slice(0, 3).join(', ')}
                    {c.agencies.length > 3 && <span style={{ color: 'var(--gray)' }}> +{c.agencies.length - 3}</span>}
                  </td>
                </tr>
              ))}
              {competitors.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--gray)' }}>
                    No competitor data yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pricing Insights row */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>

        {/* Most vs Least Competitive */}
        <div style={{
          background: 'var(--charcoal-soft)', borderRadius: 12,
          border: '1px solid var(--charcoal-mid)', padding: '16px 20px',
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Competition Density by Agency</h2>
          <p style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', marginBottom: 16 }}>
            Avg bidders per award — more = harder to win
          </p>
          {pricing.most_competitive.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: 'var(--gray)', marginBottom: 8, fontFamily: 'IBM Plex Mono' }}>MOST COMPETITIVE</div>
              {pricing.most_competitive.map(a => (
                <div key={a.agency} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  marginBottom: 6,
                }}>
                  <span style={{ fontSize: 13 }}>{a.agency}</span>
                  <span style={{
                    fontFamily: 'IBM Plex Mono', fontSize: 12,
                    color: a.avg_bidders >= 5 ? 'var(--red)' : a.avg_bidders >= 3 ? 'var(--orange)' : 'var(--green)',
                    fontWeight: 500,
                  }}>{a.avg_bidders} bidders</span>
                </div>
              ))}
              {pricing.least_competitive.length > 0 && (
                <>
                  <div style={{
                    fontSize: 11, color: 'var(--gray)', marginTop: 16, marginBottom: 8,
                    fontFamily: 'IBM Plex Mono',
                  }}>LEAST COMPETITIVE</div>
                  {pricing.least_competitive.map(a => (
                    <div key={a.agency} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      marginBottom: 6,
                    }}>
                      <span style={{ fontSize: 13 }}>{a.agency}</span>
                      <span style={{
                        fontFamily: 'IBM Plex Mono', fontSize: 12,
                        color: 'var(--green)', fontWeight: 500,
                      }}>{a.avg_bidders} bidders</span>
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </div>

        {/* Avg margin to beat winner */}
        <div style={{
          background: 'var(--charcoal-soft)', borderRadius: 12,
          border: '1px solid var(--charcoal-mid)', padding: '16px 20px',
        }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Pricing Gap</h2>
          <p style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', marginBottom: 24 }}>
            Avg gap between winner and 2nd-place bid
          </p>
          {pricing.avg_gap_pct != null ? (
            <div style={{ textAlign: 'center', paddingTop: 8 }}>
              <div style={{
                fontSize: 48, fontFamily: 'IBM Plex Mono', fontWeight: 700,
                color: pricing.avg_gap_pct < 8 ? 'var(--red)' : pricing.avg_gap_pct < 15 ? 'var(--orange)' : 'var(--green)',
                letterSpacing: '-1px',
              }}>
                {pricing.avg_gap_pct.toFixed(1)}%
              </div>
              <div style={{ fontSize: 12, color: 'var(--gray)', marginTop: 8 }}>
                {pricing.avg_gap_pct < 8
                  ? 'Tight market — every % counts'
                  : pricing.avg_gap_pct < 15
                    ? 'Moderate spread — pricing flexibility exists'
                    : 'Wide spread — winners price significantly lower'}
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--gray)', fontSize: 13, paddingTop: 20 }}>
              No comparison data available yet
            </div>
          )}

          <div style={{
            marginTop: 24, padding: '12px 16px',
            background: 'var(--charcoal)', borderRadius: 8, fontSize: 12,
            fontFamily: 'IBM Plex Mono', color: 'var(--gray)',
          }}>
            Based on {totalBids} awarded bids across all portals
          </div>
        </div>

      </div>
    </div>
  )
}
