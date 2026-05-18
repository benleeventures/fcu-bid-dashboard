import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

export async function DELETE(_req: Request, { params }: { params: { id: string } }) {
  const sb = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
  // submissions cascade-delete via FK ON DELETE CASCADE
  const { error } = await sb.from('bid_intel').delete().eq('id', params.id)
  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json({ ok: true })
}
