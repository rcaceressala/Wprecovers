const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://wprecovers.onrender.com'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Categoria = 'SEO' | 'Performance' | 'Conversion' | 'Seguridad' | 'WooCommerce'
export type Prioridad = 'Critica' | 'Alta' | 'Media' | 'Baja'
export type EstadoTicket = 'OPEN' | 'IN_PROGRESS' | 'DONE' | 'FAIL'
export type FixStatus = 'PENDING' | 'APPLIED' | 'ROLLED_BACK' | 'FAILED'

export interface Ticket {
  id: string
  categoria: Categoria
  titulo: string
  prioridad: Prioridad
  impacto: string
  agente: string
  estimacion: number
  dependencias: string[]
  estado: EstadoTicket
}

export interface TicketSummary {
  total: number
  criticos: number
  altos: number
  medios: number
  bajos: number
  estimacion_total_min: number
}

export interface TicketResponse {
  url: string | null
  recovery_score: number
  resumen: TicketSummary
  tickets: Ticket[]
}

export interface AuditInput {
  checks: Record<string, Record<string, boolean>>
  errores: string[]
  recovery_score: number
  url?: string
}

export interface SiteMetrics {
  pagespeed_score: number
  recovery_score: number
  checks: Record<string, Record<string, boolean>>
}

export interface EvidenceRecord {
  ticket_id: string
  categoria: string
  timestamp: string
  baseline: SiteMetrics
  post_fix: SiteMetrics
  fix_applied: { metodo: string; descripcion: string; archivos_modificados: string[] }
  resultado: 'PASS' | 'FAIL'
  delta_metrics: {
    recovery_score_delta: number
    pagespeed_score_delta: number
    checks_fixed: number
    checks_regressed: number
    improvement_pct: number
  }
  time_elapsed_sec: number
}

export interface FixPayload {
  command: string | null
  php_snippet: string | null
  file_target: string | null
}

export interface FixLogEntry {
  ticket_id: string
  check_name: string
  categoria: string
  metodo: string
  staging_url: string
  timestamp: string
  status: FixStatus
  fix_payload: FixPayload | null
  rollback_payload: FixPayload | null
  riesgo: string
  requires_approval: boolean
  approved_by: string | null
  error: string | null
}

export interface SiteContext {
  url: string
  platform?: string
  recovery_score?: number
  pagespeed_score?: number
  sector?: string
  notas?: string
}

export interface AgentResponse {
  agent: string
  scope: string
  ticket_id: string
  recomendaciones: string[]
  fix_sugerido: string | null
  mensaje_cliente: string
  prioridad: string
  estimacion_impacto: string
  tokens_used: number
  timestamp: string
}

export interface AgentInfo { nombre: string; scope: string; model: string }

export interface AgentsListResponse {
  agents: AgentInfo[]
  processed_tickets: {
    ticket_id: string
    last_agent: string
    last_scope: string
    last_timestamp: string
    total_interactions: number
  }[]
}

export interface Plan {
  plan_id: string
  name: string
  monthly_usd: number
  limits: {
    audits_per_month: number
    fixes_per_month: number
    agents_per_month: number
    reports_per_month: number
    sites: number
  }
  features: string[]
}

export interface UsageInfo {
  client_id: string
  period: string
  plan: string | null
  status: string
  usage: {
    audits:  { used: number; limit: number | 'unlimited'; remaining: number | 'unlimited' }
    fixes:   { used: number; limit: number | 'unlimited'; remaining: number | 'unlimited' }
    agents:  { used: number; limit: number | 'unlimited'; remaining: number | 'unlimited' }
    reports: { used: number; limit: number | 'unlimited'; remaining: number | 'unlimited' }
  }
  last_updated: string
}

