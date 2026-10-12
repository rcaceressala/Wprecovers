import { cookies } from 'next/headers'
import { jwtVerify } from 'jose'
import { NextResponse } from 'next/server'

// Proxy server-side para las rutas /projects/* del backend (M9). Mismo modelo
// que lib/ticketProxy.ts: la X-Admin-Key vive solo en el servidor
// (WPREPRO_ADMIN_KEY) y X-Actor se deriva del JWT de sesión (cookie wpr_token)
// emitido por /api/auth/login — nunca de un valor que mande el cliente.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://wprecovers.onrender.com'
const COOKIE_NAME = 'wpr_token'

// Cada segmento debe ser un id/nombre de ruta simple. Evita que '..' u otros
// caracteres hagan que la URL upstream se normalice fuera de /projects/ y la
// admin key termine inyectada en otro endpoint del backend.
const SAFE_SEGMENT = /^[A-Za-z0-9_-]+$/

// Cabeceras de la respuesta upstream que se reenvían al navegador (JSON y PDF).
const PASSTHROUGH_HEADERS = ['content-type', 'content-disposition']

export async function proxyProjectsRequest(
  request: Request,
  segments: string[] = [],
): Promise<NextResponse> {
  const secret = process.env.JWT_SECRET
  const adminKey = process.env.WPREPRO_ADMIN_KEY

  if (!secret) {
    return NextResponse.json(
      { detail: 'Autenticación no configurada en el servidor (falta JWT_SECRET).' },
      { status: 500 },
    )
  }
  // Fail-closed, igual que el backend: sin key configurada no se habilita.
  if (!adminKey) {
    return NextResponse.json(
      { detail: 'Proyectos deshabilitados: WPREPRO_ADMIN_KEY no configurada en el servidor.' },
      { status: 503 },
    )
  }

  if (!segments.every(s => SAFE_SEGMENT.test(s))) {
    return NextResponse.json({ detail: 'Ruta inválida.' }, { status: 400 })
  }

  const token = cookies().get(COOKIE_NAME)?.value
  if (!token) {
    return NextResponse.json({ detail: 'No autenticado.' }, { status: 401 })
  }

  let actor = ''
  try {
    const { payload } = await jwtVerify(token, new TextEncoder().encode(secret))
    if (typeof payload.email === 'string') actor = payload.email.trim()
  } catch {
    return NextResponse.json({ detail: 'Sesión inválida o expirada.' }, { status: 401 })
  }
  if (!actor) {
    return NextResponse.json({ detail: 'El token de sesión no incluye la identidad del operador.' }, { status: 401 })
  }

  // La raíz va con barra final (/projects/) para evitar el 307 de FastAPI.
  const path = segments.length ? `/projects/${segments.join('/')}` : '/projects/'
  const search = new URL(request.url).search
  const body = request.method === 'GET' || request.method === 'HEAD'
    ? undefined
    : (await request.text()) || undefined

  let upstream: Response
  try {
    upstream = await fetch(`${API_URL}${path}${search}`, {
      method: request.method,
      headers: {
        'Content-Type': 'application/json',
        'X-Admin-Key': adminKey,
        'X-Actor': actor,
      },
      body,
      cache: 'no-store',
    })
  } catch {
    return NextResponse.json({ detail: 'No se pudo contactar con el backend.' }, { status: 502 })
  }

  const headers = new Headers()
  for (const name of PASSTHROUGH_HEADERS) {
    const value = upstream.headers.get(name)
    if (value) headers.set(name, value)
  }
  return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers })
}
