import { NextResponse } from 'next/server'
import { SignJWT } from 'jose'

export async function POST(request: Request) {
  const body = await request.json().catch(() => null)
  const email = body?.email
  const password = body?.password

  if (!email || !password) {
    return NextResponse.json({ error: 'Email y contraseña son requeridos' }, { status: 400 })
  }

  const adminEmail = process.env.ADMIN_EMAIL
  const adminPassword = process.env.ADMIN_PASSWORD
  const secret = process.env.JWT_SECRET

  if (!adminEmail || !adminPassword || !secret) {
    return NextResponse.json(
      { error: 'Autenticación no configurada en el servidor' },
      { status: 500 }
    )
  }

  if (email !== adminEmail || password !== adminPassword) {
    return NextResponse.json({ error: 'Email o contraseña incorrectos' }, { status: 401 })
  }

  const token = await new SignJWT({ email })
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime('24h')
    .sign(new TextEncoder().encode(secret))

  return NextResponse.json({ token })
}
