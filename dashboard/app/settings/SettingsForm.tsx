'use client'

import { useState, useTransition } from 'react'
import type { Rates } from '../actions/settings'

type Props = {
  rates: Rates
  updateRates: (rates: Omit<Rates, 'updatedAt'>) => Promise<void>
}

export default function SettingsForm({ rates, updateRates }: Props) {
  const [standard,   setStandard]   = useState(String(rates.standard))
  const [prevailing, setPrevailing] = useState(String(rates.prevailing))
  const [apprentice, setApprentice] = useState(String(rates.apprentice))
  const [saved,      setSaved]      = useState(false)
  const [isPending,  startTransition] = useTransition()

  function handleSave() {
    startTransition(async () => {
      await updateRates({
        standard:   parseFloat(standard)   || rates.standard,
        prevailing: parseFloat(prevailing) || rates.prevailing,
        apprentice: parseFloat(apprentice) || rates.apprentice,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    })
  }

  const rateRows = [
    { label: 'Journeyman Standard',       note: 'Default for all public works',   value: standard,   set: setStandard },
    { label: 'Journeyman Prevailing Wage', note: 'Certified payroll / complex jobs', value: prevailing, set: setPrevailing },
    { label: 'Apprentice',                 note: 'Lower-skill tasks',               value: apprentice, set: setApprentice },
  ]

  return (
    <div style={{ background: 'var(--charcoal-soft)', borderRadius: 12, border: '1px solid var(--charcoal-mid)', padding: '24px 28px' }}>
      {rateRows.map(row => (
        <div key={row.label} style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
            {row.label}
          </label>
          <div style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', marginBottom: 8 }}>
            {row.note}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: 'var(--gray)', fontFamily: 'IBM Plex Mono', fontSize: 14 }}>$</span>
            <input
              type="number"
              value={row.value}
              onChange={e => row.set(e.target.value)}
              style={{
                background: 'var(--charcoal)', border: '1px solid var(--charcoal-mid)',
                borderRadius: 8, color: 'var(--white)', padding: '8px 12px',
                fontSize: 16, fontFamily: 'IBM Plex Mono', fontWeight: 600,
                outline: 'none', width: 120,
              }}
            />
            <span style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono' }}>/hr</span>
          </div>
        </div>
      ))}

      {rates.updatedAt && (
        <div style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', marginBottom: 20 }}>
          Last updated: {new Date(rates.updatedAt).toLocaleString('en-US', {
            timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
          })} PT
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={isPending}
        style={{
          background: saved ? 'var(--green)' : 'var(--gold)',
          color: 'var(--charcoal)', border: 'none', borderRadius: 8,
          padding: '10px 24px', fontSize: 14, fontWeight: 700,
          cursor: isPending ? 'not-allowed' : 'pointer',
          opacity: isPending ? 0.7 : 1,
          transition: 'background 0.2s',
        }}
      >
        {isPending ? 'Saving…' : saved ? '✓ Saved' : 'Save Rates'}
      </button>
    </div>
  )
}
