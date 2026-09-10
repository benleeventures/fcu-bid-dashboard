'use server'

import { createClient } from '@supabase/supabase-js'

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

// Scanner `source` string → Airtable "Source Platform" single-select option.
// Mirrors _SOURCE_MAP in bid-scanner/airtable_sync.py — keep the two in sync.
const SOURCE_MAP: Record<string, string> = {
  'PlanetBids': 'PlanetBids',
  'Cal eProcure': 'Cal eProcure',
  'Caltrans CCOP': 'Caltrans CCOP',
  'OpenGov': 'OpenGov Procurement',
  'Quality Bidders': 'Quality Bidders (Colbi)',
  'BidNet Direct': 'BidNet Direct',
  'Bid Locker': 'Bid Locker',
  'Crisp Plan Room': 'Crisp Plan Room',
  'SoCal Plan Room': 'SoCal Plan Room',
  'SAM.gov': 'SAM.gov (federal)',
  'UCLA Capital Programs': 'UCLA Capital Programs',
  'Long Beach BuySpeed': 'Long Beach BuySpeed',
  'LAUSD Facilities': 'LAUSD Facilities',
  'SecureBids': 'SecureBids (Colbi)',
  'RAMP LA County': 'RAMP LA County',
  'VendorLine': 'VendorLine',
}

// Sources whose `agency` field is already a specific city name.
const CITY_BEARING_SOURCES = new Set(['PlanetBids', 'OpenGov'])

// Always-present columns — the fallback set if Airtable 422s on an unknown field.
const CORE_FIELDS = new Set([
  'Project Name', 'Bid ID', 'Date Surfaced', 'Source Platform',
  'Bid Due Date', 'Status', 'Listing URL', 'City / County / Area',
])

const AIRTABLE_API = 'https://api.airtable.com/v0'
const TABLE = 'Opportunities'

type Result = { ok: boolean; already?: boolean; error?: string }

async function at(path: string, init: RequestInit, apiKey: string) {
  const resp = await fetch(`${AIRTABLE_API}/${path}`, {
    ...init,
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })
  return resp
}

/**
 * Push one bid into the Airtable "FCU Bid Tracker" (Opportunities table) from the
 * dashboard, for bids the scanner didn't auto-sync (unscored, borderline, older
 * rows). Dedupes on the Airtable "Bid ID" field — if a record already exists it
 * is left alone (Robert may have edited it). Stamps bids.airtable_synced_at.
 */
export async function addBidToAirtable(bidId: string): Promise<Result> {
  const apiKey = process.env.AIRTABLE_API_KEY
  const baseId = process.env.AIRTABLE_BASE_ID
  if (!apiKey || !baseId) {
    return { ok: false, error: 'Airtable not configured — set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in the Vercel env' }
  }

  try {
    const client = sb()
    const { data: bid, error } = await client
      .from('bids')
      .select('bid_id,title,agency,source,due_date,url,county,geo_status,airtable_synced_at')
      .eq('bid_id', bidId)
      .single()

    if (error || !bid) return { ok: false, error: 'Bid not found' }

    // Already on the tracker? Check Airtable directly — the source of truth —
    // rather than trusting airtable_synced_at (the scanner also creates records).
    const formula = encodeURIComponent(`{Bid ID}='${String(bid.bid_id).replace(/'/g, "\\'")}'`)
    const existing = await at(
      `${baseId}/${TABLE}?filterByFormula=${formula}&fields%5B%5D=Bid%20ID&maxRecords=1`,
      { method: 'GET' },
      apiKey,
    )
    if (!existing.ok) {
      const text = await existing.text()
      return { ok: false, error: `Airtable lookup failed (${existing.status}): ${text.slice(0, 200)}` }
    }
    const existingJson = await existing.json()
    if ((existingJson.records ?? []).length > 0) {
      if (!bid.airtable_synced_at) {
        await client.from('bids').update({ airtable_synced_at: new Date().toISOString() }).eq('bid_id', bidId)
      }
      return { ok: true, already: true }
    }

    const source = bid.source ?? ''
    const agency = (bid.agency ?? '').slice(0, 200)
    const ownerEmail = process.env.AIRTABLE_OWNER_EMAIL?.trim()

    const fields: Record<string, unknown> = {
      'Project Name': (bid.title ?? '').slice(0, 500),
      'Bid ID': bid.bid_id,
      'Date Surfaced': new Date().toISOString().slice(0, 10),
      'Source Platform': SOURCE_MAP[source] ?? 'Other',
      'Bid Due Date': bid.due_date ?? null,
      'Status': 'Surfaced',
      'Listing URL': bid.url ?? null,
    }
    if (bid.county) fields['County'] = bid.county
    if (agency) fields['Agency or GC'] = agency
    if (CITY_BEARING_SOURCES.has(source) && agency) fields['City / County / Area'] = agency
    if (bid.geo_status === 'unknown') fields['Notes'] = 'Needs county check — place of performance not confirmed'
    if (ownerEmail) fields['Owner'] = { email: ownerEmail }

    let create = await at(
      `${baseId}/${TABLE}`,
      { method: 'POST', body: JSON.stringify({ records: [{ fields }], typecast: true }) },
      apiKey,
    )

    // A missing optional column / bad collaborator email → retry with the
    // always-present core set so the opportunity still lands (matches airtable_sync.py).
    if (!create.ok && create.status === 422) {
      const core = Object.fromEntries(Object.entries(fields).filter(([k]) => CORE_FIELDS.has(k)))
      create = await at(
        `${baseId}/${TABLE}`,
        { method: 'POST', body: JSON.stringify({ records: [{ fields: core }], typecast: true }) },
        apiKey,
      )
    }

    if (!create.ok) {
      const text = await create.text()
      return { ok: false, error: `Airtable create failed (${create.status}): ${text.slice(0, 200)}` }
    }

    await client.from('bids').update({ airtable_synced_at: new Date().toISOString() }).eq('bid_id', bidId)
    return { ok: true }
  } catch (err: any) {
    return { ok: false, error: err.message }
  }
}
