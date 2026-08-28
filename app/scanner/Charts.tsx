// Hand-rolled SVG/CSS charts for the scanner dashboard. No chart library.
// All server components — purely presentational.

import { DayPoint, FunnelStep, pct } from './lib'

const MONO = 'IBM Plex Mono, monospace'

// ── Funnel ────────────────────────────────────────────────────────────────

export function Funnel({ steps }: { steps: FunnelStep[] }) {
  if (!steps.length) {
    return (
      <div style={{ color: 'var(--gray)', fontFamily: MONO, fontSize: 12 }}>
        No instrumented run yet — the funnel populates after the next full
        {' '}<code style={{ color: 'var(--gold-light)' }}>python main.py</code>
        {' '}(scheduled Mon–Fri 6 AM PT). Backfilled history still shows below.
      </div>
    )
  }
  const max = Math.max(steps[0].value, 1)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {steps.map((s, i) => {
        const w = Math.max((s.value / max) * 100, 1.5)
        const prev = i > 0 ? steps[i - 1].value : null
        return (
          <div key={s.label}>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              fontSize: 12, marginBottom: 3,
            }}>
              <span style={{ color: 'var(--white)' }}>{s.label}</span>
              <span style={{ fontFamily: MONO, color: 'var(--gray)' }}>
                {prev !== null && (
                  <span style={{ color: 'var(--gold-light)', marginRight: 8 }}>
                    {pct(s.value, prev)}
                  </span>
                )}
                <span style={{ color: 'var(--white)', fontWeight: 600 }}>{s.value.toLocaleString()}</span>
              </span>
            </div>
            <div style={{ background: 'var(--charcoal-mid)', borderRadius: 4, height: 22, overflow: 'hidden' }}>
              <div style={{
                width: `${w}%`, height: '100%',
                background: i === steps.length - 1 ? 'var(--green)' : 'var(--gold)',
                borderRadius: 4, transition: 'width .3s',
              }} />
            </div>
            {s.note && (
              <div style={{ fontSize: 10.5, color: 'var(--gray)', fontFamily: MONO, marginTop: 2 }}>
                {s.note}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Volume-over-time line chart ───────────────────────────────────────────

type Series = { key: keyof DayPoint; label: string; color: string }

const SERIES: Series[] = [
  { key: 'raw', label: 'Raw scraped', color: 'var(--gold)' },
  { key: 'relevant', label: 'Relevant', color: 'var(--green)' },
  { key: 'new', label: 'New', color: 'var(--gold-light)' },
]

export function VolumeChart({ data }: { data: DayPoint[] }) {
  const W = 720, H = 220, PAD_L = 36, PAD_B = 22, PAD_T = 8, PAD_R = 8
  const plotW = W - PAD_L - PAD_R
  const plotH = H - PAD_B - PAD_T
  const n = data.length
  const maxY = Math.max(1, ...data.flatMap(d => SERIES.map(s => d[s.key] as number)))
  const x = (i: number) => PAD_L + (n <= 1 ? 0 : (i / (n - 1)) * plotW)
  const y = (v: number) => PAD_T + plotH - (v / maxY) * plotH

  const ticks = 4
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => Math.round((maxY / ticks) * i))

  const path = (key: keyof DayPoint) =>
    data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(d[key] as number).toFixed(1)}`).join(' ')

  const everyNth = Math.ceil(n / 8)

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', minWidth: 520, display: 'block' }}>
        {yTicks.map(t => (
          <g key={t}>
            <line x1={PAD_L} x2={W - PAD_R} y1={y(t)} y2={y(t)} stroke="var(--charcoal-mid)" strokeWidth={1} />
            <text x={PAD_L - 6} y={y(t) + 3} textAnchor="end" fontSize={9} fill="var(--gray)" fontFamily={MONO}>{t}</text>
          </g>
        ))}
        {data.map((d, i) => i % everyNth === 0 && (
          <text key={d.day} x={x(i)} y={H - 6} textAnchor="middle" fontSize={9} fill="var(--gray)" fontFamily={MONO}>
            {d.day.slice(5)}
          </text>
        ))}
        {SERIES.map(s => (
          <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth={1.75}
            strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {SERIES.map(s => (
          <g key={s.key}>
            {data.map((d, i) => (
              <circle key={i} cx={x(i)} cy={y(d[s.key] as number)} r={1.6} fill={s.color} />
            ))}
          </g>
        ))}
      </svg>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 4 }}>
        {SERIES.map(s => (
          <span key={s.key} style={{ fontSize: 11, fontFamily: MONO, color: 'var(--gray)', display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 3, background: s.color, display: 'inline-block', borderRadius: 2 }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Filtered-out bars ────────────────────────────────────────────────────

export function FilteredOutBars({ data }: { data: DayPoint[] }) {
  const max = Math.max(1, ...data.map(d => d.filteredOut))
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 90, overflowX: 'auto' }}>
      {data.map(d => (
        <div key={d.day} title={`${d.day} · ${d.filteredOut} filtered out`}
          style={{ flex: '1 0 6px', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', height: '100%' }}>
          <div style={{
            height: `${(d.filteredOut / max) * 100}%`,
            minHeight: d.filteredOut > 0 ? 2 : 0,
            background: 'var(--orange)', borderRadius: 2, opacity: 0.8,
          }} />
        </div>
      ))}
    </div>
  )
}
