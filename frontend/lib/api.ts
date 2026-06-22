const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://wprecovers.onrender.com'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Categoria = 'SEO' | 'Performance' | 'Conversion' | 'Seguridad' | 'WooCommerce' | 'Marketing'
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
  project_id?: string | null
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

export interface ReportRequest {
  client_name: string
  site_url: string
  client_logo_url?: string | null
  baseline: SiteMetrics
  post_fix: SiteMetrics
  tickets_completados?: string[]
  notas?: string | null
}

export interface ReportGenerateResult {
  ticket_id: string
  score_before: number
  score_after: number
  improvement_points: number
  improvement_pct: number
  guarantee_met: boolean
  pdf_available: boolean
  timestamp: string
}

export interface EvidenceRecord {
  file: string
  ticket_id: string | null
  categoria: string | null
  resultado: 'PASS' | 'FAIL' | null
  timestamp: string | null
  improvement_pct: number | null
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

export type PendingFixStatus = 'pending' | 'applied' | 'error'

export interface PendingFix {
  ticket_id: string
  categoria: string
  agent: string
  titulo: string
  wp_cli_commands: string[]
  php_snippet: string | null
  site_url: string
  snippet_id: number | null
  snippet_status: string | null
  auto_approve: boolean
  status: PendingFixStatus
  error: string | null
  created_at: string
  applied_at: string | null
  approval_results: Record<string, unknown> | null
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
  pending_fix?: PendingFix | null
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
// M9 — Projects
// ---------------------------------------------------------------------------

export type ProjectStatus = 'DRAFT' | 'OPEN' | 'CLOSED'

export interface ProjectSummary {
  id: string
  client_name: string
  site_url: string
  plan: string
  status: ProjectStatus
  score_before: number | null
  score_after: number | null
  improvement_points: number | null
  improvement_pct: number | null
  guarantee_met: boolean | null
  created_at: string
  updated_at: string
}

export interface ProjectDetail extends ProjectSummary {
  notas: string | null
  checks_before: Record<string, Record<string, boolean>> | null
  pagespeed_before: number | null
}

export type CloseProjectResult = ProjectDetail

// ---------------------------------------------------------------------------
// M10 — Marketing OS
// ---------------------------------------------------------------------------

export type MonthlyBudget = 'bajo' | 'medio' | 'alto'
export type WprecoverPlan = 'starter' | 'growth' | 'scale' | 'elite'

export interface MarketingGenerateRequest {
  site_url: string
  business_type: string
  city: string
  monthly_budget: MonthlyBudget
  plan: WprecoverPlan
  project_id?: string | null
}

export interface ContentCalendarItem {
  dia: number
  objetivo: string
  formato: string
  guion: string
  cta: string
}

export interface Plan90Dias {
  semana_1_2: string[]
  semana_3_4: string[]
  mes_2: string[]
  mes_3: string[]
}

export interface MarketingPlan {
  diagnostico_inicial: string[]
  estrategia_adquisicion: string[]
  calendario_contenido: ContentCalendarItem[]
  embudo_ventas: string[]
  estrategia_whatsapp: string[]
  plan_ejecucion_90_dias: Plan90Dias
  ia_automatizacion: string[]
  metricas_clave: string[]
  top_10_acciones: string[]
}

export interface MarketingPlanRecord {
  id: string
  request: MarketingGenerateRequest
  plan: MarketingPlan
  recovery_score: number | null
  pagespeed_score: number | null
  pdf_available: boolean
  created_at: string
}

export interface MarketingPlanSummary {
  id: string
  site_url: string
  project_id: string | null
  recovery_score: number | null
  pdf_available: boolean
  created_at: string
}

export interface ContentPiece {
  dia: number
  formato: string
  objetivo: string
  texto_completo: string
  prompt_imagen: string
  hashtags: string[]
  mejor_horario: string
}

export type ContentJobStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED'

export interface ContentPiecesRecord {
  plan_id: string
  pieces: ContentPiece[]
  created_at: string
  status: ContentJobStatus
  error?: string | null
}

export interface MarketingActionTicketsRecord {
  plan_id: string
  tickets: Ticket[]
  created_at: string
  status: ContentJobStatus
  error?: string | null
}

export interface Plan90DiasTicketsRecord {
  plan_id: string
  tickets: Ticket[]
  created_at: string
  status: ContentJobStatus
  error?: string | null
}

export interface WhatsAppMessage {
  categoria: string
  mensaje_texto: string
  variables_sugeridas: string[]
  mejor_momento_envio: string
}

export interface WhatsAppMessagesRecord {
  plan_id: string
  mensajes: WhatsAppMessage[]
  created_at: string
  status: ContentJobStatus
  error?: string | null
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

