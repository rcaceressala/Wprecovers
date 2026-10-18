import { proxyProjectRequest } from '@/lib/projectProxy'

// Auditoría en vivo + plan de 9 módulos con Claude: tarda minutos. 300 s es
// también el límite de espera de cabeceras del fetch de Node (undici).
export const maxDuration = 300

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}))
  return proxyProjectRequest('POST', '/marketing/generate', body)
}
