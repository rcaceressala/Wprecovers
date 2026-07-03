import { proxyTicketAction } from '@/lib/ticketProxy'

export async function PATCH(
  _request: Request,
  { params }: { params: { planId: string; ticketId: string } },
) {
  return proxyTicketAction(params.planId, params.ticketId, 'approve')
}
