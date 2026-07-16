import { proxyProjectRequest } from '@/lib/projectProxy'

export async function GET() {
  return proxyProjectRequest('GET', '/projects/')
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  return proxyProjectRequest('POST', '/projects/', body)
}
