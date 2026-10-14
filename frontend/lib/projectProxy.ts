import { cookies } from 'next/headers'
import { jwtVerify } from 'jose'
import { NextResponse } from 'next/server'

// Proxy server-side para los endpoints de /projects que ahora requieren auth
// de operador en el backend (hotfix de seguridad: create/list/get/audit-and-
// baseline/close/delete quedaron sin protección hasta hoy). Mantiene la
// X-Admin-Key fuera del navegador: la key vive solo en el servidor
// (WPREPRO_ADMIN_KEY) y la identidad del operador (X-Actor) se deriva del JWT
// de sesión ya emitido por /api/auth/login, no de un valor que mande el
// cliente. Mismo patrón que se usa para las acciones del Plan 90 días.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'https://wprecovers-v2.onrender.com'
const COOKIE_NAME = 'wpr_token'

type ProxyMethod = 'GET' | 'POST' | 'DELETE'

export async function proxyProjectRequest(
  method: ProxyMethod,
  path: string,
  body?: unknown,
): Promise<NextResponse> {
  const secret = process.env.JWT_SECRET
  const adminKey = process.env.WPREPRO_ADMIN_KEY

  if (!secret) {
    return NextResponse.json(
      { detail: 'Autenticación no configurada en el servidor (falta JWT_SECRET).' },
      { status: 500 },
    )
  }
  // Fail-closed, igual que el backend: sin key configurada la acción no se habilita.
  if (!adminKey) {
    return NextResponse.json(
      { detail: 'Acción deshabilitada: WPREPRO_ADMIN_KEY no configurada en el servidor.' },
      { status: 503 },
    )
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

  const upstream = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Key': adminKey,
      'X-Actor': actor,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  const data = await upstream.json().catch(() => ({}))
  return NextResponse.json(data, { status: upstream.status })
}