  generateReport: (ticketId: string, req: ReportRequest) =>
    apiFetch<ReportGenerateResult>(`/report/generate/${ticketId}`, {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  downloadPDF: async (ticketId: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/report/download/${ticketId}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    return res.blob()
  },

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

  // M6 — Fix Approval
  approveFix: (ticketId: string) =>
    apiFetch<PendingFix>(`/fixes/approve/${ticketId}`, { method: 'POST' }),

  rejectFix: (ticketId: string) =>
    apiFetch<{ ticket_id: string; status: string }>(`/fixes/reject/${ticketId}`, { method: 'POST' }),

  listPendingFixes: () =>
    apiFetch<{ pending: PendingFix[] }>('/fixes/pending/'),

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

  // M9 — Projects
  listProjects: () =>
    apiFetch<{ projects: ProjectSummary[] }>('/projects/'),

  getProject: (projectId: string) =>
    apiFetch<ProjectDetail>(`/projects/${projectId}`),

  createProject: (req: { client_name: string; site_url: string; plan: string; notas?: string | null }) =>
    apiFetch<ProjectDetail>('/projects/', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  captureBaseline: (projectId: string) =>
    apiFetch<ProjectDetail>(`/projects/${projectId}/audit-and-baseline`, { method: 'POST' }),

  closeProject: (projectId: string) =>
    apiFetch<CloseProjectResult>(`/projects/${projectId}/close`, { method: 'POST' }),

  deleteProject: (projectId: string) =>
    apiFetch<{ id: string; status: string }>(`/projects/${projectId}`, { method: 'DELETE' }),

  getProjectApiKey: (projectId: string) =>
    apiFetch<{ project_id: string; wprepro_api_key: string }>(`/projects/${projectId}/wprepro-key`),

  // M10 — Marketing OS
  generateMarketingPlan: (req: MarketingGenerateRequest) =>
    apiFetch<MarketingPlanRecord>('/marketing/generate', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  getMarketingPlan: (planId: string) =>
    apiFetch<MarketingPlanRecord>(`/marketing/${planId}`),

  listMarketingPlans: (projectId?: string) =>
    apiFetch<{ plans: MarketingPlanSummary[] }>(
      projectId ? `/marketing/?project_id=${encodeURIComponent(projectId)}` : '/marketing/'
    ),

  downloadMarketingPDF: async (planId: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/marketing/download/${planId}`)
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
    }
    return res.blob()
  },

  executeMarketingContent: (planId: string) =>
    apiFetch<ContentPiecesRecord>(`/marketing/${planId}/execute-content`, { method: 'POST' }),
  getMarketingContent: (planId: string) =>
    apiFetch<ContentPiecesRecord>(`/marketing/${planId}/content`),
  executeMarketingActions: (planId: string) =>
    apiFetch<MarketingActionTicketsRecord>(`/marketing/${planId}/execute-actions`, { method: 'POST' }),
  getMarketingActions: (planId: string) =>
    apiFetch<MarketingActionTicketsRecord>(`/marketing/${planId}/actions`),
  executeMarketingWhatsapp: (planId: string) =>
    apiFetch<WhatsAppMessagesRecord>(`/marketing/${planId}/execute-whatsapp`, { method: 'POST' }),
  getMarketingWhatsapp: (planId: string) =>
    apiFetch<WhatsAppMessagesRecord>(`/marketing/${planId}/whatsapp`),
  executeMarketingPlan90: (planId: string) =>
    apiFetch<Plan90DiasTicketsRecord>(`/marketing/${planId}/execute-plan90`, { method: 'POST' }),
  getMarketingPlan90: (planId: string) =>
    apiFetch<Plan90DiasTicketsRecord>(`/marketing/${planId}/plan90`),
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
