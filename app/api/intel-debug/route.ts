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

  // Simple count first
  const count = await sb.from('bid_intel').select('id', { count: 'exact', head: true })
  // Simple select without joins
  const simple = await sb.from('bid_intel').select('id, agency, title').limit(3)

  return NextResponse.json({
    count_data: count.count,
    count_error: count.error?.message,
    simple_data: simple.data,
    simple_error: simple.error?.message,
    url_prefix: url.slice(0, 30),
  })
}
