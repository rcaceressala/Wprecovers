'use client'

import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw, AlertTriangle, Inbox, CheckCircle, XCircle } from 'lucide-react'
import { api, type EvidenceRecord } from '@/lib/api'

function Delta({ value }: { value: number }) {
  const color = value > 0 ? 'text-success' : value < 0 ? 'text-danger' : 'text-muted'
  return (
    <span className={`font-mono text-xs ${color}`}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Evidence row
// ---------------------------------------------------------------------------
function EvidenceRow({ rec }: { rec: EvidenceRecord }) {
  const [open, setOpen] = useState(false)
  const pass = rec.resultado === 'PASS'

  return (
    <>
      <tr className="border-b border-border/50 hover:bg-s2 transition-colors cursor-pointer"
          onClick={() => setOpen(o => !o)}>
        <td className="py-3 px-3">
          {open
            ? <ChevronDown className="w-3.5 h-3.5 text-muted" />
            : <ChevronRight className="w-3.5 h-3.5 text-muted" />}
        </td>
        <td className="py-3 px-2 font-mono text-xs text-dim">{rec.ticket_id}</td>
        <td className="py-3 px-2 text-xs text-dim">{rec.categoria}</td>
        <td className="py-3 px-2">
          {pass
            ? <span className="badge-pass flex items-center gap-1 w-fit"><CheckCircle className="w-3 h-3" />PASS</span>
            : <span className="badge-fail flex items-center gap-1 w-fit"><XCircle className="w-3 h-3" />FAIL</span>}
        </td>
        <td className="py-3 px-2"><Delta value={rec.delta_metrics.recovery_score_delta} /></td>
        <td className="py-3 px-2"><Delta value={rec.delta_metrics.pagespeed_score_delta} /></td>
        <td className="py-3 px-2 text-xs text-muted">{rec.timestamp.slice(0, 10)}</td>
      </tr>

      {open && (
        <tr className="bg-s2 border-b border-border">
          <td colSpan={7} className="px-4 py-4">
            {/* Before / After comparison */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {[
                { label: 'Antes (Baseline)', metrics: rec.baseline },
                { label: 'Después (Post-Fix)', metrics: rec.post_fix },
              ].map(({ label, metrics }) => (
                <div key={label} className="bg-surface border border-border rounded-xl p-4">
                  <p className="text-xs text-muted font-mono uppercase tracking-wide mb-3">{label}</p>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { k: 'Recovery Score', v: metrics.recovery_score },
                      { k: 'PageSpeed',      v: metrics.pagespeed_score },
                    ].map(({ k, v }) => (
                      <div key={k}>
                        <p className="text-[10px] text-muted mb-0.5">{k}</p>
                        <p className="text-xl font-mono font-bold text-[#e2e8f0]">{v}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Delta summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              {[
                { label: 'Recovery Δ',  value: rec.delta_metrics.recovery_score_delta },
                { label: 'PageSpeed Δ', value: rec.delta_metrics.pagespeed_score_delta },
                { label: 'Checks fixed',value: rec.delta_metrics.checks_fixed },
                { label: 'Regresiones', value: rec.delta_metrics.checks_regressed },
              ].map(({ label, value }) => (
                <div key={label} className="bg-surface border border-border rounded-lg px-3 py-2">
                  <p className="text-[10px] text-muted">{label}</p>
                  <Delta value={value} />
                </div>
              ))}
            </div>

            {/* Fix applied */}
            <p className="text-xs text-muted font-mono uppercase tracking-wide mb-1">Fix Aplicado</p>
            <div className="bg-surface border border-border rounded-lg px-3 py-2.5 text-xs">
              <span className="font-mono text-dim">{rec.fix_applied.metodo}</span>
              <span className="text-muted mx-2">·</span>
              <span className="text-dim">{rec.fix_applied.descripcion}</span>
            </div>

            <p className="text-[10px] text-muted mt-2">
              Tiempo: {rec.time_elapsed_sec}s · {rec.timestamp.replace('T', ' ').slice(0, 19)}
            </p>
          </td>
        </tr>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function QAPage() {
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.listEvidence()
      setEvidence(res.evidence ?? [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const passed = evidence.filter(e => e.resultado === 'PASS').length
  const failed = evidence.filter(e => e.resultado === 'FAIL').length

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">QA — Evidencias</h1>
          <p className="text-dim text-sm mt-0.5">
            {passed > 0 && <span className="text-success">{passed} PASS </span>}
            {failed > 0 && <span className="text-danger">{failed} FAIL</span>}
            {evidence.length === 0 && 'Sin evidencias registradas'}
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

      {/* Summary cards */}
      {evidence.length > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-5">
          {[
            { label: 'Total evidencias', value: evidence.length, color: '#4f7fff' },
            { label: 'PASS',             value: passed,          color: '#22c97a' },
            { label: 'FAIL',             value: failed,          color: '#ff4d4d' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card text-center py-4">
              <p className="text-2xl font-mono font-bold" style={{ color }}>{value}</p>
              <p className="text-xs text-muted mt-0.5">{label}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-12 bg-surface rounded-lg" />)}
        </div>
      ) : evidence.length === 0 && !error ? (
        <div className="flex flex-col items-center py-24 gap-3 text-center">
          <Inbox className="w-10 h-10 text-muted" />
          <p className="text-dim text-sm">Sin evidencias de QA.</p>
          <p className="text-xs text-muted">
            Usa POST /qa/baseline/:id y POST /qa/validate/:id para registrar evidencias.
          </p>
        </div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-border bg-s2 text-left">
                  <th className="pb-3 pt-3 px-3 w-6" />
                  {['Ticket ID','Categoría','Resultado','Recovery Δ','PageSpeed Δ','Fecha'].map(h => (
                    <th key={h} className="pb-3 pt-3 px-2 text-xs text-muted font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {evidence.map((rec, i) => <EvidenceRow key={i} rec={rec} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
