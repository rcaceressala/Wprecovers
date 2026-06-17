'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import {
  LayoutDashboard, FolderOpen, Ticket, ShieldCheck, Bot, CreditCard,
  Menu, X, Zap, LogOut,
} from 'lucide-react'
import { RecoveryGauge } from './RecoveryGauge'
import { logout } from '@/lib/auth'

const NAV = [
  { href: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { href: '/projects',  icon: FolderOpen,      label: 'Proyectos' },
  { href: '/tickets',   icon: Ticket,          label: 'Tickets'   },
  { href: '/qa',        icon: ShieldCheck,      label: 'QA'        },
  { href: '/agents',    icon: Bot,              label: 'Agentes IA'},
  { href: '/billing',   icon: CreditCard,       label: 'Billing'   },
]

export function Sidebar() {
  const pathname = usePathname()
  const [open,  setOpen]  = useState(false)
  const [score, setScore] = useState<number | null>(null)

  useEffect(() => {
    const load = () => {
      const stored = localStorage.getItem('wpr_last_audit')
      if (stored) setScore(JSON.parse(stored).recovery_score ?? null)
    }
    load()
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ recovery_score: number }>).detail
      if (detail?.recovery_score != null) setScore(detail.recovery_score)
    }
    window.addEventListener('wpr_audit_updated', handler)
    return () => window.removeEventListener('wpr_audit_updated', handler)
  }, [])

  const Inner = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-5 py-5 flex items-center gap-3 border-b border-border">
        <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center flex-shrink-0">
          <Zap className="w-4 h-4 text-white" strokeWidth={2.5} />
        </div>
        <div>
          <p className="font-mono text-sm font-medium text-[#e2e8f0] leading-none">WPRecover</p>
          <p className="text-[10px] text-muted mt-0.5">v2.0 Platform</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={[
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all',
                active
                  ? 'bg-accent/10 text-accent font-medium'
                  : 'text-muted hover:text-[#e2e8f0] hover:bg-s2',
              ].join(' ')}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
              {active && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-accent" />
              )}
            </Link>
          )
        })}
      </nav>

      {/* Mini gauge */}
      {score !== null && (
        <div className="px-4 pb-3 pt-2 border-t border-border">
          <p className="text-[10px] text-muted mb-2 font-mono uppercase tracking-wide">
            Recovery Score
          </p>
          <RecoveryGauge score={score} size="sm" />
        </div>
      )}

      {/* Footer */}
      <div className="px-5 py-3 border-t border-border space-y-2">
        <button
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-muted hover:text-danger hover:bg-s2 transition-all w-full"
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          Cerrar sesión
        </button>
        <p className="text-[10px] text-muted font-mono px-3">
          API: {process.env.NEXT_PUBLIC_API_URL ?? 'https://wprecovers.onrender.com'}
        </p>
      </div>
    </div>
  )

  return (
    <>
      {/* Mobile toggle */}
      <button
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-surface border border-border rounded-lg"
        onClick={() => setOpen(o => !o)}
        aria-label="Toggle menu"
      >
        {open ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
      </button>

      {/* Overlay */}
      {open && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={[
          'fixed md:sticky top-0 left-0 z-40 h-screen',
          'w-64 bg-surface border-r border-border flex-shrink-0',
          'transition-transform duration-200',
          open ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        ].join(' ')}
      >
        <Inner />
      </aside>
    </>
  )
}
