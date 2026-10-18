import { NextResponse } from 'next/server'
import { isSafeId, proxyProjectRequest } from '@/lib/projectProxy'

const MODULES = ['content', 'actions', 'plan90', 'whatsapp', 'iaautomatizacion', 'metricasclave']

type Ctx = { params: { planId: string; action: string } }

const notFound = () => NextResponse.json({ detail: 'Not Found' }, { status: 404 })

// GET /api/marketing/{planId}/{módulo}: estado/resultado del job
export async function GET(_request: Request, { params }: Ctx) {
  if (!isSafeId(params.planId) || !MODULES.includes(params.action)) return notFound()
  return proxyProjectRequest('GET', `/marketing/${params.planId}/${params.action}`)
}

// POST /api/marketing/{planId}/execute-{módulo}: lanza el job (202)
export async function POST(_request: Request, { params }: Ctx) {
  const mod = params.action.replace(/^execute-/, '')
  if (!isSafeId(params.planId) || mod === params.action || !MODULES.includes(mod)) return notFound()
  return proxyProjectRequest('POST', `/marketing/${params.planId}/${params.action}`)
}
