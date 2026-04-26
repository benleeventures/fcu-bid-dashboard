'use server'

import { createClient } from '@supabase/supabase-js'

export type Rates = {
  standard: number
  prevailing: number
  apprentice: number
  updatedAt: string
}

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

export async function getRates(): Promise<Rates> {
  const { data } = await sb().from('settings').select('key,value,updated_at').in('key', [
    'rate_journeyman_standard',
    'rate_journeyman_prevailing',
    'rate_apprentice',
  ])

  const get = (key: string) => parseFloat(data?.find(r => r.key === key)?.value ?? '0')
  const latestUpdate = data?.reduce((latest, row) => {
    return row.updated_at > latest ? row.updated_at : latest
  }, '') ?? ''

  return {
    standard:   get('rate_journeyman_standard'),
    prevailing: get('rate_journeyman_prevailing'),
    apprentice: get('rate_apprentice'),
    updatedAt:  latestUpdate,
  }
}

export async function updateRates(rates: Omit<Rates, 'updatedAt'>) {
  const client = sb()
  const now = new Date().toISOString()

  await Promise.all([
    client.from('settings').upsert({ key: 'rate_journeyman_standard',   value: String(rates.standard),   updated_at: now }),
    client.from('settings').upsert({ key: 'rate_journeyman_prevailing', value: String(rates.prevailing), updated_at: now }),
    client.from('settings').upsert({ key: 'rate_apprentice',            value: String(rates.apprentice), updated_at: now }),
  ])

  // Flag all unsaved/draft estimates as stale
  await client.from('estimates')
    .update({ is_stale: true })
    .eq('status', 'draft')
    .not('rates_version', 'is', null)
}
