export type User = { id: string; name: string; email: string; role: 'recruiter' | 'hiring_manager' | 'auditor' | 'hr_admin' }
export type Session = { token: string; user: User }
export type Meta = { model_mode: string; n8n_delivery: boolean; approval_minutes: number; test_mode: boolean; demo_mode: boolean }
export type Attention = { id: string; kind: string; title: string; case_id?: string; case_title?: string; state?: string; expires_at?: string }
export type Overview = {
  generated_at: string
  kpis: { cases: number; cvs_analysed: number; security_alerts: number; pending_approval: number; gateway_sent: number; gateway_refusals: number; ledger_events: number }
  pipeline: { stage: string; count: number; unit: string }[]
  alerts_by_type: { type: string; count: number; max_severity: string }[]
  alerts_by_severity: Record<string, number>
  proposals_by_status: Record<string, number>
  delivery_by_status: Record<string, number>
  activity_trends: {
    cvs_analysed: number[]
    security_alerts: number[]
    approval_activity: number[]
    gateway_sent: number[]
  }
  attention: Attention[]; attention_total: number
  cases: { id: string; title: string; candidate_count: number }[]
  recent_events: { seq: number; ts: string; actor: string; actor_name: string; actor_role: string; type: string; case_id: string | null; subject: string | null; hash: string; prev_hash: string }[]
  assurance: { available: boolean; pass?: number; total?: number; fail?: number; not_run?: number; generated_at?: string; model_mode?: string }
}
export const ERROR_MESSAGES: Record<string, string> = {
  APPROVAL_PAYLOAD_MISMATCH: 'Blocked by the Action Gateway: the action changed after the manager approved it.',
  APPROVAL_REPLAY: 'Blocked: this approval was already used. Each approval works once.',
  APPROVAL_EXPIRED: 'Blocked: the approval expired. Ask the manager to approve again.',
  NO_VALID_APPROVAL: 'Blocked: no manager approval exists for this action.',
  SELF_APPROVAL: "Blocked: you can't approve your own proposal.",
  FORBIDDEN_ROLE: 'Not allowed for your role.',
}
export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message) }
}
export async function api<T>(path: string, token?: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch('/api' + path, { ...options, headers })
  const data = await response.json()
  if (!response.ok) {
    const code = data.error?.code ?? 'REQUEST_FAILED'
    throw new ApiError(code, ERROR_MESSAGES[code] ?? data.error?.message ?? 'Request failed. Please retry.', response.status)
  }
  return data as T
}
export async function apiBlob(path: string, token: string): Promise<Blob> {
  const headers = new Headers()
  headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch('/api' + path, { headers })
  if (!response.ok) {
    let data: { error?: { code?: string; message?: string } } = {}
    try { data = await response.json() as typeof data } catch { /* The response may be a non-JSON server error. */ }
    const code = data.error?.code ?? 'REQUEST_FAILED'
    throw new ApiError(code, ERROR_MESSAGES[code] ?? data.error?.message ?? 'Request failed. Please retry.', response.status)
  }
  return response.blob()
}
export function readSession(): Session | null {
  try { const session = JSON.parse(sessionStorage.getItem('vouch') ?? 'null'); return session?.token && session?.user?.id ? session : null } catch { return null }
}
export const roleName = (role: string) => ({recruiter:'Recruiter',hiring_manager:'Hiring manager',auditor:'Auditor',hr_admin:'HR admin'}[role] ?? role)
export const humanize = (value: string) => value.toLowerCase().replaceAll('_', ' ').replace(/^./, c => c.toUpperCase())
export function timeLabel(value: string) { return new Date(value).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) }
