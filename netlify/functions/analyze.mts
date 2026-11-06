import type { Config, Context } from '@netlify/functions'
import { GoogleGenAI } from '@google/genai'
import { createOrder, getAccessToken } from '../lib/paypal.mts'

type Split = { person: string; amount_owed: number; items_summary: string }

export default async (req: Request, context: Context) => {
  let body: { image?: string; mimeType?: string; instructions?: string }
  try {
    body = await req.json()
  } catch {
    return Response.json({ error: 'Invalid JSON body' }, { status: 400 })
  }
  const { image, mimeType = 'image/jpeg', instructions = '' } = body
  if (!image) return Response.json({ error: 'Please upload a receipt image.' }, { status: 400 })

  const prompt = `
You are an AI Financial Split-Pay Agent.
1. Read the uploaded receipt or bill image carefully. Convert amounts to USD if needed or treat numbers as USD for payment processing.
2. Read the user's split instructions: "${instructions.slice(0, 2000)}"
3. Calculate exact shares (including proportional tax/tip if applicable) for each person mentioned.
4. Return ONLY valid JSON matching this exact structure:
{
  "merchant": "Name of restaurant/store",
  "total_bill": 0.00,
  "items_detected": [
    {"item": "Item name", "price": 0.00, "assigned_to": "Names"}
  ],
  "splits": [
    {"person": "Person Name", "amount_owed": 0.00, "items_summary": "Short summary of items"}
  ]
}`

  let result: { merchant?: string; total_bill?: number; items_detected?: unknown[]; splits?: Split[] }
  try {
    const ai = new GoogleGenAI({})
    const response = await ai.models.generateContent({
      model: 'gemini-3.8-flash',
      contents: [{ role: 'user', parts: [{ inlineData: { mimeType, data: image } }, { text: prompt }] }],
      config: { responseMimeType: 'application/json' },
    })
    result = JSON.parse(response.text || '{}')
  } catch (err) {
    console.error('Gemini analysis failed', err)
    return Response.json({ error: 'The AI could not analyze this receipt. Please try another image.' }, { status: 502 })
  }

  const orders: Record<string, { order_id: string; approve_link: string | null; status: string }> = {}
  let paypalError: string | null = null
  const payable = (result.splits || []).filter((s) => Number(s.amount_owed) > 0)
  if (payable.length) {
    try {
      const token = await getAccessToken()
      const siteUrl = new URL(req.url).origin
      for (const s of payable) {
        orders[s.person] = await createOrder(token, s.person, Number(s.amount_owed), s.items_summary || '', siteUrl)
      }
    } catch (err) {
      console.error('PayPal order creation failed', err)
      paypalError = err instanceof Error ? err.message : 'PayPal order creation failed'
    }
  }

  return Response.json({ split_data: result, paypal_orders: orders, paypal_error: paypalError })
}

export const config: Config = {
  path: '/api/analyze',
  method: 'POST',
}
