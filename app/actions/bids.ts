'use server'

import { createClient } from '@supabase/supabase-js'

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

export type BidStatus = 'active' | 'submitted' | 'won' | 'lost' | 'no_bid'

export async function updateBidStatus(
  bidId: string,
  status: BidStatus,
  submittedAmount?: number | null,
  awardAmount?: number | null,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const client = sb()
    const payload: Record<string, any> = { bid_status: status }

    if (status === 'submitted' || status === 'won' || status === 'lost') {
      if (submittedAmount != null) payload.submitted_amount = submittedAmount
      if (status === 'submitted') payload.submitted_at = new Date().toISOString()
    }
    if ((status === 'won' || status === 'lost') && awardAmount != null) {
      payload.award_amount = awardAmount
    }
    // Reset tracking fields when reverting to active/no_bid
    if (status === 'active' || status === 'no_bid') {
      payload.submitted_amount = null
      payload.award_amount = null
      payload.submitted_at = null
    }

    const { error } = await client.from('bids').update(payload).eq('bid_id', bidId)
    if (error) return { ok: false, error: error.message }
    return { ok: true }
  } catch (err: any) {
    return { ok: false, error: err.message }
  }
}

export async function updateBidFavorite(
  bidId: string,
  isFavorite: boolean,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const { error } = await sb().from('bids').update({ is_favorite: isFavorite }).eq('bid_id', bidId)
    if (error) return { ok: false, error: error.message }
    return { ok: true }
  } catch (err: any) {
    return { ok: false, error: err.message }
  }
}
