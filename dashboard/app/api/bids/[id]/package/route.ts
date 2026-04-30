import { createClient } from '@supabase/supabase-js'
import { renderToBuffer } from '@react-pdf/renderer'
import React from 'react'
import {
  Document, Page, Text, View, StyleSheet, Line, Svg,
} from '@react-pdf/renderer'

// ─── Types ────────────────────────────────────────────────────────────────────

type LineItem = {
  type: 'labor' | 'material'
  description: string
  qty: number
  unit: string
  rate: number
  total: number
}

type Bid  = Record<string, any>
type Spec = Record<string, any> | null
type Est  = Record<string, any> | null

// ─── Helpers ──────────────────────────────────────────────────────────────────

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 })

const today = () =>
  new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })

// ─── Styles ───────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  page:        { paddingHorizontal: 52, paddingVertical: 44, fontFamily: 'Helvetica', fontSize: 9, color: '#1C1C1E', lineHeight: 1.5 },
  goldBar:     { height: 6, backgroundColor: '#C8922A', marginHorizontal: -52, marginTop: -44, marginBottom: 20 },

  // Header
  co:          { fontSize: 15, fontFamily: 'Helvetica-Bold', color: '#1C1C1E', marginBottom: 3 },
  coSub:       { fontSize: 8, color: '#636366', marginBottom: 10 },
  divider:     { borderBottomWidth: 0.5, borderBottomColor: '#C8922A', marginBottom: 14 },

  // Title
  title:       { fontSize: 13, fontFamily: 'Helvetica-Bold', textAlign: 'center', marginBottom: 16 },

  // Info grid
  infoRow:     { flexDirection: 'row', marginBottom: 4 },
  infoLabel:   { width: 72, color: '#636366', fontFamily: 'Helvetica' },
  infoValue:   { flex: 1, color: '#1C1C1E' },

  // Section
  sectionHead: { fontFamily: 'Helvetica-Bold', fontSize: 8, letterSpacing: 0.8, marginTop: 14, marginBottom: 4 },
  sectionLine: { borderBottomWidth: 0.5, borderBottomColor: '#CCCCCC', marginBottom: 6 },

  // Line item row
  liRow:       { flexDirection: 'row', marginBottom: 3 },
  liDesc:      { flex: 2.5, paddingLeft: 8 },
  liDetail:    { flex: 2, color: '#636366' },
  liTotal:     { flex: 1, textAlign: 'right', fontFamily: 'Helvetica-Bold' },
  liPending:   { flex: 1, textAlign: 'right', color: '#FF9F0A', fontFamily: 'Helvetica-Oblique' },

  // Summary box
  summaryBox:  { marginTop: 14, padding: 14, backgroundColor: '#F9F5EF', borderRadius: 4 },
  summRow:     { flexDirection: 'row', marginBottom: 5 },
  summLabel:   { flex: 1, color: '#636366' },
  summValue:   { width: 100, textAlign: 'right', color: '#1C1C1E' },
  summDivider: { borderBottomWidth: 1, borderBottomColor: '#C8922A', marginVertical: 7 },
  totalLabel:  { flex: 1, fontSize: 13, fontFamily: 'Helvetica-Bold' },
  totalValue:  { width: 110, textAlign: 'right', fontSize: 13, fontFamily: 'Helvetica-Bold', color: '#C8922A' },
  altText:     { color: '#636366', fontSize: 8, marginTop: 4 },

  // Compliance
  compItem:    { flexDirection: 'row', marginBottom: 4 },
  compBox:     { width: 10, height: 10, borderWidth: 0.8, borderColor: '#636366', marginRight: 8, marginTop: 1 },
  compText:    { flex: 1, color: '#1C1C1E' },

  // Signature
  sigRule:     { borderBottomWidth: 0.5, borderBottomColor: '#C8922A', marginVertical: 14 },
  sigRow:      { flexDirection: 'row', gap: 20, marginTop: 20 },
  sigLineWrap: { flex: 1 },
  sigLine:     { borderBottomWidth: 0.5, borderBottomColor: '#1C1C1E', marginBottom: 4 },
  sigCaption:  { fontSize: 7.5, color: '#636366' },

  // Footer
  footer:      { position: 'absolute', bottom: 24, left: 52, right: 52, borderTopWidth: 0.5, borderTopColor: '#C8922A', paddingTop: 6, fontSize: 7.5, color: '#636366', textAlign: 'center' },
})

