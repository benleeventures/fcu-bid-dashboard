'use client'

import { useState, useTransition } from 'react'
import { addBidToAirtable } from '../../actions/airtable'

type Props = {
  bidId: string
  syncedAt: string | null
  /** Tab-separated single row for pasting straight into an Airtable grid. */
  copyRow: string
}

const btn: React.CSSProperties = {
  borderRadius: 8, padding: '7px 14px', fontSize: 12,
  fontWeight: 600, fontFamily: 'var(--font-mono)', cursor: 'pointer',
  border: '1px solid var(--border-strong)', background: 'transparent',
  color: 'var(--ink-dim)', transition: 'all 0.15s', whiteSpace: 'nowrap',
}

export default function AddToAirtable({ bidId, syncedAt, copyRow }: Props) {
  const [pending, startTransition] = useTransition()
  const [state, setState] = useState<'idle' | 'done' | 'already' | 'error'>(
    syncedAt ? 'done' : 'idle',
  )
  const [err, setErr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  function add() {
    setErr(null)
    startTransition(async () => {
      const res = await addBidToAirtable(bidId)
      if (res.ok) setState(res.already ? 'already' : 'done')
      else { setState('error'); setErr(res.error ?? 'Failed') }
    })
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(copyRow)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setErr('Clipboard blocked — select the row text manually')
    }
  }

  const inTracker = state === 'done' || state === 'already'

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <button
        onClick={add}
        disabled={pending || inTracker}
        style={{
          ...btn,
          ...(inTracker
            ? { background: 'var(--green-tint)', color: 'var(--green)', border: '1px solid var(--green)', cursor: 'default' }
            : state === 'error'
            ? { background: '#FF453A18', color: 'var(--red)', border: '1px solid var(--red)' }
            : { border: '1px solid var(--gold)', color: 'var(--gold-strong)', background: '#C8922A14' }),
        }}
        title={inTracker ? 'This bid is on the Airtable tracker' : 'Create an Opportunities record in the FCU Bid Tracker'}
      >
        {pending ? 'Adding…'
          : state === 'done' ? '✓ Added to Airtable'
          : state === 'already' ? '✓ Already in Airtable'
          : state === 'error' ? '⚠ Retry Add to Airtable'
          : '+ Add to Airtable'}
      </button>

      <button onClick={copy} style={{ ...btn, ...(copied ? { color: 'var(--green)', border: '1px solid var(--green)' } : {}) }}
        title="Copy this bid as a tab-separated row — paste into an Airtable grid">
        {copied ? '✓ Copied row' : '⎘ Copy row'}
      </button>

      {err && (
        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--red)', maxWidth: 320 }}>{err}</span>
      )}
    </div>
  )
}
