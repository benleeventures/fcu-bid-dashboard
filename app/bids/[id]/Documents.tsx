type Doc = {
  filename: string
  public_url: string
  content_type: string | null
  bytes: number | null
  kind: string | null
}

import { docCapability } from '../../lib/docSources'

type Props = {
  docs: Doc[]
  docsExpected: number | null
  docsSyncedAt: string | null
  portalUrl: string | null
  source: string | null
}

function fmtBytes(n: number | null): string {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function icon(ct: string | null, name: string): string {
  const s = (ct || '') + name.toLowerCase()
  if (s.includes('pdf')) return 'PDF'
  if (s.includes('word') || s.endsWith('.doc') || s.endsWith('.docx')) return 'DOC'
  if (s.includes('sheet') || s.includes('excel') || s.endsWith('.xls') || s.endsWith('.xlsx')) return 'XLS'
  if (s.includes('zip')) return 'ZIP'
  if (s.includes('image') || s.endsWith('.jpg') || s.endsWith('.jpeg') || s.endsWith('.png')) return 'IMG'
  return 'FILE'
}

export default function Documents({ docs, docsExpected, docsSyncedAt, portalUrl, source }: Props) {
  const count = docs.length
  const cap = docCapability(source)
  const allImages = count > 0 && docs.every(d => d.kind === 'page_image')
  const srcName = source || 'this portal'

  let status: { text: string; color: string }
  if (count === 0 && cap === 'unsupported') {
    status = { text: `The tracker can't retrieve documents from ${srcName} automatically — get them from the portal`, color: 'var(--ink-dim)' }
  } else if (count === 0) {
    status = { text: `No documents retrieved yet — check the portal`, color: 'var(--ink-dim)' }
  } else if (cap === 'page-images' || allImages) {
    status = { text: `${count} plan-room page image${count > 1 ? 's' : ''} — full document set is on the portal`, color: 'var(--orange)' }
  } else if (docsExpected != null && count >= docsExpected) {
    status = { text: `${count} document${count > 1 ? 's' : ''} — full set`, color: 'var(--green)' }
  } else if (docsExpected != null && count < docsExpected) {
    status = { text: `${count} of ${docsExpected} documents — verify against portal`, color: 'var(--orange)' }
  } else {
    status = { text: `Primary document only — the tracker can't get the rest from ${srcName}, check the portal`, color: 'var(--orange)' }
  }

  return (
    <div className="card" style={{ marginBottom: 24, padding: '18px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: count ? 14 : 0 }}>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--ink-dim)' }}>
          BID DOCUMENTS
        </div>
        <div style={{ fontSize: 12, color: status.color, fontFamily: 'var(--font-mono)' }}>
          {status.text}
          {portalUrl && (
            <>
              {' '}
              <a href={portalUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold-strong)' }}>
                Portal ↗
              </a>
            </>
          )}
        </div>
      </div>

      {count > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {docs.map(d => (
            <a
              key={d.filename}
              href={d.public_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '9px 12px', borderRadius: 'var(--r-sm)',
                background: 'var(--surface-sunken)', textDecoration: 'none',
              }}
            >
              <span style={{
                fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 700,
                color: 'var(--gold-strong)', background: 'var(--gold-tint)',
                padding: '3px 5px', borderRadius: 3, flexShrink: 0, letterSpacing: '0.04em',
              }}>
                {icon(d.content_type, d.filename)}
              </span>
              <span style={{ fontSize: 13, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                {d.filename}
              </span>
              <span style={{ fontSize: 11, color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                {fmtBytes(d.bytes)}
              </span>
              <span aria-hidden style={{ fontSize: 12, color: 'var(--ink-faint)', flexShrink: 0 }}>↗</span>
            </a>
          ))}
          {docsSyncedAt && (
            <div style={{ fontSize: 10, color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
              Mirrored {new Date(docsSyncedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })} · copies, verify against the portal before bidding
            </div>
          )}
        </div>
      )}
    </div>
  )
}
