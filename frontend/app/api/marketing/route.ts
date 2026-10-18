import { proxyProjectRequest } from '@/lib/projectProxy'

export async function GET(request: Request) {
  const projectId = new URL(request.url).searchParams.get('project_id')
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return proxyProjectRequest('GET', `/marketing/${qs}`)
}
