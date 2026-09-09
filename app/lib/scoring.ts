// FCU winnability score (scoring v2). Mirrored in bid-scanner/scoring.py.
// Full write-up: bid-scanner/docs/scoring.md
//
//   score = geography(0–60) + leadTime(0–30) + awardAdj(−6…+10)  → clamp 0–100
//   verdict:  >= 58 GO   ·   33–57 MAYBE   ·   < 33 NO-GO
//
// Hard NO-GO: flooring is a minor part of a larger scope, or past due.
// NEEDS MANUAL REVIEW (no score) when a scoring input is missing.

export type ScoreFactor = {
  label: string
  detail: string
}

export type ReviewReason = { code: string; label: string }

export type GoNoGoResult = {
  score: number | null
  verdict: 'go' | 'maybe' | 'no_go' | null
  factors: ScoreFactor[]
  needsReview: boolean
  reviewReasons: ReviewReason[]
}

type ScoringBid = {
  due_date: string | null
  county?: string | null
  geo_status?: string | null
}

type ScoringSpec = {
  flooring_is_primary?: boolean | null
  award_method?: string | null
  project_city?: string | null
} | null

export const REVIEW_LABELS: Record<string, string> = {
  no_docs: 'Bid documents not reviewed yet',
  no_location: 'Job location not identified',
  no_due_date: 'No bid due date on file',
  no_scope_read: 'Scope of work not reviewed yet',
  past_due: 'Bid due date has passed',
}

// ── Drive-time bands from the FCU shop (9601 Cozycroft Ave, Chatsworth 91311) ──
const BAND_A = new Set([
  'chatsworth', 'canoga park', 'winnetka', 'woodland hills', 'west hills', 'reseda',
  'northridge', 'porter ranch', 'granada hills', 'mission hills', 'north hills',
  'sylmar', 'pacoima', 'sun valley', 'panorama city', 'van nuys', 'sepulveda',
  'north hollywood', 'valley village', 'valley glen', 'sherman oaks', 'studio city',
  'encino', 'tarzana', 'lake balboa', 'arleta', 'shadow hills', 'tujunga', 'sunland',
  'san fernando', 'burbank', 'glendale', 'la crescenta', 'montrose',
  'la canada flintridge', 'la cañada flintridge', 'santa clarita', 'valencia',
  'newhall', 'saugus', 'canyon country', 'stevenson ranch', 'agoura hills', 'agoura',
  'calabasas', 'hidden hills', 'westlake village', 'oak park', 'simi valley',
  'moorpark', 'thousand oaks', 'newbury park',
])
const BAND_B = new Set([
  'los angeles', 'hollywood', 'west hollywood', 'beverly hills', 'century city',
  'brentwood', 'west los angeles', 'mar vista', 'palms', 'culver city', 'santa monica',
  'pacific palisades', 'playa vista', 'playa del rey', 'venice', 'marina del rey',
  'westchester', 'el segundo', 'pasadena', 'south pasadena', 'altadena', 'san marino',
  'alhambra', 'monterey park', 'montebello', 'rosemead', 'san gabriel', 'temple city',
  'arcadia', 'monrovia', 'duarte', 'bradbury', 'sierra madre', 'el monte',
  'south el monte', 'baldwin park', 'irwindale', 'azusa', 'glendora', 'covina',
  'west covina', 'la verne', 'san dimas', 'claremont', 'pomona', 'diamond bar',
  'walnut', 'eagle rock', 'highland park', 'inglewood', 'hawthorne', 'lawndale',
  'gardena', 'hermosa beach', 'manhattan beach', 'lennox', 'view park', 'windsor hills',
  'ladera heights', 'oxnard', 'ventura', 'san buenaventura', 'camarillo',
  'port hueneme', 'santa paula', 'fillmore', 'ojai',
])
const BAND_C = new Set([
  'torrance', 'carson', 'redondo beach', 'palos verdes estates', 'rancho palos verdes',
  'rolling hills', 'rolling hills estates', 'lomita', 'san pedro', 'wilmington',
  'harbor city', 'long beach', 'signal hill', 'compton', 'lynwood', 'south gate',
  'huntington park', 'bell', 'bell gardens', 'cudahy', 'maywood', 'vernon', 'commerce',
  'pico rivera', 'whittier', 'santa fe springs', 'norwalk', 'downey', 'bellflower',
  'paramount', 'lakewood', 'cerritos', 'artesia', 'hawaiian gardens', 'la mirada',
  'la habra heights', 'industry', 'city of industry', 'hacienda heights',
  'rowland heights', 'la puente', 'avocado heights', 'walnut park', 'palmdale',
  'lancaster', 'la habra', 'brea', 'fullerton', 'buena park', 'la palma', 'cypress',
  'anaheim', 'placentia', 'yorba linda', 'stanton', 'garden grove', 'orange',
  'villa park', 'santa ana', 'westminster', 'fountain valley', 'los alamitos',
  'seal beach', 'midway city',
])
const BAND_D = new Set([
  'irvine', 'tustin', 'costa mesa', 'newport beach', 'newport coast', 'lake forest',
  'laguna hills', 'laguna woods', 'laguna beach', 'laguna niguel', 'aliso viejo',
  'mission viejo', 'rancho santa margarita', 'coto de caza', 'ladera ranch',
  'san juan capistrano', 'san clemente', 'dana point', 'trabuco canyon',
  'foothill ranch',
])
const COUNTY_DEFAULT_BAND: Record<string, 'A' | 'B' | 'C' | 'D'> = {
  Ventura: 'B',
  'Los Angeles': 'C',
  Orange: 'C',
  'San Diego': 'D',
}
const BAND_SCORE = { A: 60, B: 48, C: 32, D: 16 } as const

