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

  // Test the exact join query used by the intel page
  const joined = await sb
    .from('bid_intel')
    .select(`
      id, agency, title,
      winner_vendor:vendors!winner_vendor_id ( canonical_name ),
      submissions:bid_intel_submissions (
        id, bid_amount, is_winner, rank, raw_vendor_name,
        vendor:vendors ( canonical_name )
      )
    `)
    .limit(1)

  return NextResponse.json({
    joined_data: joined.data,
    joined_error: joined.error?.message,
    joined_status: joined.status,
  })
}
