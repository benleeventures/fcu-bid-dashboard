import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'FCU Bid Dashboard',
  description: 'Floor Covering Unlimited — Government Bid Tracker',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div style={{ background: 'var(--charcoal)', minHeight: '100vh' }}>
          {children}
        </div>
      </body>
    </html>
  )
}
