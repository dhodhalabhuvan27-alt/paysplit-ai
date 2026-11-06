import type { Config } from '@netlify/functions'
import { getAccessToken, getOrderStatus } from '../lib/paypal.mts'

export default async (req: Request) => {
  let orderIds: string[] = []
  try {
    const body = await req.json()
    orderIds = Array.isArray(body.orderIds) ? body.orderIds.filter((id: unknown) => typeof id === 'string').slice(0, 50) : []
  } catch {
    return Response.json({ error: 'Invalid JSON body' }, { status: 400 })
  }
  try {
    const token = await getAccessToken()
    const statuses: Record<string, string> = {}
    await Promise.all(orderIds.map(async (id) => (statuses[id] = await getOrderStatus(token, id))))
    return Response.json({ statuses })
  } catch (err) {
    console.error('PayPal status check failed', err)
    return Response.json({ error: err instanceof Error ? err.message : 'Status check failed' }, { status: 502 })
  }
}

export const config: Config = {
  path: '/api/order-status',
  method: 'POST',
}
