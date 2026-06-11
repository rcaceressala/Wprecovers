'use client'

import { useEffect, useState } from 'react'
import { RefreshCw, AlertTriangle, Inbox, CheckCircle, XCircle, HelpCircle } from 'lucide-react'
import { api, type EvidenceRecord } from '@/lib/api'

function Delta({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="font-mono text-xs text-muted">—</span>
  }
  const color = value > 0 ? 'text-success' : value < 0 ? 'text-danger' : 'text-muted'
  return (
    <span className={`font-mono text-xs ${color}`}>
      {value > 0 ? '+' : ''}{value.toFixed(1)}%
    </span>
  )
}

// ---------------------------------------------------------------------------
// Evidence row
// ---------------------------------------------------------------------------
function EvidenceRow({ rec }: { rec: EvidenceRecord }) {
  const pass = rec.resultado === 'PASS'
  const fail = rec.resultado === 'FAIL'

  return (
    <tr className="border-b border-border/50 hover:bg-s2 transition-colors">
      <td className="py-3 px-3 font-mono text-xs text-dim">{rec.ticket_id ?? '—'}</td>
      <td className="py-3 px-2 text-xs text-dim">{rec.categoria ?? '—'}</td>
      <td className="py-3 px-2">
        {pass && <span className="badge-pass flex items-center gap-1 w-fit"><CheckCircle className="w-3 h-3" />PASS</span>}
        {fail && <span className="badge-fail flex items-center gap-1 w-fit"><XCircle className="w-3 h-3" />FAIL</span>}
        {!pass && !fail && <span className="flex items-center gap-1 w-fit text-muted text-xs"><HelpCircle className="w-3 h-3" />—</span>}
      </td>
      <td className="py-3 px-2"><Delta value={rec.improvement_pct} /></td>
      <td className="py-3 px-2 text-xs text-muted">{rec.timestamp ? rec.timestamp.slice(0, 10) : '—'}</td>
    </tr>
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
      const list = res?.evidence
      if (!Array.isArray(list)) {
        setEvidence([])
        setError('La API devolvió un formato inesperado para las evidencias de QA.')
        return
      }
      setEvidence(list)
    } catch (e: unknown) {
      setEvidence([])
      setError(e instanceof Error ? e.message : 'Error al cargar las evidencias de QA')
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
      ) : evidence.length > 0 ? (
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-border bg-s2 text-left">
                  {['Ticket ID','Categoría','Resultado','Mejora %','Fecha'].map(h => (
                    <th key={h} className="pb-3 pt-3 px-2 text-xs text-muted font-medium first:px-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {evidence.map((rec, i) => <EvidenceRow key={rec.file ?? i} rec={rec} />)}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  )
}
