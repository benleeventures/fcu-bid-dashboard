import { docCapability } from '../../lib/docSources'

type Doc = {
  filename: string
  public_url: string
  content_type: string | null
  bytes: number | null
  kind: string | null
}

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
    status = { text: `Automated retrieval not available for ${srcName}`, color: 'var(--ink-dim)' }
  } else if (count === 0) {
    status = { text: `No documents retrieved yet — check the portal`, color: 'var(--ink-dim)' }
  } else if (cap === 'page-images' || allImages) {
    status = { text: `${count} plan-room page image${count > 1 ? 's' : ''} — full set is on the portal`, color: 'var(--orange)' }
  } else if (docsExpected != null && count >= docsExpected) {
    status = { text: `${count} document${count > 1 ? 's' : ''} — full set`, color: 'var(--green)' }
  } else if (docsExpected != null && count < docsExpected) {
    status = { text: `${count} of ${docsExpected} documents — verify against portal`, color: 'var(--orange)' }
  } else {
    status = { text: `${count} document${count > 1 ? 's' : ''} — portal may have more`, color: 'var(--orange)' }
  }

  // Prominent callout when the tracker structurally can't (or only partly can)
  // fetch this source's documents — so the team knows a thin/empty list is a
  // tooling limit, not "this bid has no documents".
  const callout =
    cap === 'unsupported'
      ? `The bid tracker can't pull documents from ${srcName} automatically${
          source === 'PlanetBids' ? ' (no per-bid document URL is exposed)' : ''
        }. Any missing documents for this bid are a tooling limitation — download them directly from the portal.`
      : cap === 'primary-only' && count > 0
      ? `${srcName} doesn't give the tracker a guaranteed complete document list — treat the files below as a starting point and confirm the full set on the portal.`
      : null

  return (
    <div className="card" style={{ marginBottom: 24, padding: '18px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: (count || callout) ? 12 : 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--ink-dim)' }}>
            BID DOCUMENTS
          </span>
          <span
            title="Automatic document retrieval is still being built out — not every portal is covered yet. Always confirm the full set on the source portal."
            style={{
              fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 700,
              letterSpacing: '0.06em', color: 'var(--gold-strong)',
              background: 'var(--gold-tint)', border: '1px solid var(--gold-tint-strong)',
              padding: '2px 5px', borderRadius: 3,
            }}
          >
            WIP
          </span>
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

      {callout && (
        <div style={{
          display: 'flex', gap: 10, alignItems: 'flex-start',
          padding: '10px 12px', marginBottom: count ? 12 : 0,
          borderRadius: 'var(--r-sm)',
          background: 'var(--orange-tint)',
          border: '1px solid var(--border-strong)',
        }}>
          <span aria-hidden style={{ fontSize: 13, flexShrink: 0, lineHeight: 1.4 }}>⚠</span>
          <span style={{ fontSize: 12.5, color: 'var(--ink-dim)', lineHeight: 1.5 }}>
            {callout}
            {portalUrl && (
              <>
                {' '}
                <a href={portalUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gold-strong)', whiteSpace: 'nowrap' }}>
                  Open portal ↗
                </a>
              </>
            )}
          </span>
        </div>
      )}

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

      <div style={{
        marginTop: (count || callout) ? 12 : 10, paddingTop: 10,
        borderTop: '1px solid var(--border)',
        fontSize: 10.5, color: 'var(--ink-faint)', fontFamily: 'var(--font-mono)', lineHeight: 1.5,
      }}>
        Automatic document retrieval is a work in progress — coverage varies by portal
        and PlanetBids / OpenGov aren&apos;t supported yet. Always confirm the complete
        document set on the source portal before bidding.
      </div>
    </div>
  )
}
