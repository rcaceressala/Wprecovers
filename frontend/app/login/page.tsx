'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { Zap, Loader2, AlertCircle } from 'lucide-react'
import { login, isAuthenticated } from '@/lib/auth'

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isAuthenticated()) router.replace('/dashboard')
  }, [router])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const result = await login(email, password)

    if (!result.ok) {
      setError(result.error ?? 'No se pudo iniciar sesión')
      setLoading(false)
      return
    }

    router.replace('/dashboard')
    router.refresh()
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-12 h-12 bg-accent rounded-xl flex items-center justify-center shadow-glow">
            <Zap className="w-6 h-6 text-white" strokeWidth={2.5} />
          </div>
          <div className="text-center">
            <p className="font-mono text-lg font-medium text-[#e2e8f0] leading-none">WPRecover</p>
            <p className="text-xs text-muted mt-1">v2.0 Platform</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4 animate-fade-in">
          <div>
            <label htmlFor="email" className="block text-xs font-mono uppercase tracking-wide text-muted mb-1.5">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="contacto@wprecover.cl"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-mono uppercase tracking-wide text-muted mb-1.5">
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-danger bg-danger/10 border border-danger/20 rounded-lg px-3 py-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Iniciar sesión
          </button>
        </form>

        <p className="text-center text-[10px] text-muted font-mono mt-6">
          WPRecover 2.0 — WordPress &amp; WooCommerce Recovery Platform
        </p>
      </div>
    </div>
  )
}
