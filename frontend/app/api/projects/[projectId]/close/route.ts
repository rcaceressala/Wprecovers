import { proxyProjectRequest } from '@/lib/projectProxy'

export async function POST(
  _request: Request,
  { params }: { params: { projectId: string } },
) {
  return proxyProjectRequest('POST', `/projects/${encodeURIComponent(params.projectId)}/close`)
}
