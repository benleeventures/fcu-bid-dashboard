'use server'

import { createClient } from '@supabase/supabase-js'
import type { Rates } from './settings'

export type LineItem = {
  id: string
  type: 'labor' | 'material'
  description: string
  qty: number
  unit: string
  rate: number
  total: number
  rate_key: 'standard' | 'prevailing' | 'apprentice' | null
}

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

export async function saveEstimate(
  bidId: string,
  lineItems: LineItem[],
  selectedMarkup: 25 | 30,
  ratesSnapshot: Omit<Rates, 'updatedAt'>,
  status: 'draft' | 'approved' = 'draft',
) {
  const subtotal = lineItems.reduce((s, i) => s + i.total, 0)
  const markup30 = subtotal * 1.30
  const markup25 = subtotal * 1.25
  const finalBid = selectedMarkup === 30 ? markup30 : markup25

  const client = sb()
  const payload = {
    line_items:      lineItems,
    rates_snapshot:  ratesSnapshot,
    rates_version:   new Date().toISOString(),
    is_stale:        false,
    status,
    labor_hours:     lineItems.filter(i => i.type === 'labor').reduce((s, i) => s + i.qty, 0),
    labor_rate:      ratesSnapshot.standard,
    labor_total:     lineItems.filter(i => i.type === 'labor').reduce((s, i) => s + i.total, 0),
    materials_total: lineItems.filter(i => i.type === 'material').reduce((s, i) => s + i.total, 0),
    subtotal,
    markup_30:       markup30,
    markup_25:       markup25,
    selected_markup: selectedMarkup,
    final_bid_amount: finalBid,
    approved_by:     status === 'approved' ? 'Joanne' : null,
    approved_at:     status === 'approved' ? new Date().toISOString() : null,
  }

  const { data: existing } = await client.from('estimates').select('id').eq('bid_id', bidId).maybeSingle()
  const { error } = existing
    ? await client.from('estimates').update(payload).eq('bid_id', bidId)
    : await client.from('estimates').insert({ bid_id: bidId, ...payload })

  if (error) throw new Error(error.message)
}

export async function recalculateEstimate(bidId: string, currentRates: Omit<Rates, 'updatedAt'>) {
  const client = sb()
  const { data: est } = await client.from('estimates').select('line_items, selected_markup').eq('bid_id', bidId).single()
  if (!est) return

  const items: LineItem[] = est.line_items ?? []
  const existingMarkup = (est.selected_markup === 25 ? 25 : 30) as 25 | 30
  const rateMap: Record<string, number> = {
    standard:   currentRates.standard,
    prevailing: currentRates.prevailing,
    apprentice: currentRates.apprentice,
  }

  // Update labor line items with new rates; leave materials untouched
  const updated = items.map(item => {
    if (item.type === 'labor' && item.rate_key && rateMap[item.rate_key] !== undefined) {
      const newRate = rateMap[item.rate_key]
      return { ...item, rate: newRate, total: item.qty * newRate }
    }
    return item
  })

  await saveEstimate(bidId, updated, existingMarkup, currentRates, 'draft')
}
