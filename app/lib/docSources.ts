// How much of a bid's document set the scanner's downloader can actually
// retrieve, per source portal. Drives the honesty line on the bid page's
// Documents card — a source we structurally can't pull from must say so, not
// look like a download that came back empty.
//
// Keep in sync with bid-scanner/storage.py COMPLETE_SOURCES and the Portal
// Coverage table in ROADMAP.md.

export type DocCapability =
  | 'full'          // downloader enumerates the entire document set
  | 'primary-only'  // downloader grabs one best-guess PDF; more may exist on the portal
  | 'page-images'   // plan-room web viewer — page images, not source files
  | 'unsupported'   // no automated retrieval path exists yet for this portal

const CAPABILITY: Record<string, DocCapability> = {
  'BidNet Direct': 'full',
  'Caltrans CCOP': 'full',
  'Cal eProcure': 'full',

  'Crisp Plan Room': 'page-images',
  'SoCal Plan Room': 'page-images',

  'SAM.gov': 'primary-only',
  'UCLA Capital Programs': 'primary-only',
  'Quality Bidders': 'primary-only',
  'RAMP LA County': 'primary-only',
  'SecureBids': 'primary-only',

  'PlanetBids': 'unsupported',       // stored URL is the portal search page, no per-bid detail
  'OpenGov': 'unsupported',          // Cloudflare Turnstile — scan is manual, no doc step
  'Bid Locker': 'unsupported',       // attachments are javascript:downloadFile(id)
  'Long Beach BuySpeed': 'unsupported',
  'LAUSD Facilities': 'unsupported', // one combined bid-date report, not per-bid
}

export function docCapability(source: string | null | undefined): DocCapability {
  if (!source) return 'primary-only'
  return CAPABILITY[source] ?? 'primary-only'
}
