'use client'

import { useEffect, useState } from 'react'
import { CreditCard, RefreshCw, AlertTriangle, Check, Zap, ExternalLink } from 'lucide-react'
import { api, type Plan, type UsageInfo } from '@/lib/api'

// ---------------------------------------------------------------------------
// Usage meter
// ---------------------------------------------------------------------------
function UsageMeter({
  label, used, limit,
}: { label: string; used: number; limit: number | 'unlimited' }) {
  const isUnlimited = limit === 'unlimited'
  const pct = isUnlimited ? 0 : Math.min(100, (used / (limit as number)) * 100)
  const color =
    isUnlimited ? '#22c97a' :
    pct >= 90   ? '#ff4d4d' :
    pct >= 70   ? '#f5a623' : '#4f7fff'

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-dim">{label}</span>
        <span className="font-mono text-xs" style={{ color }}>
          {used}{isUnlimited ? ' / ∞' : ` / ${limit}`}
        </span>
      </div>
      <div className="h-1.5 bg-s3 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: isUnlimited ? '100%' : `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Plan card
// ---------------------------------------------------------------------------
function PlanCard({
  plan, currentPlan, onUpgrade, loading,
}: {
  plan: Plan
  currentPlan: string | null
  onUpgrade: (planId: string) => void
  loading: boolean
}) {
  const isCurrent = currentPlan === plan.plan_id
  const isElite   = plan.plan_id === 'elite'

  return (
    <div className={[
      'card flex flex-col gap-4 transition-all',
      isCurrent ? 'border-accent ring-1 ring-accent/30' : '',
      isElite   ? 'border-success/40' : '',
    ].join(' ')}>
      {/* Header */}
      <div>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-muted font-mono uppercase tracking-wide">{plan.plan_id}</p>
            <p className="text-lg font-semibold mt-0.5">{plan.name}</p>
          </div>
          {isCurrent && (
            <span className="badge bg-accent/10 text-accent border border-accent/30">Activo</span>
          )}
        </div>
        <p className="text-2xl font-mono font-bold mt-2 text-[#e2e8f0]">
          ${plan.monthly_usd}
          <span className="text-sm text-muted font-sans font-normal">/mes</span>
        </p>
      </div>

      {/* Limits */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        {[
          ['Auditorías', plan.limits.audits_per_month],
          ['Fixes',      plan.limits.fixes_per_month],
          ['Agentes IA', plan.limits.agents_per_month],
          ['Reportes',   plan.limits.reports_per_month],
          ['Sitios',     plan.limits.sites],
        ].map(([k, v]) => (
          <div key={k as string} className="flex items-center gap-1.5 text-dim">
            <span className="w-1 h-1 rounded-full bg-accent flex-shrink-0" />
            <span>{k}: </span>
            <span className="font-mono font-medium text-[#e2e8f0]">
              {v === -1 ? '∞' : v}
            </span>
          </div>
        ))}
      </div>

      {/* Features */}
      <ul className="space-y-1.5 flex-1">
        {plan.features.map(f => (
          <li key={f} className="flex items-start gap-2 text-xs text-dim">
            <Check className="w-3.5 h-3.5 text-success flex-shrink-0 mt-0.5" />
            {f}
          </li>
        ))}
      </ul>

      {/* CTA */}
      <button
        className={[
          'w-full py-2 rounded-lg text-sm font-medium transition-colors',
          isCurrent
            ? 'bg-s3 text-muted cursor-default'
            : isElite
              ? 'bg-success hover:bg-success/90 text-white'
              : 'btn-primary',
        ].join(' ')}
        onClick={() => !isCurrent && onUpgrade(plan.plan_id)}
        disabled={isCurrent || loading}
      >
        {isCurrent ? 'Plan actual' : loading ? 'Procesando…' : `Activar ${plan.name}`}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function BillingPage() {
  const [plans,     setPlans]     = useState<Plan[]>([])
  const [usage,     setUsage]     = useState<UsageInfo | null>(null)
  const [clientId,  setClientId]  = useState('demo-client-001')
  const [editId,    setEditId]    = useState(false)
  const [tmpId,     setTmpId]     = useState('demo-client-001')
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)
  const [upgrading, setUpgrading] = useState(false)
  const [upMsg,     setUpMsg]     = useState<string | null>(null)
  const [checkout,  setCheckout]  = useState<{ url: string; note?: string } | null>(null)

  const loadData = async (id = clientId) => {
    setLoading(true)
    setError(null)
    try {
      const [p, u] = await Promise.all([api.listPlans(), api.getUsage(id)])
      setPlans(p.plans)
      setUsage(u)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const stored = localStorage.getItem('wpr_client_id') ?? 'demo-client-001'
    setClientId(stored)
    setTmpId(stored)
    loadData(stored)
  }, [])

  const handleUpgrade = async (planId: string) => {
    setUpgrading(true)
    setUpMsg(null)
    setCheckout(null)
    try {
      if (!usage || usage.status === 'no_subscription') {
        const res = await api.createCheckout(
          planId, clientId,
          `${window.location.origin}/billing?success=1`,
          `${window.location.origin}/billing?cancel=1`,
        )
        setCheckout({ url: res.checkout_url, note: res.note })
      } else {
        const res = await api.upgradePlan(clientId, planId)
        setUpMsg(`Plan actualizado: ${res.old_plan} → ${res.new_plan} (${res.mode})`)
        await loadData()
      }
    } catch (e: unknown) {
      setUpMsg(e instanceof Error ? e.message : 'Error')
    } finally {
      setUpgrading(false)
    }
  }

  const applyClientId = () => {
    setClientId(tmpId)
    localStorage.setItem('wpr_client_id', tmpId)
    setEditId(false)
    loadData(tmpId)
  }

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Billing</h1>
          <p className="text-dim text-sm mt-0.5">Gestión de plan y uso mensual</p>
        </div>
        <button className="btn-ghost border border-border flex items-center gap-2"
          onClick={() => loadData()} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Actualizar
        </button>
      </div>

      {/* Client ID */}
      <div className="card mb-5 flex flex-wrap items-center gap-3">
        <CreditCard className="w-4 h-4 text-accent flex-shrink-0" />
        <span className="text-xs text-muted">Client ID:</span>
        {editId ? (
          <>
            <input className="input w-56" value={tmpId} onChange={e => setTmpId(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && applyClientId()} autoFocus />
            <button className="btn-primary text-xs py-1" onClick={applyClientId}>Aplicar</button>
            <button className="btn-ghost text-xs" onClick={() => { setEditId(false); setTmpId(clientId) }}>
              Cancelar
            </button>
          </>
        ) : (
          <>
            <span className="font-mono text-sm text-[#e2e8f0]">{clientId}</span>
            <button className="btn-ghost text-xs" onClick={() => setEditId(true)}>Cambiar</button>
          </>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-danger/10 border border-danger/30 text-danger
                        text-sm rounded-lg px-4 py-3 mb-5">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {upMsg && (
        <div className="flex items-center gap-2 bg-success/10 border border-success/30 text-success
                        text-sm rounded-lg px-4 py-3 mb-5">
          <Check className="w-4 h-4" /> {upMsg}
        </div>
      )}

      {checkout && (
        <div className="bg-s2 border border-border rounded-xl p-4 mb-5">
          <p className="text-sm font-medium mb-1">Sesión de pago creada</p>
          {checkout.note && <p className="text-xs text-muted mb-3">{checkout.note}</p>}
          <a
            href={checkout.url} target="_blank" rel="noreferrer"
            className="btn-primary inline-flex items-center gap-2 text-sm"
          >
            <ExternalLink className="w-4 h-4" /> Ir al Checkout de Stripe
          </a>
        </div>
      )}

      {/* Current plan + usage */}
      {!loading && usage && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5 mb-8">
          {/* Usage meters */}
          <div className="card">
            <div className="flex items-center gap-2 mb-5">
              <Zap className="w-4 h-4 text-accent" />
              <h2 className="font-medium text-sm">Uso — {usage.period}</h2>
              <span className={[
                'badge ml-auto',
                usage.status === 'active' ? 'badge-done' :
                usage.status === 'past_due' ? 'badge-critica' :
                usage.status === 'canceled' ? 'badge-fail' : 'badge-baja',
              ].join(' ')}>{usage.status}</span>
            </div>
            {usage.plan ? (
              <div className="space-y-4">
                <UsageMeter label="Auditorías" used={usage.usage.audits.used}  limit={usage.usage.audits.limit} />
                <UsageMeter label="Fixes"      used={usage.usage.fixes.used}   limit={usage.usage.fixes.limit}  />
                <UsageMeter label="Agentes IA" used={usage.usage.agents.used}  limit={usage.usage.agents.limit} />
                <UsageMeter label="Reportes"   used={usage.usage.reports.used} limit={usage.usage.reports.limit} />
              </div>
            ) : (
              <p className="text-sm text-muted">Sin plan activo. Selecciona un plan abajo.</p>
            )}
          </div>

          {/* Current plan summary */}
          <div className="card">
            <p className="text-xs text-muted font-mono uppercase tracking-wide mb-3">Plan Actual</p>
            {usage.plan ? (
              <>
                {(() => {
                  const p = plans.find(x => x.plan_id === usage.plan)
                  return p ? (
                    <div>
                      <p className="text-2xl font-mono font-bold text-[#e2e8f0]">${p.monthly_usd}</p>
                      <p className="text-lg font-semibold mt-1">{p.name}</p>
                      <ul className="mt-4 space-y-1.5">
                        {p.features.slice(0, 4).map(f => (
                          <li key={f} className="flex items-start gap-2 text-xs text-dim">
                            <Check className="w-3.5 h-3.5 text-success flex-shrink-0 mt-0.5" />
                            {f}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null
                })()}
              </>
            ) : (
              <div className="flex flex-col items-center py-8 gap-2 text-center">
                <CreditCard className="w-8 h-8 text-muted" />
                <p className="text-dim text-sm">Sin suscripción activa</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Plans comparison */}
      <div className="mb-3">
        <h2 className="font-medium text-sm">Comparativa de Planes</h2>
        <p className="text-xs text-muted mt-0.5">Selecciona un plan para activarlo o hacer upgrade</p>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-80 bg-surface rounded-xl" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {plans.map(plan => (
            <PlanCard
              key={plan.plan_id}
              plan={plan}
              currentPlan={usage?.plan ?? null}
              onUpgrade={handleUpgrade}
              loading={upgrading}
            />
          ))}
        </div>
      )}

      {/* Stripe note */}
      <p className="text-xs text-muted mt-6 text-center">
        Pagos procesados por Stripe. En modo dev, las sesiones son mock.
        Configura <span className="font-mono">STRIPE_SECRET_KEY</span> en <span className="font-mono">api/.env</span> para pagos reales.
      </p>
    </>
  )
}
