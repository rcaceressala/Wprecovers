import { proxyProjectsRequest } from '@/lib/projectsProxy'

// audit-and-baseline, close y full-report ejecutan auditorías / generan PDF en
// el backend y pueden tardar; 60s es el máximo válido en todos los planes de Vercel.
export const maxDuration = 60
export const dynamic = 'force-dynamic'

type Ctx = { params: { path?: string[] } }

export async function GET(request: Request, { params }: Ctx) {
  return proxyProjectsRequest(request, params.path)
}

export async function POST(request: Request, { params }: Ctx) {
  return proxyProjectsRequest(request, params.path)
}

export async function DELETE(request: Request, { params }: Ctx) {
  return proxyProjectsRequest(request, params.path)
}
