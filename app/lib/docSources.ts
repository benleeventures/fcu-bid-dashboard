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
  | 'on-demand'     // retrievable, but only via a manual CAPTCHA-solved sweep (not the nightly run)
  | 'unsupported'   // no automated retrieval path exists yet for this portal

const CAPABILITY: Record<string, DocCapability> = {
  'BidNet Direct': 'full',
  'Caltrans CCOP': 'full',
  'Cal eProcure': 'full',
  'SAM.gov': 'full',                  // enumerates every Attachments/Links file
  'Long Beach BuySpeed': 'full',      // Playwright clicks every downloadFile() control

  'Crisp Plan Room': 'page-images',
  'SoCal Plan Room': 'page-images',

  'UCLA Capital Programs': 'primary-only',  // url points straight at one Ad-for-Bids PDF
  'Quality Bidders': 'primary-only',        // downloads every doc link, but the set isn't guaranteed
  'RAMP LA County': 'primary-only',         // Salesforce SPA — often yields nothing
  'SecureBids': 'primary-only',
  'Bid Locker': 'primary-only',             // best-effort JS-download capture, unverified

  'VendorLine': 'on-demand',          // PlanetBids portal docs — fetched by `main.py --vl-docs` (manual CAPTCHA solve)
  'PlanetBids': 'unsupported',        // stored URL is the portal search page, no per-bid detail
  'OpenGov': 'unsupported',           // Cloudflare Turnstile — scan is manual, no doc step
  'LAUSD Facilities': 'unsupported',  // one combined bid-date report, not per-bid
}

export function docCapability(source: string | null | undefined): DocCapability {
  if (!source) return 'primary-only'
  return CAPABILITY[source] ?? 'primary-only'
}
