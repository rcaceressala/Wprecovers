'use client'

import { useEffect, useState } from 'react'
import {
  Play, Download, Wrench, AlertTriangle, RefreshCw,
  Zap, CheckCircle, Clock, XCircle,
} from 'lucide-react'
import { RecoveryGauge } from '@/components/RecoveryGauge'
import {
  api, DEMO_AUDIT, scoreColor,
  type TicketResponse, type Ticket, type Prioridad, type AuditInput,
} from '@/lib/api'

// ---------------------------------------------------------------------------
// Prioridad / Estado badge helpers
// ---------------------------------------------------------------------------
const PRIO_CLS: Record<Prioridad, string> = {
  Critica: 'badge-critica',
  Alta:    'badge-alta',
  Media:   'badge-media',
  Baja:    'badge-baja',
}
const ESTADO_CLS: Record<string, string> = {
  OPEN:        'badge-open',
  IN_PROGRESS: 'badge-prog',
  DONE:        'badge-done',
  FAIL:        'badge-fail',
}

// ---------------------------------------------------------------------------
// Metric card
// ---------------------------------------------------------------------------
function MetricCard({
  label, value, icon: Icon, color, sub,
}: {
  label: string; value: number | string; icon: React.ElementType; color: string; sub?: string
}) {
  return (
    <div className="card flex items-start gap-4">
      <div className="p-2.5 rounded-lg" style={{ background: `${color}18` }}>
        <Icon className="w-5 h-5" style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-dim text-xs font-medium">{label}</p>
        <p className="text-2xl font-mono font-bold mt-0.5" style={{ color }}>{value}</p>
        {sub && <p className="text-xs text-muted mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

const DEMO_URL = 'https://demo.wprecover.cl'

// ---------------------------------------------------------------------------
// Audit modal
// ---------------------------------------------------------------------------
function AuditModal({
  onClose, onRun, running,
}: {
  onClose: () => void
  onRun: (url: string) => void
  running: boolean
}) {
  const [url, setUrl] = useState(DEMO_URL)
  const isDemo = url.trim() === DEMO_URL || url.trim() === ''

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={!running ? onClose : undefined} />
      <div className="relative bg-surface border border-border rounded-2xl p-6 w-full max-w-md shadow-2xl animate-slide-in">
        <h3 className="text-base font-semibold mb-1">Ejecutar Auditoría</h3>
        <p className="text-dim text-sm mb-4">
          Genera tickets de recuperación basados en el análisis del sitio.
        </p>

        <label className="text-xs text-muted mb-1.5 block">URL del sitio</label>
        <input
          className="input mb-3"
          value={url}
          onChange={e => setUrl(e.target.value)}
          placeholder="https://tusitio.cl"
          disabled={running}
        />

        {isDemo ? (
          <div className="bg-s2 rounded-lg p-3 mb-4 text-xs text-dim">
            <p className="font-mono text-[11px] text-muted mb-1">DEMO — checks predefinidos:</p>
            <div className="grid grid-cols-2 gap-1">
              {Object.entries(DEMO_AUDIT.checks).map(([cat, checks]) => {
                const failed = Object.values(checks as Record<string, boolean>).filter(v => !v).length
                return (
                  <span key={cat} className={failed > 0 ? 'text-danger/80' : 'text-success/80'}>
                    {cat}: {failed} fallos
                  </span>
                )
              })}
            </div>
          </div>
        ) : (
          <div className="bg-accent/5 border border-accent/20 rounded-lg p-3 mb-4">
            <p className="text-xs text-accent font-medium mb-0.5">Auditoría Real</p>
            <p className="text-[11px] text-dim">
              Analiza PageSpeed Insights + HTML en tiempo real. Proceso: ~10–20s.
            </p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 mt-2 text-[10px] text-muted font-mono">
              <span>✓ LCP / CLS / INP</span>
              <span>✓ Títulos SEO / H1</span>
              <span>✓ SSL / Headers HTTP</span>
              <span>✓ CTAs / WhatsApp</span>
              <span>✓ Schema / Canonical</span>
              <span>✓ WooCommerce</span>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <button className="btn-primary flex-1 flex items-center justify-center gap-2"
            onClick={() => onRun(url.trim() || DEMO_URL)} disabled={running}>
            {running
              ? <><RefreshCw className="w-4 h-4 animate-spin" />{isDemo ? 'Procesando…' : 'Analizando sitio…'}</>
              : <><Play className="w-4 h-4" />{isDemo ? 'Generar Demo' : 'Analizar Sitio'}</>}
          </button>
          <button className="btn-ghost" onClick={onClose} disabled={running}>Cancelar</button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function DashboardPage() {
  const [data,    setData]    = useState<TicketResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)
  const [modal,   setModal]   = useState(false)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem('wpr_last_audit')
    if (stored) setData(JSON.parse(stored))
    setLoading(false)
  }, [])

  async function handleRunAudit(url: string) {
    setRunning(true)
    setError(null)
    try {
      let result: TicketResponse
      if (url === DEMO_URL) {
        const input: AuditInput = { ...DEMO_AUDIT, url }
        result = await api.generateTickets(input)
      } else {
        result = await api.runAudit(url)
      }
      localStorage.setItem('wpr_last_audit', JSON.stringify(result))
      window.dispatchEvent(new CustomEvent('wpr_audit_updated', { detail: result }))
      setData(result)
      setModal(false)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al conectar con la API')
    } finally {
      setRunning(false)
    }
  }

  const tickets  = data?.tickets ?? []
  const resumen  = data?.resumen
  const inProg   = tickets.filter(t => t.estado === 'IN_PROGRESS').length
  const resolved = tickets.filter(t => t.estado === 'DONE').length

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-dim text-sm mt-0.5">
            {data?.url ?? 'Sin auditoría activa'}
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary flex items-center gap-2"
            onClick={() => setModal(true)}>
            <Play className="w-4 h-4" /> Run Audit
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-danger/10 border border-danger/30 text-danger
                        text-sm rounded-lg px-4 py-3 mb-6">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {error} — ¿Está corriendo la API en {process.env.NEXT_PUBLIC_API_URL ?? 'https://wprecovers.onrender.com'}?
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 animate-pulse">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="card h-32 bg-s2" />
          ))}
        </div>
      ) : !data ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-32 gap-5">
          <div className="w-16 h-16 bg-s2 rounded-2xl flex items-center justify-center border border-border">
            <Zap className="w-7 h-7 text-accent" />
          </div>
          <div className="text-center">
            <h2 className="text-lg font-semibold">Sin datos de auditoría</h2>
            <p className="text-dim text-sm mt-1 max-w-sm">
              Ejecuta tu primera auditoría para ver el Recovery Score y los tickets de tu sitio.
            </p>
          </div>
          <button className="btn-primary flex items-center gap-2 text-base px-6 py-2.5"
            onClick={() => setModal(true)}>
            <Play className="w-4 h-4" /> Ejecutar Auditoría Demo
          </button>
        </div>
      ) : (
        <>
          {/* Top section: gauge + metric cards */}
          <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-4 mb-6">
            {/* Gauge */}
            <div className="card flex items-center justify-center px-8 py-4">
              <RecoveryGauge score={data.recovery_score} size="lg" />
            </div>

            {/* Metric cards */}
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              <MetricCard
                label="Total Tickets" value={resumen?.total ?? 0}
                icon={Wrench} color="#4f7fff"
                sub={`~${resumen?.estimacion_total_min ?? 0} min`}
              />
              <MetricCard
                label="Críticos" value={resumen?.criticos ?? 0}
                icon={XCircle} color="#ff4d4d"
                sub={`${resumen?.altos ?? 0} altos`}
              />
              <MetricCard
                label="En Progreso" value={inProg}
                icon={Clock} color="#f5a623"
                sub="tickets activos"
              />
              <MetricCard
                label="Resueltos" value={resolved}
                icon={CheckCircle} color="#22c97a"
                sub={`de ${resumen?.total ?? 0} total`}
              />
            </div>
          </div>

          {/* Tickets table */}
          <div className="card mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-medium text-sm">Tickets Recientes</h2>
              <a href="/tickets" className="text-xs text-accent hover:underline">Ver todos →</a>
            </div>
            <div className="overflow-x-auto -mx-1">
              <table className="w-full text-sm min-w-[640px]">
                <thead>
                  <tr className="border-b border-border text-left">
                    {['ID','Categoría','Título','Prioridad','Estado','Est.'].map(h => (
                      <th key={h} className="pb-3 px-2 text-xs text-muted font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tickets.slice(0, 6).map((t: Ticket) => (
                    <tr key={t.id} className="border-b border-border/50 table-row-hover">
                      <td className="py-3 px-2 font-mono text-xs text-dim">{t.id}</td>
                      <td className="py-3 px-2">
                        <span className="text-xs text-dim">{t.categoria}</span>
                      </td>
                      <td className="py-3 px-2 max-w-[220px] truncate text-xs">{t.titulo}</td>
                      <td className="py-3 px-2">
                        <span className={PRIO_CLS[t.prioridad]}>{t.prioridad}</span>
                      </td>
                      <td className="py-3 px-2">
                        <span className={ESTADO_CLS[t.estado]}>{t.estado}</span>
                      </td>
                      <td className="py-3 px-2 font-mono text-xs text-dim">{t.estimacion}m</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Quick actions */}
          <div className="flex flex-wrap gap-3">
            <button className="btn-primary flex items-center gap-2"
              onClick={() => setModal(true)}>
              <Play className="w-4 h-4" /> Run Audit
            </button>
            <a href="/tickets"
              className="btn-ghost flex items-center gap-2 border border-border">
              <Wrench className="w-4 h-4" /> Apply Fix
            </a>
            <a href={api.downloadPDFUrl(tickets[0]?.id ?? 'none')} target="_blank" rel="noreferrer"
              className="btn-ghost flex items-center gap-2 border border-border">
              <Download className="w-4 h-4" /> Download Report
            </a>
          </div>
        </>
      )}

      {modal && (
        <AuditModal onClose={() => setModal(false)} onRun={handleRunAudit} running={running} />
      )}
    </>
  )
}
