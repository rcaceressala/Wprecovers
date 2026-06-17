'use client'

import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw, AlertTriangle, RotateCcw, Inbox } from 'lucide-react'
import { api, PRIORIDAD_ORDER, type Ticket, type Prioridad, type FixLogEntry } from '@/lib/api'

const PRIO_CLS: Record<Prioridad, string> = {
  Critica: 'badge-critica', Alta: 'badge-alta', Media: 'badge-media', Baja: 'badge-baja',
}
const ESTADO_CLS: Record<string, string> = {
  OPEN: 'badge-open', IN_PROGRESS: 'badge-prog', DONE: 'badge-done', FAIL: 'badge-fail',
}

// ---------------------------------------------------------------------------
// Expandable ticket row
// ---------------------------------------------------------------------------
function TicketRow({ ticket }: { ticket: Ticket }) {
  const [open,     setOpen]     = useState(false)
  const [log,      setLog]      = useState<FixLogEntry[]>([])
  const [logLoad,  setLogLoad]  = useState(false)
  const [rolling,  setRolling]  = useState(false)
  const [rollMsg,  setRollMsg]  = useState<string | null>(null)

  const loadLog = async () => {
    if (log.length > 0 || logLoad) return
    setLogLoad(true)
    try {
      const res = await api.getFixLog(ticket.id)
      setLog(res.log)
    } catch {
      // 404 = no fixes yet, silently ignore
    } finally {
      setLogLoad(false)
    }
  }

  const toggle = () => {
    setOpen(o => !o)
    if (!open) loadLog()
  }

  const handleRollback = async () => {
    setRolling(true)
    setRollMsg(null)
    try {
      const res = await api.rollbackFix(ticket.id)
      setRollMsg(`Rollback: ${res.status} — ${res.timestamp}`)
      await loadLog()
    } catch (e: unknown) {
      setRollMsg(e instanceof Error ? e.message : 'Error al hacer rollback')
    } finally {
      setRolling(false)
    }
  }

  const lastApplied = log.find(l => l.status === 'APPLIED')

  return (
    <>
      <tr className="border-b border-border/50 hover:bg-s2 transition-colors cursor-pointer"
          onClick={toggle}>
        <td className="py-3 px-3">
          {open
            ? <ChevronDown className="w-3.5 h-3.5 text-muted" />
            : <ChevronRight className="w-3.5 h-3.5 text-muted" />}
        </td>
        <td className="py-3 px-2 font-mono text-xs text-dim whitespace-nowrap">{ticket.id}</td>
        <td className="py-3 px-2 text-xs text-dim whitespace-nowrap">{ticket.categoria}</td>
        <td className="py-3 px-2 text-xs max-w-[240px] truncate">{ticket.titulo}</td>
        <td className="py-3 px-2"><span className={PRIO_CLS[ticket.prioridad]}>{ticket.prioridad}</span></td>
        <td className="py-3 px-2"><span className={ESTADO_CLS[ticket.estado]}>{ticket.estado}</span></td>
        <td className="py-3 px-2 font-mono text-xs text-dim">{ticket.estimacion}m</td>
      </tr>

      {open && (
        <tr className="bg-s2 border-b border-border">
          <td colSpan={7} className="px-4 py-4">
            {/* Ticket details */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <p className="text-xs text-muted mb-1 font-mono uppercase tracking-wide">Impacto</p>
                <p className="text-sm text-dim">{ticket.impacto}</p>
              </div>
              <div>
                <p className="text-xs text-muted mb-1 font-mono uppercase tracking-wide">Agente</p>
                <p className="text-sm text-dim font-mono">{ticket.agente}</p>
              </div>
            </div>

            {/* Fix history */}
            <p className="text-xs text-muted mb-2 font-mono uppercase tracking-wide">
              Historial de Fixes ({log.length})
            </p>

            {logLoad ? (
              <div className="flex items-center gap-2 text-xs text-muted py-2">
                <RefreshCw className="w-3 h-3 animate-spin" /> Cargando historial…
              </div>
            ) : log.length === 0 ? (
              <p className="text-xs text-muted italic">Sin fixes aplicados aún.</p>
            ) : (
              <div className="space-y-2 mb-4">
                {log.map((entry, i) => (
                  <div key={i} className="bg-surface border border-border rounded-lg px-3 py-2.5 text-xs">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={
                        entry.status === 'APPLIED'      ? 'badge-done' :
                        entry.status === 'ROLLED_BACK'  ? 'badge-media' :
                        entry.status === 'FAILED'       ? 'badge-fail' : 'badge-open'
                      }>{entry.status}</span>
                      <span className="font-mono text-dim">{entry.check_name}</span>
                      <span className="text-muted">{entry.metodo}</span>
                      <span className="text-muted ml-auto">{entry.timestamp.slice(0, 16).replace('T', ' ')}</span>
                    </div>
                    {entry.fix_payload?.command && (
                      <pre className="mt-2 bg-bg rounded p-2 text-[11px] text-dim overflow-x-auto">
                        {entry.fix_payload.command}
                      </pre>
                    )}
                    {entry.error && (
                      <p className="mt-1 text-danger/80 text-[11px]">{entry.error}</p>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Rollback button */}
            {lastApplied && (
              <div className="flex items-center gap-3">
                <button
                  className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg
                             bg-warn/10 text-warn border border-warn/30 hover:bg-warn/20 transition-colors
                             disabled:opacity-50"
                  onClick={handleRollback}
                  disabled={rolling}
                >
                  {rolling
                    ? <><RefreshCw className="w-3 h-3 animate-spin" /> Revirtiendo…</>
                    : <><RotateCcw className="w-3 h-3" /> Rollback</>}
                </button>
                {rollMsg && <p className="text-xs text-dim">{rollMsg}</p>}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function TicketsPage() {
  const [tickets,     setTickets]     = useState<Ticket[]>([])
  const [loading,     setLoading]     = useState(true)
  const [prioFlt,     setPrioFlt]     = useState<string>('all')
  const [stateFlt,    setStateFlt]    = useState<string>('all')
  const [projectName, setProjectName] = useState<string | null>(null)
  const [projectUrl,  setProjectUrl]  = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem('wpr_last_audit')
    if (stored) {
      const parsed = JSON.parse(stored)
      setTickets(parsed.tickets ?? [])
    }
    const activeProject = localStorage.getItem('wpr_active_project')
    if (activeProject) {
      const parsed = JSON.parse(activeProject)
      setProjectName(parsed.client_name ?? null)
      setProjectUrl(parsed.site_url ?? null)
    }
    setLoading(false)
  }, [])

  const filtered = tickets
    .filter(t => prioFlt  === 'all' || t.prioridad === prioFlt)
    .filter(t => stateFlt === 'all' || t.estado    === stateFlt)
    .sort((a, b) => PRIORIDAD_ORDER[a.prioridad] - PRIORIDAD_ORDER[b.prioridad])

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Tickets</h1>
          {projectName && (
            <p className="text-dim text-sm mt-0.5">
              📁 Proyecto: {projectName} — {projectUrl}
            </p>
          )}
          <p className="text-dim text-sm mt-0.5">
            {tickets.length} tickets · {filtered.length} mostrados
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted">Prioridad</label>
          <select className="select w-auto"
            value={prioFlt} onChange={e => setPrioFlt(e.target.value)}>
            <option value="all">Todas</option>
            {['Critica','Alta','Media','Baja'].map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-muted">Estado</label>
          <select className="select w-auto"
            value={stateFlt} onChange={e => setStateFlt(e.target.value)}>
            <option value="all">Todos</option>
            {['OPEN','IN_PROGRESS','DONE','FAIL'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-surface rounded-lg" />)}
        </div>
      ) : tickets.length === 0 ? (
        <div className="flex flex-col items-center py-24 gap-3 text-center">
          <Inbox className="w-10 h-10 text-muted" />
          <p className="text-dim text-sm">No hay tickets.</p>
          <a href="/dashboard" className="btn-primary text-sm">Ir al Dashboard → Run Audit</a>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[680px]">
              <thead>
                <tr className="border-b border-border bg-s2 text-left">
                  <th className="pb-3 pt-3 px-3 w-6" />
                  {['ID','Categoría','Título','Prioridad','Estado','Est.'].map(h => (
                    <th key={h} className="pb-3 pt-3 px-2 text-xs text-muted font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-10 text-muted text-sm">
                      Sin resultados para los filtros aplicados
                    </td>
                  </tr>
                ) : (
                  filtered.map(t => <TicketRow key={t.id} ticket={t} />)
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