function driveBand(city: string | null | undefined, county: string | null | undefined): 'A' | 'B' | 'C' | 'D' | null {
  const c = (city || '').trim().toLowerCase().replace(/[.,'-]+$/, '').replace(/\s+/g, ' ')
  if (c) {
    if (BAND_A.has(c)) return 'A'
    if (BAND_B.has(c)) return 'B'
    if (BAND_C.has(c)) return 'C'
    if (BAND_D.has(c)) return 'D'
  }
  if (county && COUNTY_DEFAULT_BAND[county]) return COUNTY_DEFAULT_BAND[county]
  return null
}

function leadTimeScore(dueDate: string): number {
  const days = Math.round((new Date(dueDate).getTime() - Date.now()) / 86_400_000)
  if (days >= 21) return 30
  if (days >= 14) return 24
  if (days >= 10) return 15
  if (days >= 7) return 8
  if (days >= 4) return 3
  return 0
}

function awardAdj(method: string | null | undefined): number {
  if (method === 'best_value' || method === 'qualifications') return 10
  if (method === 'low_bid') return -6
  return 0
}

const review = (codes: string[]): GoNoGoResult => ({
  score: null,
  verdict: null,
  factors: [],
  needsReview: true,
  reviewReasons: codes.map(code => ({ code, label: REVIEW_LABELS[code] ?? code })),
})

export function scoreGoNoGo(bid: ScoringBid, spec: ScoringSpec): GoNoGoResult {
  // ── Not parsed ──────────────────────────────────────────────────────────
  if (!spec) return review(['no_docs'])

  // ── Hard NO-GO: flooring is a minor slice of a bigger multi-trade scope ──
  if (spec.flooring_is_primary === false) {
    return {
      score: 0, verdict: 'no_go', needsReview: false, reviewReasons: [],
      factors: [{ label: 'Flooring is minor scope', detail: 'Flooring is one of many trades on a larger project — not worth chasing' }],
    }
  }

  // ── Hard NO-GO: past due ────────────────────────────────────────────────
  if (bid.due_date && new Date(bid.due_date).getTime() - Date.now() < -86_400_000) {
    return {
      score: 0, verdict: 'no_go', needsReview: false, reviewReasons: [],
      factors: [{ label: 'Past due', detail: 'The bid due date has passed' }],
    }
  }

  // ── Missing inputs → NEEDS MANUAL REVIEW ────────────────────────────────
  const reasons: string[] = []
  const city = (spec.project_city || '').trim()
  const band = driveBand(city || null, bid.county)
  if (band === null || (bid.geo_status === 'unknown' && !city)) reasons.push('no_location')
  if (!bid.due_date) reasons.push('no_due_date')
  if (spec.flooring_is_primary === null || spec.flooring_is_primary === undefined) reasons.push('no_scope_read')
  if (reasons.length) return review(reasons)

  // ── Score ──────────────────────────────────────────────────────────────
  const geo = BAND_SCORE[band as 'A' | 'B' | 'C' | 'D']
  const lead = leadTimeScore(bid.due_date as string)
  const adj = awardAdj(spec.award_method)

  const factors: ScoreFactor[] = [
    { label: 'Geography', detail: geoNote(band as string, city, bid.county) },
    { label: 'Lead time', detail: leadNote(bid.due_date as string) },
  ]
  if (spec.award_method) factors.push({ label: 'Award method', detail: awardNote(spec.award_method) })

  const clamped = Math.min(100, Math.max(0, Math.round(geo + lead + adj)))
  const verdict: 'go' | 'maybe' | 'no_go' =
    clamped >= 58 ? 'go' : clamped >= 33 ? 'maybe' : 'no_go'

  return { score: clamped, verdict, factors, needsReview: false, reviewReasons: [] }
}

function geoNote(band: string, city: string, county: string | null | undefined): string {
  const where = city || county || 'location'
  const km: Record<string, string> = {
    A: '≤45 min from the shop', B: '≤75 min from the shop',
    C: '≤110 min — travel cost rises', D: '>110 min — far, thin margin',
  }
  return `${where} — ${km[band] ?? ''}`
}
function leadNote(dueDate: string): string {
  const days = Math.round((new Date(dueDate).getTime() - Date.now()) / 86_400_000)
  if (days >= 14) return `${days} days to bid — comfortable`
  if (days >= 7) return `${days} days to bid — workable`
  return `${days} days to bid — tight`
}
function awardNote(method: string): string {
  if (method === 'low_bid') return 'Low-bid — pure price competition'
  if (method === 'best_value') return 'Best-value — FCU compliance story counts'
  if (method === 'qualifications') return 'Qualifications-based — favors FCU'
  return method
}

export const verdictConfig = {
  go:     { label: 'GO',     color: 'var(--green)', bg: '#30D15822' },
  maybe:  { label: 'MAYBE',  color: 'var(--gold)',  bg: '#C8922A22' },
  no_go:  { label: 'NO-GO',  color: 'var(--red)',   bg: '#FF453A22' },
  review: { label: 'NEEDS REVIEW', color: 'var(--gray)', bg: '#8E8E9322' },
}
