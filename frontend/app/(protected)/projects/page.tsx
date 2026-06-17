'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Plus, X, RefreshCw, FolderKanban, ExternalLink, Wand2,
  CheckCircle2, Circle, XCircle, Download, ClipboardCheck, Lock, Trash2,
  Copy, Check, KeyRound, Eye,
} from 'lucide-react'
import { api } from '@/lib/api'

const API_BASE = 'https://wprecovers.onrender.com'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type ProjectStatus = 'DRAFT' | 'OPEN' | 'CLOSED'
type PlanId = 'starter' | 'growth' | 'scale' | 'elite'

interface Project {
  id: string
  client_name: string
  site_url: string
  plan: PlanId
  notas?: string | null
  status: ProjectStatus
  score_before?: number | null
  score_after?: number | null
  improvement_points?: number | null
  guarantee_met?: boolean | null
  created_at?: string
  /** Only present in the response right after POST /projects/ (creation). */
  wprepro_api_key?: string
}

interface VerifyUrlResult {
  https_active: boolean
  http_to_https_redirect: boolean
  xmlrpc_disabled: boolean
  readme_exposed: boolean
  wordpress_detected: boolean
  wp_version: string | null
}

const STATUS_ORDER: ProjectStatus[] = ['DRAFT', 'OPEN', 'CLOSED']
const STATUS_LABELS: Record<ProjectStatus, string> = {
  DRAFT: 'Borrador',
  OPEN: 'En Progreso',
  CLOSED: 'Cerrado',
}
const STATUS_CLS: Record<ProjectStatus, string> = {
  DRAFT: 'badge-baja',
  OPEN: 'badge-open',
  CLOSED: 'badge-done',
}
const PLAN_LABELS: Record<PlanId, string> = {
  starter: 'Starter',
  growth: 'Growth',
  scale: 'Scale',
  elite: 'Elite',
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json()
}

async function fetchProjects(): Promise<Project[]> {
  const data = await apiFetch<Project[] | { projects: Project[] }>('/projects')
  return Array.isArray(data) ? data : data.projects ?? []
}

// ---------------------------------------------------------------------------
// Improvement / guarantee badges
// ---------------------------------------------------------------------------
function ImprovementBadge({ points }: { points: number | null | undefined }) {
  if (points === null || points === undefined) return null
  const cls = points >= 15 ? 'badge-done' : points > 0 ? 'badge-prog' : 'badge-fail'
  const sign = points > 0 ? '+' : ''
  return <span className={cls}>{sign}{points} pts</span>
}

function GuaranteeBadge({ met }: { met: boolean | null | undefined }) {
  if (met === null || met === undefined) return null
  return met ? (
    <span className="badge-done flex items-center gap-1">
      <CheckCircle2 className="w-3 h-3" /> Garantía cumplida
    </span>
  ) : (
    <span className="badge-fail flex items-center gap-1">
      <XCircle className="w-3 h-3" /> Garantía no cumplida
    </span>
  )
}

