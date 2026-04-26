import { getRates, updateRates } from '../actions/settings'
import SettingsForm from './SettingsForm'

export const revalidate = 0

export default async function SettingsPage() {
  const rates = await getRates()

  return (
    <main style={{ maxWidth: 600, margin: '0 auto', padding: '32px 16px' }}>
      <div style={{ marginBottom: 32 }}>
        <a href="/" style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono', textDecoration: 'none' }}>
          ← Back to bids
        </a>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--gold)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'IBM Plex Mono', fontWeight: 500, fontSize: 14, color: 'var(--charcoal)'
        }}>⚙</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.3px' }}>Rate Settings</h1>
      </div>
      <p style={{ color: 'var(--gray)', fontSize: 12, fontFamily: 'IBM Plex Mono', marginBottom: 32 }}>
        Changing rates will flag all open draft estimates as stale.
      </p>

      <SettingsForm rates={rates} updateRates={updateRates} />

      <div style={{ marginTop: 40, padding: '16px 20px', background: 'var(--charcoal-soft)', borderRadius: 10, border: '1px solid var(--charcoal-mid)' }}>
        <div style={{ fontSize: 11, color: 'var(--gray)', fontFamily: 'IBM Plex Mono', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
          Markup Policy (fixed)
        </div>
        {[
          { label: 'Default', value: '30%', note: 'Always submit this first', color: 'var(--green)' },
          { label: 'To win', value: '25%', note: 'Owner must approve', color: 'var(--gold)' },
          { label: 'Below 25%', value: 'BLOCK', note: 'Never without owner sign-off', color: 'var(--red)' },
        ].map(row => (
          <div key={row.label} style={{ display: 'flex', gap: 12, alignItems: 'baseline', marginBottom: 8 }}>
            <span style={{ color: 'var(--gray)', fontSize: 12, width: 80, fontFamily: 'IBM Plex Mono' }}>{row.label}</span>
            <span style={{ color: row.color, fontFamily: 'IBM Plex Mono', fontWeight: 600, fontSize: 14, width: 50 }}>{row.value}</span>
            <span style={{ color: 'var(--gray)', fontSize: 12 }}>{row.note}</span>
          </div>
        ))}
      </div>
    </main>
  )
}