export interface CheckoutResponse {
  mode: 'mock' | 'live'
  plan: string
  client_id: string
  monthly_usd: number
  checkout_url: string
  session_id: string
  note?: string
}

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export const api = {
  health: () =>
    apiFetch<{ status: string; modules: string[] }>('/health'),

  // M2 — Tickets
  generateTickets: (input: AuditInput) =>
    apiFetch<TicketResponse>('/api/v1/tickets/generate', {
      method: 'POST',
      body: JSON.stringify(input),
    }),

  // M3 — QA
  listEvidence: () =>
    apiFetch<{ evidence: EvidenceRecord[] }>('/qa/evidence/'),

  getQAReport: (ticketId: string) =>
    apiFetch<Record<string, unknown>>(`/qa/report/${ticketId}`),

  // M4 — Fixes
  getFixLog: (ticketId: string) =>
    apiFetch<{ ticket_id: string; total_operations: number; log: FixLogEntry[] }>(
      `/fix/log/${ticketId}`
    ),

  getFixStatus: (ticketId: string) =>
    apiFetch<{ ticket_id: string; status: FixStatus; check_name?: string; rollback_available?: boolean }>(
      `/fix/status/${ticketId}`
    ),

  rollbackFix: (ticketId: string, reason = 'Rollback solicitado desde el dashboard') =>
    apiFetch<{ ticket_id: string; status: string; reason: string; timestamp: string }>(
      `/fix/rollback/${ticketId}`,
      { method: 'POST', body: JSON.stringify({ reason }) }
    ),

  // M5 — Reports
  getReport: (ticketId: string) =>
    apiFetch<Record<string, unknown>>(`/report/${ticketId}`),

  downloadPDFUrl: (ticketId: string) => `${BASE}/report/download/${ticketId}`,

  // M6 — Agents
  listAgents: () =>
    apiFetch<AgentsListResponse>('/agents/'),

  runAgent: (ticketId: string, ticket: Ticket, siteContext: SiteContext) =>
    apiFetch<AgentResponse>(`/agents/run/${ticketId}`, {
      method: 'POST',
      body: JSON.stringify({ ticket, site_context: siteContext, historial: [] }),
    }),

  getAgentHistory: (ticketId: string) =>
    apiFetch<{ ticket_id: string; total_interactions: number; history: AgentResponse[] }>(
      `/agents/history/${ticketId}`
    ),

  // M1 — Real Audit
  runAudit: (url: string) =>
    apiFetch<TicketResponse>('/audit/run', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  // M8 — Billing
  listPlans: () =>
    apiFetch<{ plans: Plan[] }>('/billing/plans/'),

  getUsage: (clientId: string) =>
    apiFetch<UsageInfo>(`/billing/usage/${clientId}`),

  createCheckout: (plan: string, clientId: string, successUrl: string, cancelUrl: string) =>
    apiFetch<CheckoutResponse>(`/billing/checkout/${plan}`, {
      method: 'POST',
      body: JSON.stringify({ client_id: clientId, success_url: successUrl, cancel_url: cancelUrl }),
    }),

  upgradePlan: (clientId: string, newPlan: string) =>
    apiFetch<{ client_id: string; old_plan: string; new_plan: string; status: string; mode: string }>(
      `/billing/upgrade/${clientId}`,
      { method: 'POST', body: JSON.stringify({ new_plan: newPlan }) }
    ),
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export const PRIORIDAD_ORDER: Record<Prioridad, number> = {
  Critica: 0, Alta: 1, Media: 2, Baja: 3,
}

export const DEMO_AUDIT: AuditInput = {
  checks: {
    SEO: { title: true, meta_desc: false, canonical: true, sitemap: false, robots: false, schema: false },
    Performance: { LCP: false, CLS: true, pagespeed: false, ttfb: false },
    Conversion: { tel_clickeable: false, whatsapp: false, CTA: true },
    Seguridad: { ssl: true, headers: false, permisos: false },
    WooCommerce: { pasarelas: true, productos_sin_img: false, checkout: true },
  },
  errores: [],
  recovery_score: 38,
  url: 'https://demo.wprecover.cl',
}

export function scoreColor(score: number): string {
  if (score >= 75) return '#22c97a'
  if (score >= 60) return '#f5a623'
  return '#ff4d4d'
}

export function scoreLabel(score: number): string {
  if (score >= 75) return 'Bueno'
  if (score >= 60) return 'Regular'
  return 'Crítico'
}
