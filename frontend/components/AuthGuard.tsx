'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Loader2 } from 'lucide-react'
import { isAuthenticated, clearToken } from '@/lib/auth'

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const check = () => {
      if (!isAuthenticated()) {
        clearToken()
        router.replace('/login')
        return
      }
      setReady(true)
    }

    check()
    const interval = setInterval(check, 60_000)
    return () => clearInterval(interval)
  }, [router])

  if (!ready) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-bg">
        <Loader2 className="w-6 h-6 text-accent animate-spin" />
      </div>
    )
  }

  return <>{children}</>
}
