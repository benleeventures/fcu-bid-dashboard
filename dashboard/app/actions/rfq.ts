'use server'

import { createClient } from '@supabase/supabase-js'

function sb() {
  return createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
}

async function sendResend(to: string[], subject: string, html: string, cc?: string[]) {
  const apiKey = process.env.RESEND_API_KEY
  if (!apiKey) throw new Error('RESEND_API_KEY not set')
  const body: Record<string, any> = { from: 'FCU Bid Agent <onboarding@resend.dev>', to, subject, html }
  if (cc?.length) body.cc = cc
  const resp = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`Resend ${resp.status}: ${text}`)
  }
}

export async function sendRFQEmails(
  bidId: string,
  toEmail: string,
  ccEmail?: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const client = sb()
    const [{ data: bid }, { data: spec }, { data: est }] = await Promise.all([
      client.from('bids').select('*').eq('bid_id', bidId).single(),
      client.from('bid_specs').select('*').eq('bid_id', bidId).maybeSingle(),
      client.from('estimates').select('*').eq('bid_id', bidId).maybeSingle(),
    ])

    if (!bid) return { ok: false, error: 'Bid not found' }
    if (!est) return { ok: false, error: 'No estimate — build one first' }

    const materialLines: Array<{ description: string; qty: number; unit: string }> =
      ((est.line_items as any[]) ?? []).filter((l: any) => l.type === 'material')

    if (!materialLines.length) return { ok: false, error: 'No material lines in estimate' }

    const title    = bid.title ?? 'Unknown Job'
    const agency   = bid.agency ?? ''
    const bidDue   = (bid as any).due_date_raw ?? bid.due_date ?? '—'
    const portal   = bid.url ?? ''
    const sqft     = (spec as any)?.total_sqft
    const sqftStr  = sqft ? `${sqft.toLocaleString()} SF total` : 'SF TBD'
    const pwNote   = (spec as any)?.prevailing_wage ? 'Prevailing wage project.' : ''

    const matRows = materialLines.map((l, i) => `
    <tr style="background:${i % 2 === 0 ? '#2C2C2E' : '#3A3A3C'};">
      <td style="padding:12px 16px;font-size:14px;font-weight:600;color:#F5F5F0;">${l.description}</td>
      <td style="padding:12px 16px;font-size:14px;font-family:monospace;color:#F5F5F0;text-align:right;">${l.qty.toLocaleString()}</td>
      <td style="padding:12px 16px;font-size:14px;font-family:monospace;color:#8E8E93;">${l.unit}</td>
      <td style="padding:12px 16px;font-size:13px;color:#FF9F0A;font-weight:600;">Quote needed</td>
    </tr>`).join('')

    const portalLink = portal
      ? `<a href="${portal}" style="color:#C8922A;">${portal.slice(0, 80)}</a>`
      : '—'

    const html = `
<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:700px;margin:0 auto;padding:32px 24px;">

    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:24px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent · RFQ Draft</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">${title}</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8E8E93;">${agency}</p>
    </div>

    <div style="background:#2C2C2E;border-radius:8px;padding:16px 20px;margin-bottom:28px;font-size:13px;color:#8E8E93;">
      <strong style="color:#F5F5F0;">How to use:</strong> Forward the quote request below to your material reps.
      Return completed quotes before <strong style="color:#FF9F0A;">${bidDue}</strong>.
    </div>

    <div style="border:1px dashed #3A3A3C;border-radius:8px;padding:24px;margin-bottom:24px;">
      <p style="margin:0 0 6px;font-size:12px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">── Forward this to your rep ──</p>

      <p style="margin:12px 0;font-size:14px;color:#F5F5F0;">Hi [Rep Name],</p>
      <p style="margin:0 0 16px;font-size:14px;color:#F5F5F0;line-height:1.6;">
        We are bidding on a flooring project and need material pricing. Please provide your best pricing by <strong>${bidDue}</strong>.
      </p>

      <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
        <tr><td style="padding:5px 0;color:#8E8E93;font-size:13px;width:110px;">Project</td><td style="padding:5px 0;font-size:13px;color:#F5F5F0;">${title}</td></tr>
        <tr><td style="padding:5px 0;color:#8E8E93;font-size:13px;">Agency</td><td style="padding:5px 0;font-size:13px;color:#F5F5F0;">${agency}</td></tr>
        <tr><td style="padding:5px 0;color:#8E8E93;font-size:13px;">Scope</td><td style="padding:5px 0;font-size:13px;color:#F5F5F0;">${sqftStr}. ${pwNote}</td></tr>
        <tr><td style="padding:5px 0;color:#8E8E93;font-size:13px;">Bid Due</td><td style="padding:5px 0;font-size:13px;font-weight:700;color:#FF9F0A;">${bidDue}</td></tr>
      </table>

      <h3 style="font-size:12px;font-weight:700;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;margin-bottom:10px;">Materials Needed</h3>
      <table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#3A3A3C;">
            <th style="padding:10px 16px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Description</th>
            <th style="padding:10px 16px;text-align:right;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Qty</th>
            <th style="padding:10px 16px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Unit</th>
            <th style="padding:10px 16px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Your Price</th>
          </tr>
        </thead>
        <tbody>${matRows}</tbody>
      </table>

      <p style="margin:20px 0 0;font-size:14px;color:#F5F5F0;line-height:1.6;">
        Please include product specs, color options, and lead time.<br><br>
        Thank you,<br>
        <strong>Joanne Lee</strong><br>
        Floor Covering Unlimited · Chatsworth, CA
      </p>
    </div>

    <p style="font-size:12px;color:#8E8E93;">Portal: ${portalLink}</p>
  </div>
</body>
</html>`

    if (!toEmail?.trim()) return { ok: false, error: 'Enter a recipient email first' }
    const cc = ccEmail?.trim() ? [ccEmail.trim()] : []
    await sendResend(
      [toEmail.trim()],
      `[RFQ Draft] ${title.slice(0, 55)} — ${materialLines.length} material line${materialLines.length > 1 ? 's' : ''}`,
      html,
      cc,
    )
    return { ok: true }
  } catch (err: any) {
    return { ok: false, error: err.message }
  }
}
