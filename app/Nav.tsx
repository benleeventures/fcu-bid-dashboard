import type { ReactNode } from 'react'

/**
 * Shared top navigation bar.
 *
 * The Airtable button opens the team base. Set NEXT_PUBLIC_AIRTABLE_URL in the
 * environment to override; the fallback is the current team invite link (only
 * resolves for people already granted access to the base, which is fine — the
 * dashboard and the base share the same small internal audience).
 */
const AIRTABLE_URL =
  process.env.NEXT_PUBLIC_AIRTABLE_URL ||
  'https://airtable.com/invite/l?inviteId=invo7mbPUsuWCvKtW&inviteToken=54bfce5e0661c6368cb40a5187c4bfa2bc75fe66ba362ad9be7f46e188f4fdae'

type NavKey = 'bids' | 'scanner' | 'intel' | 'settings'

const LINKS: { key: NavKey; label: string; href: string }[] = [
  { key: 'bids',     label: 'Bids',           href: '/' },
  { key: 'scanner',  label: 'Scanner health', href: '/scanner' },
  { key: 'intel',    label: 'Intel',          href: '/intel' },
  { key: 'settings', label: 'Settings',       href: '/settings' },
]

export default function Nav({ active, right }: { active?: NavKey; right?: ReactNode }) {
  return (
    <nav className="app-nav">
      <a href="/" className="app-nav__brand" style={{ color: 'inherit' }}>
        <span className="app-nav__mark">FCU</span>
        <span className="app-nav__title">Bid Dashboard</span>
      </a>

      <div className="app-nav__links">
        {LINKS.map(l => (
          <a
            key={l.key}
            href={l.href}
            className={`app-nav__link${active === l.key ? ' app-nav__link--active' : ''}`}
          >
            {l.label}
          </a>
        ))}
      </div>

      <div className="app-nav__right">
        {right}
        <a
          href={AIRTABLE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn--primary"
          title="Open the FCU bid base in Airtable"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path d="M11.6 3.2 3.4 6.5c-.5.2-.5.9 0 1.1l8.2 3.3c.3.1.6.1.9 0l8.2-3.3c.5-.2.5-.9 0-1.1l-8.2-3.3a1.2 1.2 0 0 0-.9 0Z" fill="#2A1E06"/>
            <path d="M21 9.6 13 12.8v7.6c0 .5.5.8.9.6l7.4-2.9c.4-.2.7-.6.7-1V9.6Z" fill="#2A1E06" opacity=".78"/>
            <path d="M3 9.7v6.5c0 .5.3.9.7 1l4.5 1.8V13L3 9.7Z" fill="#2A1E06" opacity=".55"/>
          </svg>
          Open Airtable
          <span aria-hidden style={{ opacity: .55 }}>↗</span>
        </a>
      </div>
    </nav>
  )
}
