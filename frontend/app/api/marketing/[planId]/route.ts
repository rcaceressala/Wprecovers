import { NextResponse } from 'next/server'
import { isSafeId, proxyProjectRequest } from '@/lib/projectProxy'

export async function GET(
  _request: Request,
  { params }: { params: { planId: string } },
) {
  if (!isSafeId(params.planId)) return NextResponse.json({ detail: 'Not Found' }, { status: 404 })
  return proxyProjectRequest('GET', `/marketing/${params.planId}`)
}
