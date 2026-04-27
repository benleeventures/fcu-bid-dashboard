export type ScoreFactor = {
  label: string
  delta: number   // positive = helps, negative = hurts
  note: string
}

export type GoNoGoResult = {
  score: number                    // 0–100
  verdict: 'go' | 'maybe' | 'no_go'
  factors: ScoreFactor[]
  partial: boolean                 // true when spec not parsed — score is estimate only
}

type ScoringBid = {
  is_relevant: boolean
  due_date: string | null
}

type ScoringSpec = {
  total_sqft: number | null
  prevailing_wage: boolean | null
  bid_bond: boolean | null
  walk_required: boolean | null
  dvbe_required?: boolean | null
  dbe_goal_pct?: number | null
} | null

export function scoreGoNoGo(bid: ScoringBid, spec: ScoringSpec): GoNoGoResult {
  const factors: ScoreFactor[] = []
  let score = 55

  // ── 1. Flooring scope match ──────────────────────────────────────────────
  if (bid.is_relevant) {
    factors.push({ label: 'Flooring scope', delta: +20, note: 'Job matches FCU trade' })
    score += 20
  } else {
    factors.push({ label: 'Flooring scope', delta: -25, note: 'Not a flooring job' })
    score -= 25
  }

  // ── 2. Square footage ────────────────────────────────────────────────────
  if (spec?.total_sqft) {
    const sf = spec.total_sqft
    if (sf >= 20_000) {
      factors.push({ label: 'Project size', delta: +15, note: `${sf.toLocaleString()} SF — large job, strong margin` })
      score += 15
    } else if (sf >= 5_000) {
      factors.push({ label: 'Project size', delta: +10, note: `${sf.toLocaleString()} SF — solid scope` })
      score += 10
    } else if (sf >= 1_000) {
      factors.push({ label: 'Project size', delta: +3, note: `${sf.toLocaleString()} SF — workable scope` })
      score += 3
    } else {
      factors.push({ label: 'Project size', delta: -10, note: `${sf.toLocaleString()} SF — too small for overhead` })
      score -= 10
    }
  }

  // ── 3. Prevailing wage ───────────────────────────────────────────────────
  if (spec?.prevailing_wage === true) {
    factors.push({ label: 'Prevailing wage', delta: -8, note: 'Certified payroll overhead; $108/hr rate applies' })
    score -= 8
  } else if (spec?.prevailing_wage === false) {
    factors.push({ label: 'Prevailing wage', delta: +5, note: 'Standard rates — simpler execution' })
    score += 5
  }

  // ── 4. Bid bond ──────────────────────────────────────────────────────────
  if (spec?.bid_bond === true) {
    factors.push({ label: 'Bid bond required', delta: -5, note: 'Insurance coordination adds lead time' })
    score -= 5
  }

  // ── 5. Mandatory job walk ────────────────────────────────────────────────
  if (spec?.walk_required === true) {
    factors.push({ label: 'Job walk required', delta: -5, note: 'Lenny must attend — schedule conflict risk' })
    score -= 5
  }

  // ── 6. DVBE requirement (FCU is certified — competitive edge) ────────────
  if (spec?.dvbe_required === true) {
    factors.push({ label: 'DVBE required', delta: +12, note: 'FCU is certified — fewer qualified competitors' })
    score += 12
  }

  // ── 7. DBE goal ──────────────────────────────────────────────────────────
  if (spec?.dbe_goal_pct && spec.dbe_goal_pct > 0) {
    factors.push({ label: 'DBE goal', delta: -10, note: `${spec.dbe_goal_pct}% goal — need a qualified sub` })
    score -= 10
  }

  // ── 8. Due date — hard block only (system catches bids early by design) ──
  if (bid.due_date) {
    const daysOut = Math.round((new Date(bid.due_date).getTime() - Date.now()) / 86_400_000)
    if (daysOut < 0) {
      factors.push({ label: 'Past due', delta: -100, note: 'Deadline passed — cannot submit' })
      return { score: 0, verdict: 'no_go', factors, partial: !spec }
    }
  }

  // ── 9. Spec parsed ───────────────────────────────────────────────────────
  const partial = !spec
  if (spec) {
    factors.push({ label: 'Spec parsed', delta: +5, note: 'Scope details available' })
    score += 5
  } else {
    factors.push({ label: 'Spec not parsed', delta: -5, note: 'Run parser to improve accuracy' })
    score -= 5
  }

  const clamped = Math.min(100, Math.max(0, Math.round(score)))
  const verdict: GoNoGoResult['verdict'] =
    clamped >= 65 ? 'go' : clamped >= 40 ? 'maybe' : 'no_go'

  return { score: clamped, verdict, factors, partial }
}

export const verdictConfig = {
  go:     { label: 'GO',     color: 'var(--green)', bg: '#30D15822' },
  maybe:  { label: 'MAYBE',  color: 'var(--gold)',  bg: '#C8922A22' },
  no_go:  { label: 'NO-GO',  color: 'var(--red)',   bg: '#FF453A22' },
}