// ─── PDF Document ─────────────────────────────────────────────────────────────

function BidPackagePDF({ bid, spec, est }: { bid: Bid; spec: Spec; est: Est }) {
  const items:       LineItem[] = est?.line_items ?? []
  const laborLines    = items.filter(l => l.type === 'labor')
  const materialLines = items.filter(l => l.type === 'material')

  const subtotal       = est?.subtotal        ?? 0
  const markup30       = est?.markup_30       ?? 0
  const markup25       = est?.markup_25       ?? 0
  const selectedMarkup = est?.selected_markup ?? 30
  const selectedTotal  = selectedMarkup === 30 ? markup30 : markup25
  const overhead       = selectedTotal - subtotal
  const altMarkup      = selectedMarkup === 30 ? 25 : 30
  const altTotal       = selectedMarkup === 30 ? markup25 : markup30

  const complianceItems: string[] = []
  if (spec?.prevailing_wage)  complianceItems.push('Prevailing wage rates apply — Journeyman $108.00/hr · Apprentice $58.00/hr')
  if (spec?.bid_bond) {
    const pct = spec.bid_bond_pct ? ` (${spec.bid_bond_pct}%)` : ''
    complianceItems.push(`Bid bond required${pct} — certificate to be attached to bid package`)
  }
  if (spec?.walk_required)    complianceItems.push(`Mandatory pre-bid walk: ${spec.walk_date_raw || 'See bid documents'}`)

  const dueStr = (bid.due_date_raw ?? bid.due_date ?? '—').toString()

  return React.createElement(
    Document,
    {},
    React.createElement(
      Page,
      { size: 'LETTER', style: s.page },

      // Gold bar
      React.createElement(View, { style: s.goldBar }),

      // Company header
      React.createElement(Text, { style: s.co }, 'FLOOR COVERING UNLIMITED, INC.'),
      React.createElement(Text, { style: s.coSub },
        'Chatsworth, CA 91311  ·  C-15 License  ·  IUPAT Local 1247, District Council 36  ·  DVBE Certified'),
      React.createElement(View, { style: s.divider }),

      // Bid Proposal title
      React.createElement(Text, { style: s.title }, 'BID PROPOSAL'),

      // Project info
      React.createElement(View, null,
        ...[
          ['Project:', bid.title ?? ''],
          ['Agency:', bid.agency ?? ''],
          ['Bid No.:', bid.bid_id ?? ''],
          ['Date:', today()],
          ['Bid Due:', dueStr],
        ].map(([label, value]) =>
          React.createElement(View, { key: label, style: s.infoRow },
            React.createElement(Text, { style: s.infoLabel }, label),
            React.createElement(Text, { style: s.infoValue }, value),
          )
        )
      ),

      // Labor
      laborLines.length > 0 && React.createElement(View, null,
        React.createElement(Text, { style: s.sectionHead }, 'LABOR'),
        React.createElement(View, { style: s.sectionLine }),
        ...laborLines.map((l, i) =>
          React.createElement(View, { key: i, style: s.liRow },
            React.createElement(Text, { style: s.liDesc }, l.description),
            React.createElement(Text, { style: s.liDetail },
              `${l.qty.toLocaleString()} hrs × ${money(l.rate)}/hr`),
            React.createElement(Text, { style: s.liTotal }, money(l.total)),
          )
        ),
      ),

      // Materials
      materialLines.length > 0 && React.createElement(View, null,
        React.createElement(Text, { style: s.sectionHead }, 'MATERIALS'),
        React.createElement(View, { style: s.sectionLine }),
        ...materialLines.map((l, i) => {
          const hasCost = l.rate > 0 && l.total > 0
          return React.createElement(View, { key: i, style: s.liRow },
            React.createElement(Text, { style: s.liDesc }, l.description),
            React.createElement(Text, { style: s.liDetail },
              hasCost
                ? `${l.qty.toLocaleString()} ${l.unit} × ${money(l.rate)}/${l.unit}`
                : `${l.qty.toLocaleString()} ${l.unit}`
            ),
            hasCost
              ? React.createElement(Text, { style: s.liTotal }, money(l.total))
              : React.createElement(Text, { style: s.liPending }, 'Pending quote'),
          )
        }),
      ),

      // Summary box
      est && React.createElement(View, { style: s.summaryBox },
        React.createElement(View, { style: s.summRow },
          React.createElement(Text, { style: s.summLabel }, 'Subtotal'),
          React.createElement(Text, { style: s.summValue }, money(subtotal)),
        ),
        React.createElement(View, { style: s.summRow },
          React.createElement(Text, { style: s.summLabel }, `Overhead & Profit (${selectedMarkup}%)`),
          React.createElement(Text, { style: s.summValue }, money(overhead)),
        ),
        React.createElement(View, { style: s.summDivider }),
        React.createElement(View, { style: s.summRow },
          React.createElement(Text, { style: s.totalLabel }, 'TOTAL BID AMOUNT'),
          React.createElement(Text, { style: s.totalValue }, money(selectedTotal)),
        ),
        altTotal > 0 && React.createElement(Text, { style: s.altText },
          `Alternative (${altMarkup}% markup): ${money(altTotal)}`),
      ),

      // Compliance
      complianceItems.length > 0 && React.createElement(View, null,
        React.createElement(Text, { style: s.sectionHead }, 'COMPLIANCE'),
        React.createElement(View, { style: s.sectionLine }),
        ...complianceItems.map((item, i) =>
          React.createElement(View, { key: i, style: s.compItem },
            React.createElement(View, { style: s.compBox }),
            React.createElement(Text, { style: s.compText }, item),
          )
        ),
      ),

      // Signature
      React.createElement(View, { style: s.sigRule }),
      React.createElement(Text, { style: { fontFamily: 'Helvetica-Bold', marginBottom: 6 } }, 'Submitted by:'),
      React.createElement(Text, null, 'Joanne Lee, VP Operations'),
      React.createElement(Text, { style: { color: '#636366', marginBottom: 4 } }, 'Floor Covering Unlimited, Inc.'),
      React.createElement(View, { style: s.sigRow },
        React.createElement(View, { style: s.sigLineWrap },
          React.createElement(View, { style: s.sigLine }),
          React.createElement(Text, { style: s.sigCaption }, 'Authorized Signature'),
        ),
        React.createElement(View, { style: { width: 130 } },
          React.createElement(View, { style: s.sigLine }),
          React.createElement(Text, { style: s.sigCaption }, 'Date'),
        ),
      ),

      // Footer
      React.createElement(View, { style: s.footer, fixed: true },
        React.createElement(Text, null,
          'Floor Covering Unlimited, Inc. · Chatsworth, CA 91311 · C-15 License · IUPAT Local 1247, DC 36 · DVBE Certified'
        ),
      ),
    ),
  )
}

// ─── Route Handler ─────────────────────────────────────────────────────────────

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const bidId = decodeURIComponent(params.id)
  const client = sb()

  const [{ data: bid }, { data: spec }, { data: est }] = await Promise.all([
    client.from('bids').select('*').eq('bid_id', bidId).single(),
    client.from('bid_specs').select('*').eq('bid_id', bidId).maybeSingle(),
    client.from('estimates').select('*').eq('bid_id', bidId).maybeSingle(),
  ])

  if (!bid) return new Response('Bid not found', { status: 404 })

  const buffer = await renderToBuffer(
    React.createElement(BidPackagePDF, { bid, spec, est }) as React.ReactElement<any>
  )

  const safe = (bid.bid_id ?? bidId).replace(/[^a-zA-Z0-9-_]/g, '_')
  return new Response(buffer, {
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': `attachment; filename="FCU-Bid-${safe}.pdf"`,
    },
  })
}
