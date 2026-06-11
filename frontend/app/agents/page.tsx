'use client'

import { useEffect, useState } from 'react'
import {
  Play, RefreshCw, AlertTriangle, ChevronDown, ChevronRight,
  Bot, Sparkles, Clock, Inbox, CheckCircle, XCircle, Wrench,
} from 'lucide-react'
import {
  api,
  type AgentInfo, type AgentResponse, type Ticket, type SiteContext,
  type PendingFix,
} from '@/lib/api'

const SCOPE_COLOR: Record<string, string> = {
  SEO:          '#4f7fff',
  Performance:  '#f5a623',
  Conversion:   '#22c97a',
  Seguridad:    '#ff4d4d',
  WooCommerce:  '#a78bfa',
  Reportes:     '#94a3b8',
  'Prospección':'#fb923c',
}

// ---------------------------------------------------------------------------
// Agent info card
// ---------------------------------------------------------------------------
function AgentCard({ agent }: { agent: AgentInfo }) {
  const col = SCOPE_COLOR[agent.scope] ?? '#6b7280'
  return (
    <div className="card flex items-center gap-3 py-3">
      <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
           style={{ background: `${col}18` }}>
        <Bot className="w-4 h-4" style={{ color: col }} />
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium text-[#e2e8f0]">{agent.nombre}</p>
        <p className="text-xs text-muted">{agent.scope}</p>
      </div>
      <span className="ml-auto text-[10px] font-mono text-muted">{agent.model.split('-').slice(-2).join('-')}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pending fix approval card (WPRepro Agent plugin)
// ---------------------------------------------------------------------------
function PendingFixCard({
  pendingFix, ticketId, onChange,
}: { pendingFix: PendingFix; ticketId: string; onChange: (updated: PendingFix | null) => void }) {
  const [loading, setLoading] = useState<'approve' | 'reject' | null>(null)
  const [actionErr, setActionErr] = useState<string | null>(null)

  const handleApprove = async () => {
    setLoading('approve')
    setActionErr(null)
    try {
      const updated = await api.approveFix(ticketId)
      onChange(updated)
    } catch (e: unknown) {
      setActionErr(e instanceof Error ? e.message : 'Error al aprobar el fix')
    } finally {
      setLoading(null)
    }
  }

  const handleReject = async () => {
    setLoading('reject')
    setActionErr(null)
    try {
      await api.rejectFix(ticketId)
      onChange(null)
    } catch (e: unknown) {
      setActionErr(e instanceof Error ? e.message : 'Error al rechazar el fix')
    } finally {
      setLoading(null)
    }
  }

  if (pendingFix.status === 'error') {
    return (
      <div className="flex items-center gap-2 bg-danger/10 border border-danger/30 text-danger
                      text-sm rounded-lg px-3 py-2 mb-4">
        <XCircle className="w-4 h-4 flex-shrink-0" />
        No se pudo preparar el fix: {pendingFix.error ?? 'error desconocido'}
      </div>
    )
  }

  if (pendingFix.status === 'applied') {
    const results = (pendingFix.approval_results ?? {}) as {
      wp_cli?: { command: string; output: string; status: 'ok' | 'error' }[]
      snippet?: { snippet_id: number; status: string }
    }
    return (
      <div className="mb-4">
        <div className="flex items-center gap-2 bg-success/10 border border-success/30 text-success
                        text-sm rounded-lg px-3 py-2 mb-2">
          <CheckCircle className="w-4 h-4 flex-shrink-0" />
          ✅ Fix aplicado automáticamente
          {pendingFix.site_url && <span className="text-xs opacity-80">— {pendingFix.site_url}</span>}
        </div>
        {(results.wp_cli?.length ?? 0) > 0 && (
          <ul className="space-y-1">
            {results.wp_cli!.map((r, i) => (
              <li key={i} className="font-mono text-[11px] text-dim flex items-start gap-2">
                {r.status === 'ok'
                  ? <CheckCircle className="w-3 h-3 text-success flex-shrink-0 mt-0.5" />
                  : <XCircle className="w-3 h-3 text-danger flex-shrink-0 mt-0.5" />}
                <span className="break-all">{r.command} — {r.output}</span>
              </li>
            ))}
          </ul>
        )}
        {results.snippet && (
          <p className="font-mono text-[11px] text-dim flex items-center gap-2 mt-1">
            <CheckCircle className="w-3 h-3 text-success flex-shrink-0" />
            Snippet PHP #{results.snippet.snippet_id} activado en el sitio
          </p>
        )}
      </div>
    )
  }

  // status === 'pending'
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 bg-accent/10 border border-accent/30 text-accent
                      text-sm rounded-lg px-3 py-2 mb-2">
        <Wrench className="w-4 h-4 flex-shrink-0" />
        Fix listo para aplicar
        {pendingFix.site_url && <span className="text-xs opacity-80">— {pendingFix.site_url}</span>}
      </div>

      {pendingFix.php_snippet && (
        <>
          <p className="text-[10px] text-muted font-mono uppercase tracking-wide mb-1.5">Preview del código PHP</p>
          <pre className="bg-bg border border-border rounded-lg p-3 text-xs text-dim
                          overflow-x-auto whitespace-pre-wrap mb-2">
            {pendingFix.php_snippet}
          </pre>
        </>
      )}

      {pendingFix.wp_cli_commands.length > 0 && (
        <ul className="space-y-1 mb-2">
          {pendingFix.wp_cli_commands.map((c, i) => (
            <li key={i} className="font-mono text-[11px] text-dim break-all">$ {c}</li>
          ))}
        </ul>
      )}

      {actionErr && <p className="text-xs text-danger mb-2">{actionErr}</p>}

      <div className="flex gap-2">
        <button
          className="flex items-center gap-2 bg-success/10 hover:bg-success/20 border border-success/30
                     text-success text-sm font-medium rounded-lg px-3 py-1.5 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={handleApprove}
          disabled={loading !== null}
        >
          {loading === 'approve'
            ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            : null}
          ✓ Aprobar y aplicar
        </button>
        <button
          className="flex items-center gap-2 bg-danger/10 hover:bg-danger/20 border border-danger/30
                     text-danger text-sm font-medium rounded-lg px-3 py-1.5 transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={handleReject}
          disabled={loading !== null}
        >
          {loading === 'reject'
            ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            : null}
          ✗ Rechazar
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recommendation display
// ---------------------------------------------------------------------------
function RecommendationCard({
  res, onPendingFixChange,
}: { res: AgentResponse; onPendingFixChange: (updated: PendingFix | null) => void }) {
  const col = SCOPE_COLOR[res.scope] ?? '#6b7280'
  return (
    <div className="card border-l-4 animate-slide-in" style={{ borderLeftColor: col }}>
      <div className="flex items-center gap-2 mb-3">
        <Bot className="w-4 h-4" style={{ color: col }} />
        <span className="font-medium text-sm">{res.agent}</span>
        <span className="badge-baja ml-auto">{res.prioridad}</span>
        <span className="text-[10px] font-mono text-muted">{res.tokens_used} tokens</span>
      </div>

      {/* Recommendations */}
      <p className="text-[10px] text-muted font-mono uppercase tracking-wide mb-2">Recomendaciones</p>
      <ol className="space-y-2 mb-4">
        {res.recomendaciones.map((r, i) => (
          <li key={i} className="flex gap-2.5 text-sm text-dim">
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-s3 text-xs font-mono
                             flex items-center justify-center text-muted">{i + 1}</span>
            <span>{r}</span>
          </li>
        ))}
      </ol>

      {/* Fix sugerido */}
      {res.fix_sugerido && (
        <>
          <p className="text-[10px] text-muted font-mono uppercase tracking-wide mb-1.5">Fix Sugerido</p>
          <pre className="bg-bg border border-border rounded-lg p-3 text-xs text-dim
                          overflow-x-auto whitespace-pre-wrap mb-4">
            {res.fix_sugerido}
          </pre>
        </>
      )}

      {/* Aprobación de fix (WPRepro Agent) */}
      {res.pending_fix && (
        <PendingFixCard
          pendingFix={res.pending_fix}
          ticketId={res.ticket_id}
          onChange={onPendingFixChange}
        />
      )}

      {/* Mensaje cliente */}
      <p className="text-[10px] text-muted font-mono uppercase tracking-wide mb-1.5">Mensaje Cliente</p>
      <div className="bg-success/5 border border-success/20 rounded-lg p-3 text-sm text-dim italic">
        {res.mensaje_cliente}
      </div>

      {res.estimacion_impacto && (
        <p className="text-xs text-muted mt-3">
          <span className="text-dim font-medium">Impacto estimado: </span>
          {res.estimacion_impacto}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// History accordion item
// ---------------------------------------------------------------------------
function HistoryItem({
  ticketId, count, lastAgent, lastTs,
}: { ticketId: string; count: number; lastAgent: string; lastTs: string }) {
  const [open,    setOpen]    = useState(false)
  const [history, setHistory] = useState<AgentResponse[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    if (history.length) return
    setLoading(true)
    try {
      const res = await api.getAgentHistory(ticketId)
      setHistory(res.history)
    } catch {/* ignore */}
    finally { setLoading(false) }
  }

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-s2 transition-colors text-left"
        onClick={() => { setOpen(o => !o); if (!open) load() }}
      >
        {open ? <ChevronDown className="w-4 h-4 text-muted" /> : <ChevronRight className="w-4 h-4 text-muted" />}
        <span className="font-mono text-xs text-dim flex-1">{ticketId}</span>
        <span className="text-xs text-muted">{count} interacciones</span>
        <span className="text-xs text-muted ml-3">{lastAgent}</span>
        <span className="text-xs text-muted ml-3">{lastTs.slice(0,10)}</span>
      </button>
      {open && (
        <div className="border-t border-border bg-s2 px-4 py-3">
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-muted py-2">
              <RefreshCw className="w-3 h-3 animate-spin" /> Cargando…
            </div>
          ) : (
            <div className="space-y-3">
              {history.map((h, i) => (
                <div key={i} className="bg-surface border border-border rounded-lg p-3 text-xs">
                  <div className="flex items-center gap-2 mb-2">
                    <Bot className="w-3 h-3 text-accent" />
                    <span className="font-medium">{h.agent}</span>
                    <span className="text-muted ml-auto">{h.timestamp.slice(0,16).replace('T',' ')}</span>
                  </div>
                  <ul className="space-y-0.5">
                    {h.recomendaciones.slice(0,2).map((r, j) => (
                      <li key={j} className="text-dim truncate">• {r}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function AgentsPage() {
  const [agents,    setAgents]    = useState<AgentInfo[]>([])
  const [processed, setProcessed] = useState<{
    ticket_id: string; last_agent: string; last_timestamp: string; total_interactions: number
  }[]>([])
  const [tickets,   setTickets]   = useState<Ticket[]>([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)

  // Run form state
  const [selTicket, setSelTicket] = useState<string>('')
  const [url,       setUrl]       = useState('https://demo.wprecover.cl')
  const [sector,    setSector]    = useState('General')
  const [notes,     setNotes]     = useState('')
  const [running,   setRunning]   = useState(false)
  const [result,    setResult]    = useState<AgentResponse | null>(null)
  const [runErr,    setRunErr]    = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.listAgents()
      setAgents(res.agents)
      setProcessed(res.processed_tickets)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const stored = localStorage.getItem('wpr_last_audit')
    if (stored) {
      const data = JSON.parse(stored)
      setTickets(data.tickets ?? [])
      if (data.tickets?.length) setSelTicket(data.tickets[0].id)
      if (data.url) setUrl(data.url)
    }
  }, [])

  const handleRun = async () => {
    const ticket = tickets.find(t => t.id === selTicket)
    if (!ticket) { setRunErr('Selecciona un ticket'); return }
    setRunning(true)
    setRunErr(null)
    setResult(null)
    try {
      const ctx: SiteContext = { url, sector: sector || undefined, notas: notes || undefined }
      const res = await api.runAgent(ticket.id, ticket, ctx)
      setResult(res)
      await load() // refresh history
    } catch (e: unknown) {
      setRunErr(e instanceof Error ? e.message : 'Error al ejecutar agente')
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Agentes IA</h1>
          <p className="text-dim text-sm mt-0.5">
            {agents.length} agentes · {processed.length} tickets procesados
          </p>
        </div>
        <button className="btn-ghost border border-border flex items-center gap-2"
          onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Actualizar
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-danger/10 border border-danger/30 text-danger
                        text-sm rounded-lg px-4 py-3 mb-5">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-6">
        {/* Left: agent list */}
        <div className="space-y-2">
          <p className="text-xs text-muted font-mono uppercase tracking-wide mb-3">
            Agentes Disponibles
          </p>
          {loading
            ? [...Array(7)].map((_, i) => <div key={i} className="h-14 bg-surface rounded-xl animate-pulse" />)
            : agents.map(a => <AgentCard key={a.nombre} agent={a} />)}
        </div>

        {/* Right: run form + result */}
        <div className="space-y-5">
          {/* Run form */}
          <div className="card">
            <div className="flex items-center gap-2 mb-4">
              <Sparkles className="w-4 h-4 text-accent" />
              <h2 className="font-medium text-sm">Ejecutar Agente</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              <div>
                <label className="text-xs text-muted mb-1 block">Ticket</label>
                <select className="select" value={selTicket}
                  onChange={e => setSelTicket(e.target.value)}>
                  {tickets.length === 0
                    ? <option value="">Sin tickets — ejecuta un audit primero</option>
                    : tickets.map(t => (
                        <option key={t.id} value={t.id}>
                          [{t.categoria}] {t.id} — {t.titulo.slice(0, 40)}
                        </option>
                      ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">URL del sitio</label>
                <input className="input" value={url}
                  onChange={e => setUrl(e.target.value)}
                  placeholder="https://tusitio.cl" />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">Sector</label>
                <input className="input" value={sector}
                  onChange={e => setSector(e.target.value)}
                  placeholder="Panadería, E-commerce, …" />
              </div>
              <div>
                <label className="text-xs text-muted mb-1 block">Notas adicionales</label>
                <input className="input" value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder="Migrado desde Wix, Yoast instalado…" />
              </div>
            </div>

            {runErr && (
              <p className="text-xs text-danger mb-3">{runErr}</p>
            )}

            <button
              className="btn-primary flex items-center gap-2"
              onClick={handleRun}
              disabled={running || tickets.length === 0}
            >
              {running
                ? <><RefreshCw className="w-4 h-4 animate-spin" /> Consultando Claude…</>
                : <><Play className="w-4 h-4" /> Ejecutar Agente</>}
            </button>
          </div>

          {/* Result */}
          {result && (
            <RecommendationCard
              res={result}
              onPendingFixChange={(updated) =>
                setResult(prev => prev ? { ...prev, pending_fix: updated } : prev)
              }
            />
          )}

          {/* History */}
          {processed.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Clock className="w-4 h-4 text-muted" />
                <p className="text-sm font-medium">Historial</p>
              </div>
              <div className="space-y-2">
                {processed.map(p => (
                  <HistoryItem
                    key={p.ticket_id}
                    ticketId={p.ticket_id}
                    count={p.total_interactions}
                    lastAgent={p.last_agent}
                    lastTs={p.last_timestamp}
                  />
                ))}
              </div>
            </div>
          )}

          {processed.length === 0 && !result && !loading && (
            <div className="flex flex-col items-center py-16 gap-3 text-center">
              <Inbox className="w-8 h-8 text-muted" />
              <p className="text-dim text-sm">Sin historial de agentes.</p>
              <p className="text-xs text-muted">Ejecuta un agente arriba para ver recomendaciones.</p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