// ---------------------------------------------------------------------------
// Modal shell
// ---------------------------------------------------------------------------
function ModalShell({
  title, onClose, children, wide,
}: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
         onClick={onClose}>
      <div className={`card w-full ${wide ? 'max-w-2xl' : 'max-w-lg'} max-h-[85vh] overflow-y-auto`}
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="text-muted hover:text-[#e2e8f0]" onClick={onClose}>
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Onboarding checklist — data
// ---------------------------------------------------------------------------
type ChecklistItem = { key: string; label: string; critical?: boolean }
type ChecklistSection = { id: string; title: string; items: ChecklistItem[] }

const ACCESOS_CLIENTE: ChecklistSection = {
  id: 'accesos_cliente',
  title: 'Accesos del Cliente',
  items: [
    { key: 'acceso_hosting', label: 'Acceso al hosting confirmado', critical: true },
    { key: 'password_manager', label: 'Credenciales guardadas en gestor de contraseñas', critical: true },
    { key: 'cliente_aprobo', label: 'Cliente aprobó el plan de trabajo', critical: true },
  ],
}

const WORDPRESS_SECTION: ChecklistSection = {
  id: 'wordpress',
  title: 'WordPress',
  items: [
    { key: 'wprepro_agent', label: 'Plugin WPRepro Agent instalado y activo', critical: true },
    { key: 'wp_config_revisado', label: 'wp-config.php revisado con el cliente' },
    { key: 'backup_inicial', label: 'Backup inicial tomado', critical: true },
  ],
}

const ALL_SECTIONS: ChecklistSection[] = [ACCESOS_CLIENTE, WORDPRESS_SECTION]

function buildDefaultChecks(): Record<string, Record<string, boolean>> {
  const obj: Record<string, Record<string, boolean>> = {}
  ALL_SECTIONS.forEach(s => {
    obj[s.id] = {}
    s.items.forEach(it => { obj[s.id][it.key] = false })
  })
  return obj
}

function SectionCard({
  section, checks, onToggle,
}: {
  section: ChecklistSection
  checks: Record<string, boolean>
  onToggle: (key: string) => void
}) {
  const done  = section.items.filter(it => checks[it.key]).length
  const total = section.items.length

  return (
    <div className="bg-s2 border border-border rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-medium text-dim">{section.title}</h3>
        <span className={done === total ? 'badge-done' : 'badge-open'}>{done} / {total}</span>
      </div>
      <div className="space-y-0.5">
        {section.items.map(it => {
          const checked = !!checks[it.key]
          return (
            <button
              key={it.key}
              type="button"
              onClick={() => onToggle(it.key)}
              className={[
                'w-full flex items-center gap-2.5 px-2 py-1.5 rounded-md text-xs text-left transition-colors',
                checked ? 'bg-success/5' : 'hover:bg-surface',
              ].join(' ')}
            >
              {checked
                ? <CheckCircle2 className="w-3.5 h-3.5 text-success flex-shrink-0" />
                : <Circle className="w-3.5 h-3.5 text-muted flex-shrink-0" />}
              <span className={checked ? 'text-dim line-through' : ''}>{it.label}</span>
              {it.critical && !checked && (
                <span className="ml-auto text-[9px] font-mono uppercase tracking-wide text-warn flex-shrink-0">
                  crítico
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// WPRepro Agent key — reveal + copy panel
// ---------------------------------------------------------------------------
function WpreproKeyPanel({ apiKey }: { apiKey: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(apiKey)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API unavailable (e.g. insecure context) — user can still select+copy manually.
    }
  }

  return (
    <div className="bg-s2 border border-border rounded-lg p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <code className="flex-1 text-xs font-mono text-dim break-all bg-bg rounded px-2.5 py-2">
          {apiKey}
        </code>
        <button
          type="button"
          className="btn-ghost border border-border flex items-center gap-1.5 flex-shrink-0"
          onClick={copy}
        >
          {copied
            ? <><Check className="w-3.5 h-3.5 text-success" /> Copiado</>
            : <><Copy className="w-3.5 h-3.5" /> Copiar</>}
        </button>
      </div>
      <p className="text-xs text-dim">
        Pega esto en <code className="text-[11px]">wp-config.php</code> del sitio del cliente, antes
        de <code className="text-[11px]">/* That&apos;s all, stop editing! */</code>:
      </p>
      <pre className="bg-bg rounded p-2 text-[11px] text-dim overflow-x-auto">
        {`define( 'WPREPRO_API_KEY', '${apiKey}' );`}
      </pre>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create project modal (con checklist de onboarding integrado)
// ---------------------------------------------------------------------------
function CreateProjectModal({
  onClose, onCreated,
}: { onClose: () => void; onCreated: (p: Project) => void }) {
  const [clientName,  setClientName]  = useState('')
  const [siteUrl,      setSiteUrl]      = useState('')
  const [plan,         setPlan]         = useState<PlanId>('starter')
  const [notas,        setNotas]        = useState('')
  const [checks,       setChecks]       = useState(buildDefaultChecks)
  const [saving,       setSaving]       = useState(false)
  const [error,        setError]        = useState<string | null>(null)
  const [verifying,    setVerifying]    = useState(false)
  const [verifyResult, setVerifyResult] = useState<VerifyUrlResult | null>(null)
  const [verifyError,  setVerifyError]  = useState<string | null>(null)
  const [createdProject, setCreatedProject] = useState<Project | null>(null)

  const { done, total, percent } = useMemo(() => {
    let d = 0, t = 0
    ALL_SECTIONS.forEach(s => s.items.forEach(it => {
      t++
      if (checks[s.id]?.[it.key]) d++
    }))
    return { done: d, total: t, percent: t === 0 ? 0 : Math.round((d / t) * 100) }
  }, [checks])

  function toggleItem(sectionId: string, key: string) {
    setChecks(prev => ({ ...prev, [sectionId]: { ...prev[sectionId], [key]: !prev[sectionId][key] } }))
  }

  const handleVerify = async () => {
    if (!siteUrl.trim()) return
    setVerifying(true)
    setVerifyError(null)
    try {
      const result = await apiFetch<VerifyUrlResult>('/projects/verify-url', {
        method: 'POST',
        body: JSON.stringify({ url: siteUrl.trim() }),
      })
      setVerifyResult(result)
    } catch (e: unknown) {
      setVerifyError(e instanceof Error ? e.message : 'Error al verificar la URL')
    } finally {
      setVerifying(false)
    }
  }

  const submit = async () => {
    if (!clientName.trim() || !siteUrl.trim()) {
      setError('Cliente y URL son obligatorios')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const created = await apiFetch<Project>('/projects', {
        method: 'POST',
        body: JSON.stringify({
          client_name: clientName.trim(),
          site_url: siteUrl.trim(),
          plan,
          notas: notas.trim() || null,
        }),
      })
      onCreated(created)
      if (created.wprepro_api_key) {
        setCreatedProject(created)
      } else {
        onClose()
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al crear el proyecto')
    } finally {
      setSaving(false)
    }
  }

  if (createdProject?.wprepro_api_key) {
    return (
      <ModalShell title="Proyecto creado" onClose={onClose}>
        <div className="space-y-4">
          <div className="flex items-center gap-2 bg-success/10 border border-success/30 text-success
                          text-sm font-medium rounded-lg px-3 py-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> &quot;{createdProject.client_name}&quot; creado correctamente
          </div>

          <div>
            <label className="text-xs text-muted flex items-center gap-1.5 mb-1.5">
              <KeyRound className="w-3.5 h-3.5" /> Clave WPRepro Agent de este proyecto
            </label>
            <WpreproKeyPanel apiKey={createdProject.wprepro_api_key} />
          </div>

          <p className="text-xs text-muted">
            Esta clave es única para este proyecto. Si la pierdes, puedes volver a verla desde la
            tarjeta del proyecto.
          </p>

          <div className="flex justify-end pt-2 border-t border-border">
            <button className="btn-primary" onClick={onClose}>Listo</button>
          </div>
        </div>
      </ModalShell>
    )
  }

  return (
    <ModalShell title="Nuevo Proyecto" onClose={onClose} wide>
      <div className="space-y-4">
        {/* Progreso del checklist */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-muted font-mono uppercase tracking-wide">Checklist de onboarding</span>
            <span
              className="text-xs font-mono font-semibold"
              style={{ color: percent === 100 ? '#22c97a' : '#4f7fff' }}
            >
              {done} / {total} · {percent}%
            </span>
          </div>
          <div className="h-2 bg-s2 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${percent}%`, background: percent === 100 ? '#22c97a' : '#4f7fff' }}
            />
          </div>
        </div>

        {percent === 100 && (
          <div className="flex items-center gap-2 bg-success/10 border border-success/30 text-success
                          text-xs font-medium rounded-lg px-3 py-2">
            <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> ✔ Listo para empezar
          </div>
        )}

        {/* Datos del proyecto */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted block mb-1">Cliente</label>
            <input className="input" placeholder="Nombre del cliente"
              value={clientName} onChange={e => setClientName(e.target.value)} autoFocus />
          </div>
          <div>
            <label className="text-xs text-muted block mb-1">URL del sitio</label>
            <input className="input" placeholder="https://ejemplo.com"
              value={siteUrl} onChange={e => setSiteUrl(e.target.value)} />
            {siteUrl.trim() && (
              <button
                type="button"
                className="mt-1.5 text-xs flex items-center gap-1.5 text-accent hover:underline disabled:opacity-50"
                onClick={handleVerify}
                disabled={verifying}
              >
                {verifying
                  ? <><RefreshCw className="w-3 h-3 animate-spin" /> Verificando…</>
                  : <><Wand2 className="w-3 h-3" /> Verificar automáticamente</>}
              </button>
            )}
            {verifyResult && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                <span className={verifyResult.https_active ? 'badge-done' : 'badge-fail'}>
                  HTTPS {verifyResult.https_active ? 'activo' : 'inactivo'}
                </span>
                <span className={verifyResult.http_to_https_redirect ? 'badge-done' : 'badge-fail'}>
                  Redirect {verifyResult.http_to_https_redirect ? 'OK' : 'falta'}
                </span>
                <span className={verifyResult.xmlrpc_disabled ? 'badge-done' : 'badge-fail'}>
                  xmlrpc {verifyResult.xmlrpc_disabled ? 'OK' : 'expuesto'}
                </span>
                <span className={!verifyResult.readme_exposed ? 'badge-done' : 'badge-fail'}>
                  readme {verifyResult.readme_exposed ? 'expuesto' : 'OK'}
                </span>
                {verifyResult.wordpress_detected && (
                  <span className="badge bg-accent/10 text-accent border border-accent/20">
                    WP {verifyResult.wp_version ?? 'detectado'}
                  </span>
                )}
              </div>
            )}
            {verifyError && <p className="text-xs text-danger mt-1.5">{verifyError}</p>}
          </div>
          <div>
            <label className="text-xs text-muted block mb-1">Plan</label>
            <select className="select" value={plan} onChange={e => setPlan(e.target.value as PlanId)}>
              {(Object.keys(PLAN_LABELS) as PlanId[]).map(p => (
                <option key={p} value={p}>{PLAN_LABELS[p]}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-xs text-muted block mb-1">Notas</label>
            <textarea className="input min-h-[60px] resize-none" placeholder="Notas internas (opcional)"
              value={notas} onChange={e => setNotas(e.target.value)} />
          </div>
        </div>

        {/* Secciones del checklist */}
        <div className="space-y-3">
          {ALL_SECTIONS.map(s => (
            <SectionCard
              key={s.id}
              section={s}
              checks={checks[s.id] ?? {}}
              onToggle={key => toggleItem(s.id, key)}
            />
          ))}
        </div>

        {error && (
          <p className="text-xs text-danger">{error}</p>
        )}

        <div className="flex items-center justify-between pt-2 border-t border-border">
          <button
            type="button"
            className="text-xs text-muted hover:text-[#e2e8f0] hover:underline disabled:opacity-50"
            onClick={submit}
            disabled={saving}
          >
            Saltar checklist y crear proyecto
          </button>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={onClose} disabled={saving}>Cancelar</button>
            {percent === 100 && (
              <button className="btn-primary flex items-center gap-2" onClick={submit} disabled={saving}>
                {saving
                  ? 'Creando…'
                  : <><CheckCircle2 className="w-4 h-4" /> Crear Proyecto</>}
              </button>
            )}
          </div>
        </div>
      </div>
    </ModalShell>
  )
}

// ---------------------------------------------------------------------------
// Project detail modal
// ---------------------------------------------------------------------------
function ProjectDetailModal({
  project, onClose, onUpdated,
}: { project: Project; onClose: () => void; onUpdated: (p: Project) => void }) {
  const [busy,  setBusy]  = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revealedKey, setRevealedKey] = useState<string | null>(null)
  const [revealingKey, setRevealingKey] = useState(false)

  const revealKey = async () => {
    setRevealingKey(true)
    setError(null)
    try {
      const data = await api.getProjectApiKey(project.id)
      setRevealedKey(data.wprepro_api_key)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al obtener la clave de API')
    } finally {
      setRevealingKey(false)
    }
  }

  const captureBaseline = async () => {
    setBusy(true)
    setError(null)
    try {
      const updated = await apiFetch<Project>(`/projects/${project.id}/audit-and-baseline`, {
        method: 'POST',
      })
      localStorage.setItem('wpr_active_project', JSON.stringify({
        project_id: updated.id,
        client_name: updated.client_name,
        site_url: updated.site_url,
        plan: updated.plan,
      }))
      const auditResult = await api.runAudit(updated.site_url)
      localStorage.setItem('wpr_last_audit', JSON.stringify(auditResult))
      onUpdated(updated)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al capturar el baseline')
    } finally {
      setBusy(false)
    }
  }

  const closeProject = async () => {
    setBusy(true)
    setError(null)
    try {
      const updated = await apiFetch<Project>(`/projects/${project.id}/close`, {
        method: 'POST',
      })
      onUpdated(updated)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al cerrar el proyecto')
    } finally {
      setBusy(false)
    }
  }

  const downloadPdf = () => {
    window.open(`${API_BASE}/report/download/${project.id}`, '_blank')
  }

  return (
    <ModalShell title={project.client_name} onClose={onClose}>
      <div className="space-y-5">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={STATUS_CLS[project.status]}>{STATUS_LABELS[project.status]}</span>
          <span className="badge bg-s2 text-dim border border-border">{PLAN_LABELS[project.plan]}</span>
          <a href={project.site_url} target="_blank" rel="noreferrer"
             className="text-xs text-accent flex items-center gap-1 ml-auto">
            {project.site_url} <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        {project.notas && (
          <p className="text-sm text-dim bg-s2 border border-border rounded-lg p-3">{project.notas}</p>
        )}

        {/* WPRepro Agent key */}
        <div>
          {revealedKey ? (
            <>
              <label className="text-xs text-muted flex items-center gap-1.5 mb-1.5">
                <KeyRound className="w-3.5 h-3.5" /> Clave WPRepro Agent
              </label>
              <WpreproKeyPanel apiKey={revealedKey} />
            </>
          ) : (
            <button
              type="button"
              className="text-xs text-accent flex items-center gap-1.5 hover:underline disabled:opacity-50"
              onClick={revealKey}
              disabled={revealingKey}
            >
              {revealingKey
                ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Cargando…</>
                : <><Eye className="w-3.5 h-3.5" /> Ver clave de API</>}
            </button>
          )}
        </div>

        {/* Scores antes/después */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-s2 border border-border rounded-lg p-3 text-center">
            <p className="text-xs text-muted mb-1 font-mono uppercase tracking-wide">Score Antes</p>
            <p className="text-2xl font-mono font-bold text-[#e2e8f0]">
              {project.score_before ?? '—'}
            </p>
          </div>
          <div className="bg-s2 border border-border rounded-lg p-3 text-center">
            <p className="text-xs text-muted mb-1 font-mono uppercase tracking-wide">Score Después</p>
            <p className="text-2xl font-mono font-bold text-[#e2e8f0]">
              {project.score_after ?? '—'}
            </p>
          </div>
        </div>

        {/* Improvement + guarantee badges */}
        {(project.improvement_points !== null && project.improvement_points !== undefined) && (
          <div className="flex items-center gap-2 flex-wrap">
            <ImprovementBadge points={project.improvement_points} />
            <GuaranteeBadge met={project.guarantee_met} />
          </div>
        )}

        {error && <p className="text-xs text-danger">{error}</p>}

        {/* Status-specific action */}
        <div className="flex justify-end gap-2 pt-2 border-t border-border">
          {project.status === 'DRAFT' && (
            <button className="btn-primary flex items-center gap-2" onClick={captureBaseline} disabled={busy}>
              {busy
                ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Capturando…</>
                : <><ClipboardCheck className="w-3.5 h-3.5" /> Capturar Baseline</>}
            </button>
          )}
          {project.status === 'OPEN' && (
            <button className="btn-primary flex items-center gap-2" onClick={closeProject} disabled={busy}>
              {busy
                ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Cerrando…</>
                : <><Lock className="w-3.5 h-3.5" /> Cerrar Proyecto</>}
            </button>
          )}
          {project.status === 'CLOSED' && (
            <button className="btn-primary flex items-center gap-2" onClick={downloadPdf}>
              <Download className="w-3.5 h-3.5" /> Descargar PDF
            </button>
          )}
        </div>
      </div>
    </ModalShell>
  )
}

// ---------------------------------------------------------------------------
// Project card
// ---------------------------------------------------------------------------
function ProjectCard({
  project, onClick, onDelete,
}: { project: Project; onClick: () => void; onDelete: () => void }) {
  const [confirming, setConfirming] = useState(false)

  return (
    <div onClick={onClick} role="button" tabIndex={0}
      className="card text-left hover:border-accent/50 transition-colors w-full cursor-pointer">
      <div className="flex items-start justify-between mb-2">
        <p className="text-sm font-medium truncate">{project.client_name}</p>
        <span className="badge bg-s2 text-dim border border-border flex-shrink-0">
          {PLAN_LABELS[project.plan]}
        </span>
      </div>
      <p className="text-xs text-dim truncate mb-3">{project.site_url}</p>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <ImprovementBadge points={project.improvement_points} />
          <GuaranteeBadge met={project.guarantee_met} />
        </div>
        {confirming ? (
          <div className="flex items-center gap-1.5 flex-shrink-0" onClick={e => e.stopPropagation()}>
            <span className="text-[11px] text-danger">¿Eliminar?</span>
            <button className="text-[11px] text-danger font-semibold hover:underline"
              onClick={onDelete}>
              Sí
            </button>
            <button className="text-[11px] text-muted hover:underline"
              onClick={() => setConfirming(false)}>
              No
            </button>
          </div>
        ) : (
          <button
            className="text-[11px] text-muted hover:text-danger flex items-center gap-1 flex-shrink-0"
            onClick={e => { e.stopPropagation(); setConfirming(true) }}
          >
            <Trash2 className="w-3 h-3" /> Eliminar
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState<Project | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setProjects(await fetchProjects())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al cargar proyectos')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreated = (p: Project) => setProjects(prev => [p, ...prev])
  const handleUpdated = (p: Project) => {
    setProjects(prev => prev.map(x => x.id === p.id ? p : x))
    setSelected(p)
  }
  const handleDelete = async (id: string) => {
    setError(null)
    try {
      await api.deleteProject(id)
      setProjects(prev => prev.filter(p => p.id !== id))
      if (selected?.id === id) setSelected(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al eliminar el proyecto')
    }
  }

  const grouped = STATUS_ORDER.map(status => ({
    status,
    items: projects.filter(p => p.status === status),
  }))

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Proyectos</h1>
          <p className="text-dim text-sm mt-0.5">{projects.length} proyectos</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost border border-border flex items-center gap-2"
            onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Actualizar
          </button>
          <button className="btn-primary flex items-center gap-2" onClick={() => setShowCreate(true)}>
            <Plus className="w-4 h-4" /> Nuevo Proyecto
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-danger/10 border border-danger/30 text-danger
                        text-sm rounded-lg px-4 py-3 mb-5">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 animate-pulse">
          {[...Array(6)].map((_, i) => <div key={i} className="h-32 bg-surface rounded-xl" />)}
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center py-24 gap-3 text-center">
          <FolderKanban className="w-10 h-10 text-muted" />
          <p className="text-dim text-sm">No hay proyectos todavía.</p>
          <button className="btn-primary text-sm" onClick={() => setShowCreate(true)}>
            Crear el primer proyecto
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {grouped.map(({ status, items }) => (
            <div key={status}>
              <div className="flex items-center gap-2 mb-3">
                <span className={STATUS_CLS[status]}>{STATUS_LABELS[status]}</span>
                <span className="text-xs text-muted">{items.length}</span>
              </div>
              {items.length === 0 ? (
                <p className="text-xs text-muted italic">Sin proyectos en este estado.</p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {items.map(p => (
                    <ProjectCard key={p.id} project={p} onClick={() => setSelected(p)}
                      onDelete={() => handleDelete(p.id)} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateProjectModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />
      )}
      {selected && (
        <ProjectDetailModal
          project={selected}
          onClose={() => setSelected(null)}
          onUpdated={handleUpdated}
        />
      )}
    </>
  )
}
