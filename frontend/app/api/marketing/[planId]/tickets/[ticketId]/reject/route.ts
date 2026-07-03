import { proxyTicketAction } from '@/lib/ticketProxy'

export async function PATCH(
  request: Request,
  { params }: { params: { planId: string; ticketId: string } },
) {
  const body = await request.json().catch(() => ({} as { motivo?: string | null }))
  return proxyTicketAction(params.planId, params.ticketId, 'reject', body?.motivo ?? null)
}
