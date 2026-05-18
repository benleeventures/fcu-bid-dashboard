import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function GET() {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY

  if (!url || !key) {
    return NextResponse.json({ error: 'missing env vars', url: !!url, key: !!key })
  }

  const sb = createClient(url, key)

  // Exact query from intel page
  const full = await sb
    .from('bid_intel')
    .select(`
      id, portal_id, agency, title, awarded_at, winner_amount, total_bidders,
      winner_vendor:vendors!winner_vendor_id ( canonical_name ),
      submissions:bid_intel_submissions (
        id, bid_amount, is_winner, rank, raw_vendor_name,
        vendor:vendors ( canonical_name )
      )
    `)
    .order('awarded_at', { ascending: false })
    .limit(500)

  return NextResponse.json({
    count: full.data?.length ?? 0,
    error: full.error?.message ?? null,
    status: full.status,
    sample: full.data?.slice(0, 1) ?? [],
  })
}
