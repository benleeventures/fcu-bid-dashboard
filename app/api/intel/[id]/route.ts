import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function DELETE(_req: Request, { params }: { params: { id: string } }) {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_KEY
  if (!url || !key) return NextResponse.json({ error: 'missing env vars', url: !!url, key: !!key }, { status: 500 })

  const sb = createClient(url, key)
  const { data, error, status, statusText } = await sb
    .from('bid_intel')
    .delete()
    .eq('id', params.id)
    .select('id')

  return NextResponse.json({ id: params.id, data, error: error?.message, status, statusText })
}
