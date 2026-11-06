const PAYPAL_BASE_URL = process.env.PAYPAL_BASE_URL || 'https://api-m.sandbox.paypal.com'

async function getAccessToken(): Promise<string> {
  const clientId = process.env.PAYPAL_CLIENT_ID
  const secret = process.env.PAYPAL_CLIENT_SECRET
  if (!clientId || !secret) {
    throw new Error('PayPal credentials are not configured (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET).')
  }
  const res = await fetch(`${PAYPAL_BASE_URL}/v1/oauth2/token`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${Buffer.from(`${clientId}:${secret}`).toString('base64')}`,
    },
    body: 'grant_type=client_credentials',
  })
  if (!res.ok) throw new Error(`PayPal auth failed (${res.status})`)
  const data = await res.json()
  return data.access_token
}

export async function createOrder(token: string, person: string, amountUsd: number, description: string, siteUrl: string) {
  const res = await fetch(`${PAYPAL_BASE_URL}/v2/checkout/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      intent: 'CAPTURE',
      purchase_units: [
        {
          reference_id: `split_${person.toLowerCase().replace(/\s+/g, '_')}`.slice(0, 256),
          description: `Bill Split for ${person}: ${description.slice(0, 100)}`.slice(0, 127),
          amount: { currency_code: 'USD', value: amountUsd.toFixed(2) },
        },
      ],
      application_context: {
        brand_name: 'PaySplit AI Agent',
        user_action: 'PAY_NOW',
        return_url: `${siteUrl}/?payment=success`,
        cancel_url: `${siteUrl}/?payment=cancel`,
      },
    }),
  })
  if (!res.ok) throw new Error(`PayPal order creation failed (${res.status})`)
  const order = await res.json()
  const approveLink = (order.links || []).find((l: { rel: string }) => l.rel === 'approve')?.href ?? null
  return { order_id: order.id as string, approve_link: approveLink as string | null, status: order.status as string }
}

export async function getOrderStatus(token: string, orderId: string): Promise<string> {
  const res = await fetch(`${PAYPAL_BASE_URL}/v2/checkout/orders/${encodeURIComponent(orderId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) return 'UNKNOWN'
  const data = await res.json()
  return data.status || 'UNKNOWN'
}

export { getAccessToken }
