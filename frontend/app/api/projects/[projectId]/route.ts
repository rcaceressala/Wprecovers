import { proxyProjectRequest } from '@/lib/projectProxy'

export async function GET(
  _request: Request,
  { params }: { params: { projectId: string } },
) {
  return proxyProjectRequest('GET', `/projects/${encodeURIComponent(params.projectId)}`)
}

export async function DELETE(
  _request: Request,
  { params }: { params: { projectId: string } },
) {
  return proxyProjectRequest('DELETE', `/projects/${encodeURIComponent(params.projectId)}`)
}
