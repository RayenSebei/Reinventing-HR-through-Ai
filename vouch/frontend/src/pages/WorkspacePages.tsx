import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { formatDistanceToNowStrict } from 'date-fns'
import { useFieldArray, useForm } from 'react-hook-form'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { z } from 'zod'
import { toast } from 'sonner'
import { AlertTriangle, ArrowDown, ArrowUp, CalendarDays, Check, ChevronRight, CircleCheck, Clock3, Download, FileUp, Fingerprint, ListTodo, Mail, Plus, RefreshCw, ShieldCheck, Sparkles, Trash2, Upload, Users } from 'lucide-react'
import { api, apiBlob, ApiError, humanize, type Session } from '@/lib/api'
import { demoInboxMessages } from '@/lib/demoInbox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

z.config({ jitless: true })

type Props = { session: Session }
type CaseItem = {
  id: string; title: string; description: string; created_at: string; criteria: Criterion[]
  criteria_confirmed: boolean; can_edit: boolean; members: { id: string; name: string; role: string }[]
}
type Criterion = { id?: string; label: string; kind: string; weight: number; aliases?: string[] }
type Candidate = {
  id: string; case_id: string; pseudonym: string; case_title: string; created_at: string
  document_id: string | null; finding_count: number; finding_types: string[]; shortlisted: boolean
  display_name?: string; score: number | null; position: number | null
}
type Dossier = {
  candidate_id: string; case_id: string; pseudonym: string
  document: { id: string; sha256: string; pages: number; filename: string } | null
  evidence: { criterion_id: string; criterion: string; status: string; quote: string | null; page: number | null; boxes: Box[]; note: string }[]
  findings: { type: string; severity: string; page: number | null; excerpt: string; boxes: Box[] }[]
}
type ChatInterviewRecord = {
  session: null | { id: string; state: string; language: string | null; expires_at: string; started_at: string | null; ended_at: string | null }
  transcript: { sender: 'assistant' | 'candidate'; text: string; question_id: string | null; response_seconds: number | null; ts: string }[]
  report: null | { statement: string; answered_questions: number; review_flags: { type: string; question_id?: string; categories?: string[] }[]; requirements: { criterion_id: string; criterion: string; cv_evidence: { status: string; quote: string | null; page: number | null }[]; interview_evidence: { answer: string; response_seconds: number; short_answer: boolean }[] }[] }
  decisions: { decision: string; reason: string; created_at: string; decided_by_name: string }[]
}
type Box = { x0: number; top: number; x1: number; bottom: number }
type Ranking = { case_id: string; version: number | null; status: string | null; rows: RankingRow[]; statement?: string }
type RankingRow = { candidate_id: string; pseudonym: string; score: number; position: number; breakdown: { criterion: string; weight: number; status: string }[]; missing: string[]; flags: string[]; justification: string }
type Proposal = {
  id: string; case_id: string; candidate_id: string; kind: string; payload: Record<string, unknown>
  payload_sha256: string; status: string; created_at: string
  approval: null | { decision: string; approved_hash: string; expires_at: string; used_at: string | null; matches_current_payload: boolean }
}
type CandidatePage = { items: Candidate[]; total: number; limit: number; offset: number }
type AuditEvent = { seq: number; ts: string; actor: string; type: string; case_id: string | null; subject: string | null; body: Record<string, unknown>; prev_hash: string; hash: string; mac: string }
type Interview = {
  id: string; case_id: string; candidate_id: string; interviewer_id: string; interview_type: string
  scheduled_start: string; duration_minutes: number; timezone: string; location: string
  status: string; preparation_notes: string; feedback: string; created_at: string; completed_at: string | null
  candidate_pseudonym?: string; case_title?: string; interviewer_name?: string
}
type FollowUpTask = {
  id: string; case_id: string; title: string; description: string; task_type: string; candidate_id: string | null
  interview_id: string | null; proposal_id: string | null; assigned_to: string | null; due_at: string | null
  priority: string; status: string; origin: string; created_at: string; completed_at: string | null
  candidate_pseudonym?: string; case_title?: string; assignee_name?: string
}

function PageTitle({ title, description, actions }: { title: string; description: string; actions?: React.ReactNode }) {
  return <div className="page-title"><div><h1>{title}</h1><p>{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>
}

function QueryError({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="workspace-error" role="alert"><AlertTriangle size={20}/><div><strong>We couldn’t load this view.</strong><p>{message}</p></div>{retry && <Button variant="outline" onClick={retry}>Try again</Button>}</div>
}

function LoadingRows({ count = 4 }: { count?: number }) {
  return <div className="workspace-loading" role="status" aria-label="Loading"><Skeleton className="h-8 w-1/3"/>{Array.from({ length: count }, (_, i) => <Skeleton className="h-12 w-full" key={i}/>)}</div>
}

function NoRows({ title, text }: { title: string; text: string }) {
  return <div className="workspace-empty"><CircleCheck size={23}/><strong>{title}</strong><p>{text}</p></div>
}

function useCases(session: Session) {
  return useQuery({
    queryKey: ['workspace-cases', session.user.id],
    queryFn: () => api<CaseItem[]>('/cases?limit=100', session.token),
    staleTime: 15_000,
  })
}

type CandidateFilters = { sort?: string; order?: string; offset?: number; findingType?: string; shortlisted?: string }

function useCandidates(session: Session, caseId: string, search = '', limit = 100, filters: CandidateFilters = {}) {
  const query = new URLSearchParams({ limit: String(limit), search })
  if (caseId) query.set('case_id', caseId)
  if (filters.sort) query.set('sort', filters.sort)
  if (filters.order) query.set('order', filters.order)
  if (filters.offset !== undefined) query.set('offset', String(filters.offset))
  if (filters.findingType) query.set('finding_type', filters.findingType)
  if (filters.shortlisted) query.set('shortlisted', filters.shortlisted)
  return useQuery({
    queryKey: ['workspace-candidates', session.user.id, caseId, search, limit, filters],
    queryFn: () => api<CandidatePage>(`/candidates?${query}`, session.token),
    enabled: true,
  })
}

export function CasesPage({ session }: Props) {
  const navigate = useNavigate()
  const cases = useCases(session)
  const users = useQuery({ queryKey: ['users'], queryFn: () => api<{ id: string; name: string; role: string }[]>('/users', session.token) })
  const client = useQueryClient()
  const formSchema = z.object({ title: z.string().trim().min(1).max(200), description: z.string().max(5000), manager_id: z.string() })
  const form = useForm<z.infer<typeof formSchema>>({ resolver: zodResolver(formSchema), defaultValues: { title: '', description: '', manager_id: '' } })
  const create = useMutation({
    mutationFn: (body: z.infer<typeof formSchema>) => api<CaseItem>('/cases', session.token, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: async result => { toast.success('Case created. Set and confirm criteria before adding CVs.'); await client.invalidateQueries({ queryKey: ['workspace-cases'] }); navigate(`/cases/${result.id}?tab=scorecard`) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Could not create case.'),
  })
  return <section>
    <PageTitle title="Recruitment" description="Hiring workflows available to your role."/>
    {cases.isPending ? <LoadingRows/> : cases.isError ? <QueryError message={cases.error.message} retry={() => void cases.refetch()}/> :
      <div className="workspace-grid">{cases.data.map(item => <article className="workspace-card case-card" key={item.id}>
        <div className="case-card-icon"><Users size={20}/></div><div><h2><Link to={`/cases/${item.id}`}>{item.title}</Link></h2>
          <p>{item.criteria.length} criteria · {item.criteria_confirmed ? 'Confirmed' : 'Needs review'}</p></div>
        <Link className="panel-link" to={`/cases/${item.id}`}>Open case<ChevronRight size={17}/></Link>
      </article>)}
      {!cases.data.length && <NoRows title="No cases yet" text="Create a case to start a traceable hiring workflow."/>}</div>}
    {session.user.role === 'recruiter' && <section className="surface workspace-form">
      <h2>Create a case</h2><form onSubmit={form.handleSubmit(body => create.mutate(body))} className="stack-form">
        <label>Role title<Input {...form.register('title')} placeholder="e.g. Data analyst"/></label>
        {form.formState.errors.title && <p className="danger">{form.formState.errors.title.message}</p>}
        <label>Description<Textarea {...form.register('description')} placeholder="Describe the role and team context."/></label>
        <label>Hiring manager<select {...form.register('manager_id')}><option value="">Select a manager</option>{users.data?.filter(user => user.role === 'hiring_manager').map(user => <option key={user.id} value={user.id}>{user.name}</option>)}</select></label>
        <Button type="submit" disabled={create.isPending}><Plus size={16}/>Create case</Button>
      </form>
    </section>}
  </section>
}

export function CandidatesPage({ session }: Props) {
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('created_at')
  const [order, setOrder] = useState('desc')
  const [offset, setOffset] = useState(0)
  const limit = 25
  const candidates = useCandidates(session, '', search, limit, { sort, order, offset })
  const page = candidates.data

  return <section>
    <PageTitle title="Candidates" description="Candidates across the cases available to your role. Names appear only after a confirmed shortlist."/>
    <section className="surface workspace-section">
      <div className="table-controls candidate-controls">
        <Input aria-label="Search candidates" placeholder="Search pseudonym or candidate ID" value={search}
          onChange={event => { setSearch(event.target.value); setOffset(0) }}/>
        <label>Sort by<select value={sort} onChange={event => { setSort(event.target.value); setOffset(0) }}>
          <option value="created_at">Recently added</option><option value="pseudonym">Pseudonym</option>
          <option value="finding_count">Findings</option><option value="score">Score</option>
        </select></label>
        <Button variant="outline" aria-label={`Sort ${order === 'desc' ? 'ascending' : 'descending'}`}
          onClick={() => { setOrder(value => value === 'desc' ? 'asc' : 'desc'); setOffset(0) }}>
          {order === 'desc' ? <ArrowDown size={16}/> : <ArrowUp size={16}/>} {order === 'desc' ? 'Descending' : 'Ascending'}
        </Button>
      </div>
      {candidates.isPending ? <LoadingRows/> : candidates.isError ? <QueryError message={candidates.error.message} retry={() => void candidates.refetch()}/> :
        page?.items.length ? <>
          <div className="table-scroll"><Table><TableHeader><TableRow>
            <TableHead>Candidate</TableHead><TableHead>Case</TableHead><TableHead>Evidence score</TableHead>
            <TableHead>Findings</TableHead><TableHead>Shortlist</TableHead><TableHead>Added</TableHead>
          </TableRow></TableHeader><TableBody>{page.items.map(candidate => <TableRow key={candidate.id}>
            <TableCell><Link to={`/cases/${candidate.case_id}?tab=evidence&candidate=${candidate.id}`} className="table-primary" dir="auto">
              {candidate.display_name ?? candidate.pseudonym}</Link><small>{candidate.id}</small></TableCell>
            <TableCell dir="auto">{candidate.case_title}</TableCell>
            <TableCell>{candidate.score === null ? '—' : `${candidate.score}/100`}</TableCell>
            <TableCell>{candidate.finding_count ? <span>{candidate.finding_count} <span className="muted">({candidate.finding_types.map(humanize).join(', ')})</span></span> : 'None recorded'}</TableCell>
            <TableCell><Badge variant="outline" className={candidate.shortlisted ? 'success' : ''}>{candidate.shortlisted ? 'Shortlisted' : 'Not shortlisted'}</Badge></TableCell>
            <TableCell>{new Date(candidate.created_at).toLocaleDateString()}</TableCell>
          </TableRow>)}</TableBody></Table></div>
          <div className="pagination"><span>{page.total ? `${offset + 1}–${Math.min(offset + page.items.length, page.total)} of ${page.total}` : '0 candidates'}</span>
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - limit))}>Previous</Button>
            <Button variant="outline" size="sm" disabled={offset + limit >= page.total} onClick={() => setOffset(value => value + limit)}>Next</Button>
          </div>
        </> : <NoRows title="No candidates found" text={search ? 'Try another search term.' : 'Upload a CV in a recruitment case to add candidates.'}/>}
    </section>
  </section>
}

export function InboxPage({ session }: Props) {
  const [selectedId, setSelectedId] = useState(demoInboxMessages[0]?.id ?? '')
  const [filter, setFilter] = useState('All')
  const selected = demoInboxMessages.find(message => message.id === selectedId)
  const visible = demoInboxMessages.filter(message => filter === 'All' || message.category === filter)

  return <section>
    <PageTitle title="AI Inbox" description="A preview of a future inbox workflow; this workspace is not connected to a mailbox."/>
    <div className="warning-box inbox-demo-notice" role="note"><Mail size={18}/><span><strong>Demonstration inbox.</strong> All messages and summaries are synthetic. No mailbox, AI model, approval, or delivery is connected for this {humanize(session.user.role)} session.</span></div>
    <div className="inbox-layout">
      <section className="surface inbox-list-panel" aria-label="Synthetic messages">
        <div className="inbox-filters">{['All', ...new Set(demoInboxMessages.map(message => message.category))].map(category =>
          <Button key={category} size="sm" variant={filter === category ? 'default' : 'outline'} onClick={() => {
            setFilter(category)
            const first = category === 'All' ? demoInboxMessages[0] : demoInboxMessages.find(message => message.category === category)
            if (first) setSelectedId(first.id)
          }}>{category}</Button>)}</div>
        {visible.length ? visible.map(message => <button key={message.id} type="button" className={`inbox-message ${selectedId === message.id ? 'selected' : ''}`}
          onClick={() => setSelectedId(message.id)} aria-pressed={selectedId === message.id}>
          <span className="inbox-message-heading"><strong dir="auto">{message.sender}</strong><time>{new Date(message.receivedAt).toLocaleDateString()}</time></span>
          <span className="inbox-message-subject" dir="auto">{message.subject}</span><span className="inbox-message-preview" dir="auto">{message.body}</span>
        </button>) : <NoRows title="No messages in this filter" text="Select another category to view synthetic examples."/>}
      </section>
      {selected ? <section className="surface inbox-detail">
        <div className="panel-heading"><div><Badge variant="outline">Synthetic message</Badge><h2 dir="auto">{selected.subject}</h2><p dir="auto">{selected.sender} · {selected.category}</p></div><Mail size={21}/></div>
        <div className="inbox-message-body" dir="auto">{selected.body}</div>
        <section className="inbox-suggestion"><h3><Sparkles size={16}/> Example summary</h3><p dir="auto">{selected.summary}</p><small>Prewritten sample; no AI request was made.</small></section>
        <section className="inbox-suggestion"><h3>Example reply</h3><p dir="auto">{selected.reply}</p><small>This text is a demo only. It cannot be approved or sent.</small></section>
      </section> : <section className="surface inbox-detail"><NoRows title="Select a message" text="Choose one of the synthetic messages to review the demonstration summary."/></section>}
    </div>
  </section>
}

const criterionSchema = z.object({
  label: z.string().trim().min(1, 'Enter a criterion label.').max(200),
  kind: z.enum(['skill', 'experience', 'education', 'project', 'certification', 'other']),
  weight: z.coerce.number().int().min(0).max(100),
  aliases: z.string(),
})
const scorecardSchema = z.object({ criteria: z.array(criterionSchema).min(1) }).superRefine((value, ctx) => {
  const total = value.criteria.reduce((sum, item) => sum + item.weight, 0)
  if (total !== 100) ctx.addIssue({ code: 'custom', message: `Weights must total 100 (currently ${total}).`, path: ['criteria'] })
})
type ScorecardInput = z.input<typeof scorecardSchema>
type ScorecardForm = z.output<typeof scorecardSchema>
const BIAS_WORDS = /\b(young|energetic|native speaker|culture fit|digital native|recent graduate|strong man|mature)\b/i

function Scorecard({ session, caseItem }: { session: Session; caseItem: CaseItem }) {
  const client = useQueryClient()
  const form = useForm<ScorecardInput, unknown, ScorecardForm>({ resolver: zodResolver(scorecardSchema), defaultValues: { criteria: [] }, mode: 'onChange' })
  const resetForm = form.reset
  const fields = useFieldArray({ control: form.control, name: 'criteria' })
  const criteria = form.watch('criteria') ?? []
  useEffect(() => {
    resetForm({ criteria: caseItem.criteria.map(item => ({ label: item.label, kind: item.kind as ScorecardForm['criteria'][number]['kind'], weight: item.weight, aliases: item.aliases?.join(', ') ?? '' })) })
  }, [caseItem.criteria, resetForm])
  const save = useMutation({
    mutationFn: (value: ScorecardForm) => api<CaseItem>(`/cases/${caseItem.id}/criteria`, session.token, {
      method: 'PUT', body: JSON.stringify({ criteria: value.criteria.map(item => ({ ...item, aliases: item.aliases.split(',').map(alias => alias.trim()).filter(Boolean) })) }),
    }),
    onSuccess: async () => { toast.success('Criteria saved.'); await client.invalidateQueries({ queryKey: ['workspace-case', caseItem.id] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Criteria could not be saved.'),
  })
  const confirm = useMutation({
    mutationFn: () => api(`/cases/${caseItem.id}/criteria/confirm`, session.token, { method: 'POST', body: '{}' }),
    onSuccess: async () => { toast.success('Criteria confirmed.'); await client.invalidateQueries({ queryKey: ['workspace-case', caseItem.id] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Criteria could not be confirmed.'),
  })
  const total = criteria.reduce((sum, item) => sum + (Number(item.weight) || 0), 0)
  const warnings = criteria.filter(item => BIAS_WORDS.test(item.label))
  return <section className="surface workspace-section">
    <div className="panel-heading"><div><h2>Scorecard</h2><p>Set job-related criteria. The weights must total 100.</p></div><Badge variant="outline">{caseItem.criteria_confirmed ? 'Confirmed' : 'Draft'}</Badge></div>
    {warnings.length > 0 && <div className="warning-box"><AlertTriangle size={18}/><span>Review potentially subjective wording: {warnings.map(item => item.label).join('; ')}</span></div>}
    <form onSubmit={form.handleSubmit(value => save.mutate(value))} className="stack-form">
      {fields.fields.map((field, index) => <div className="criterion-row" key={field.id}>
        <label>Criterion<Input {...form.register(`criteria.${index}.label`)} dir="auto"/></label>
        <label>Type<select {...form.register(`criteria.${index}.kind`)}>{['skill', 'experience', 'education', 'project', 'certification', 'other'].map(kind => <option key={kind} value={kind}>{humanize(kind)}</option>)}</select></label>
        <label>Weight (%)<Input type="number" min="0" max="100" {...form.register(`criteria.${index}.weight`, { valueAsNumber: true })}/></label>
        <label>Aliases<Input {...form.register(`criteria.${index}.aliases`)} placeholder="Separate with commas"/></label>
        {caseItem.can_edit && <Button type="button" variant="ghost" size="icon" aria-label={`Remove criterion ${index + 1}`} onClick={() => fields.remove(index)}><Trash2 size={17}/></Button>}
      </div>)}
      <div className="weight-total" aria-live="polite"><strong>Total weight</strong><strong className={total === 100 ? 'success' : 'danger'}>{total}%</strong></div>
      {form.formState.errors.criteria && <p className="danger" role="alert">{form.formState.errors.criteria.message}</p>}
      {caseItem.can_edit && <div className="page-actions">
        <Button type="button" variant="outline" onClick={() => fields.append({ label: '', kind: 'skill', weight: 0, aliases: '' })}><Plus size={16}/>Add criterion</Button>
        <Button type="submit" disabled={!form.formState.isValid || save.isPending}>Save scorecard</Button>
        <Button type="button" variant="outline" onClick={() => confirm.mutate()} disabled={total !== 100 || confirm.isPending}>Confirm criteria</Button>
      </div>}
    </form>
    <p className="honest-note">Nobody is rejected automatically. Criteria support human review; they do not make a hiring decision.</p>
  </section>
}

type UploadStatus = { name: string; state: 'queued' | 'uploading' | 'done' | 'duplicate' | 'failed'; message?: string }

function Candidates({ session, caseItem }: { session: Session; caseItem: CaseItem }) {
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('created_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [findingType, setFindingType] = useState('')
  const [shortlisted, setShortlisted] = useState('')
  const [uploads, setUploads] = useState<UploadStatus[]>([])
  const [dragging, setDragging] = useState(false)
  const client = useQueryClient()
  const limit = 10
  const candidates = useCandidates(session, caseItem.id, search, limit, { sort, order, offset, findingType, shortlisted })
  async function uploadFiles(files: FileList | File[]) {
    const pdfs = Array.from(files).filter(file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) { toast.error('Choose PDF files.'); return }
    const state = pdfs.map(file => ({ name: file.name, state: 'queued' as const }))
    setUploads(state)
    for (let index = 0; index < pdfs.length; index += 1) {
      const file = pdfs[index]
      setUploads(current => current.map((item, i) => i === index ? { ...item, state: 'uploading' } : item))
      const form = new FormData()
      form.append('file', file)
      try {
        await api(`/cases/${caseItem.id}/candidates`, session.token, { method: 'POST', body: form })
        setUploads(current => current.map((item, i) => i === index ? { ...item, state: 'done' } : item))
      } catch (error) {
        const duplicate = error instanceof ApiError && error.code === 'DUPLICATE_DOCUMENT'
        const message = error instanceof Error ? error.message : 'Upload failed.'
        setUploads(current => current.map((item, i) => i === index ? { ...item, state: duplicate ? 'duplicate' : 'failed', message } : item))
      }
    }
    await client.invalidateQueries({ queryKey: ['workspace-candidates', session.user.id, caseItem.id] })
  }
  const complete = uploads.filter(item => item.state === 'done' || item.state === 'duplicate' || item.state === 'failed').length
  return <section className="surface workspace-section">
    <div className="panel-heading"><div><h2>Candidates</h2><p>CV text is shown as plain text; identities remain masked until a shortlist is confirmed.</p></div><Badge variant="outline">{candidates.data?.total ?? 0} records</Badge></div>
    {caseItem.can_edit && <div className={`upload-zone ${dragging ? 'is-dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
      onDrop={event => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length) void uploadFiles(event.dataTransfer.files) }}>
      <FileUp size={26}/><strong>Drop PDF CVs here</strong><span>Or choose multiple files. Each file has an independent result.</span>
      <label className="button-like" htmlFor={`cv-upload-${caseItem.id}`}><Upload size={15}/>Choose PDFs</label>
      <input id={`cv-upload-${caseItem.id}`} type="file" accept="application/pdf,.pdf" multiple onChange={event => { if (event.target.files) void uploadFiles(event.target.files); event.target.value = '' }}/>
      {uploads.length > 0 && <div className="upload-progress"><progress className="upload-native-progress" value={complete} max={uploads.length} aria-label={`${complete} of ${uploads.length} files processed`}/><span>{complete} of {uploads.length} files processed</span>
        {uploads.map((file, index) => <div className="upload-file" key={`${file.name}-${index}`}><span dir="auto">{file.name}</span><Badge variant="outline">{humanize(file.state)}</Badge>{file.state === 'duplicate' && <span className="warning-text">Duplicate CV: {file.message}</span>}{file.state === 'failed' && <span className="danger">{file.message}</span>}</div>)}
      </div>}
    </div>}
    <div className="table-controls"><Input aria-label="Search candidates" value={search} onChange={event => { setSearch(event.target.value); setOffset(0) }} placeholder="Search pseudonym or candidate ID"/>
      <label>Sort<select value={sort} onChange={event => setSort(event.target.value)}><option value="created_at">Recently added</option><option value="pseudonym">Pseudonym</option><option value="finding_count">Findings</option><option value="score">Score</option></select></label>
      <Button variant="outline" onClick={() => setOrder(current => current === 'asc' ? 'desc' : 'asc')} aria-label={`Sort ${order === 'asc' ? 'descending' : 'ascending'}`}>{order === 'asc' ? <ArrowUp size={16}/> : <ArrowDown size={16}/>}</Button>
      <label>Finding type<Input aria-label="Filter by finding type" value={findingType} onChange={event => { setFindingType(event.target.value); setOffset(0) }} placeholder="e.g. HIDDEN_TEXT"/></label>
      <label>Shortlist<select value={shortlisted} onChange={event => { setShortlisted(event.target.value); setOffset(0) }}><option value="">All candidates</option><option value="true">Shortlisted</option><option value="false">Not shortlisted</option></select></label>
    </div>
    {candidates.isPending ? <LoadingRows/> : candidates.isError ? <QueryError message={candidates.error.message} retry={() => void candidates.refetch()}/> :
      candidates.data.items.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Candidate</TableHead><TableHead>Added</TableHead><TableHead>Score</TableHead><TableHead>Findings</TableHead><TableHead>Shortlist</TableHead></TableRow></TableHeader>
        <TableBody>{candidates.data.items.map(candidate => <TableRow key={candidate.id}>
          <TableCell><Link to={`/cases/${caseItem.id}?tab=evidence&candidate=${candidate.id}`} className="table-primary" dir="auto">{candidate.display_name ?? candidate.pseudonym}</Link><small>{candidate.id}</small></TableCell>
          <TableCell>{new Date(candidate.created_at).toLocaleDateString()}</TableCell><TableCell>{candidate.score ?? '—'}</TableCell>
          <TableCell>{candidate.finding_types.length ? candidate.finding_types.map(type => <Badge variant="outline" key={type} className="finding-badge">{humanize(type)}</Badge>) : 'No findings'}</TableCell>
          <TableCell>{candidate.shortlisted ? <Badge className="success">Confirmed</Badge> : 'Not selected'}</TableCell>
        </TableRow>)}</TableBody></Table></div> : <NoRows title="No candidates found" text={search ? 'Try another search.' : 'Upload PDF CVs to review evidence.'}/>}
    {candidates.data && <div className="pagination"><span>Showing {Math.min(offset + 1, candidates.data.total)}–{Math.min(offset + limit, candidates.data.total)} of {candidates.data.total}</span>
      <Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</Button>
      <Button variant="outline" disabled={offset + limit >= candidates.data.total} onClick={() => setOffset(offset + limit)}>Next</Button></div>}
  </section>
}

function useObjectUrl(blob: Blob | undefined) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    if (!blob) { setUrl(''); return }
    const next = URL.createObjectURL(blob)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [blob])
  return url
}

function ChatInterviewEvidence({ session, candidateId }: { session: Session; candidateId: string }) {
  const client = useQueryClient()
  const record = useQuery({
    queryKey: ['chat-interview', candidateId],
    queryFn: () => api<ChatInterviewRecord>(`/candidates/${candidateId}/interview`, session.token),
    enabled: !!candidateId,
  })
  const [openedReport, setOpenedReport] = useState<ChatInterviewRecord | null>(null)
  const [decision, setDecision] = useState('hold')
  const [reason, setReason] = useState('')
  useEffect(() => { setOpenedReport(null); setReason('') }, [candidateId])
  const openReport = useMutation({
    mutationFn: () => api<ChatInterviewRecord>(`/candidates/${candidateId}/interview/report`, session.token),
    onSuccess: value => { setOpenedReport(value); toast.success('Combined evidence report opened and recorded in the audit trail.') },
    onError: error => toast.error(error instanceof Error ? error.message : 'The report could not be opened.'),
  })
  const saveDecision = useMutation({
    mutationFn: () => api(`/candidates/${candidateId}/decision`, session.token, { method: 'POST', body: JSON.stringify({ decision, reason }) }),
    onSuccess: async () => { toast.success('Human decision recorded with its reason.'); setReason(''); await client.invalidateQueries({ queryKey: ['chat-interview', candidateId] }); if (openedReport) setOpenedReport(await api<ChatInterviewRecord>(`/candidates/${candidateId}/interview/report`, session.token)) },
    onError: error => toast.error(error instanceof Error ? error.message : 'The decision could not be recorded.'),
  })
  if (record.isPending) return <LoadingRows count={2}/>
  if (record.isError) return <QueryError message={record.error.message} retry={() => void record.refetch()}/>
  const data = record.data
  if (!data.session) return <NoRows title="No chat interview yet" text="Create, approve, and execute an interview invitation to issue a one-time candidate link."/>
  const canDecide = session.user.role === 'recruiter' || session.user.role === 'hiring_manager'
  return <section className="chat-evidence">
    <div className="panel-heading"><div><h3>Candidate chat interview</h3><p>Timed candidate answers are evidence for human review, never an automated decision.</p></div><Badge variant="outline">{humanize(data.session.state)}</Badge></div>
    <div className="chat-transcript" aria-label="Interview transcript">{data.transcript.length ? data.transcript.map((message, index) => <article className={`transcript-message ${message.sender}`} key={`${message.ts}-${index}`}>
      <strong>{message.sender === 'assistant' ? 'Vouch assistant' : 'Candidate'}</strong><p dir="auto">{message.text}</p>
      {message.sender === 'candidate' && message.response_seconds !== null && <small>Answered in {formatDuration(message.response_seconds)}</small>}
    </article>) : <p>No answers have been recorded.</p>}</div>
    {data.report ? <div className="report-gate"><p><strong>Combined CV + interview evidence is available.</strong> Opening it is audit-recorded and required before a human decision.</p><Button variant="outline" disabled={openReport.isPending} onClick={() => openReport.mutate()}>{openReport.isPending ? 'Opening…' : 'Open combined evidence report'}</Button></div> : <div className="honest-note">The combined report appears when the candidate completes or ends the chat interview.</div>}
    {openedReport?.report && <section className="combined-report"><div className="warning-box"><Fingerprint size={18}/><span>{openedReport.report.statement}</span></div>
      {openedReport.report.review_flags.length > 0 && <div><h4>Review flags</h4>{openedReport.report.review_flags.map((flag, index) => <Badge variant="outline" className="severity high" key={`${flag.type}-${index}`}>{humanize(flag.type)}</Badge>)}</div>}
      <div className="report-requirements">{openedReport.report.requirements.map(requirement => <article key={requirement.criterion_id}><h4 dir="auto">{requirement.criterion}</h4>
        <div><strong>CV evidence</strong>{requirement.cv_evidence.length ? requirement.cv_evidence.map((item, index) => <p key={index} dir="auto"><Badge variant="outline">{humanize(item.status)}</Badge> {item.quote || 'No sourced quote'}</p>) : <p>No CV evidence.</p>}</div>
        <div><strong>Interview evidence</strong>{requirement.interview_evidence.length ? requirement.interview_evidence.map((item, index) => <blockquote key={index} dir="auto">{item.answer}<small>{formatDuration(item.response_seconds)} response{item.short_answer ? ' · short answer flag' : ''}</small></blockquote>) : <p>No interview answer linked to this criterion.</p>}</div>
      </article>)}</div>
    </section>}
    {data.decisions.length > 0 && <section><h4>Recorded human decisions</h4>{data.decisions.map((item, index) => <article className="decision-record" key={`${item.created_at}-${index}`}><Badge variant="outline">{humanize(item.decision)}</Badge><p dir="auto">{item.reason}</p><small>{item.decided_by_name} · {new Date(item.created_at).toLocaleString()}</small></article>)}</section>}
    {canDecide && openedReport?.report && <form className="decision-form" onSubmit={event => { event.preventDefault(); saveDecision.mutate() }}><h4>Record a human decision</h4><label>Decision<select value={decision} onChange={event => setDecision(event.target.value)}><option value="advance">Advance</option><option value="hold">Hold</option><option value="reject">Reject</option></select></label><label>Job-related reason<Textarea required minLength={15} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)}/></label><Button type="submit" disabled={saveDecision.isPending || reason.trim().length < 15}>Record decision</Button></form>}
  </section>
}

function Evidence({ session, caseItem }: { session: Session; caseItem: CaseItem }) {
  const candidates = useCandidates(session, caseItem.id)
  const [searchParams, setSearchParams] = useSearchParams()
  const [candidateId, setCandidateId] = useState(searchParams.get('candidate') ?? '')
  const [pageNo, setPageNo] = useState(1)
  useEffect(() => { if (!candidateId && candidates.data?.items[0]) setCandidateId(candidates.data.items[0].id) }, [candidateId, candidates.data])
  const dossier = useQuery({
    queryKey: ['candidate-dossier', candidateId],
    queryFn: () => api<Dossier>(`/candidates/${candidateId}/dossier`, session.token),
    enabled: !!candidateId,
  })
  const documentId = dossier.data?.document?.id
  const extraction = useQuery({
    queryKey: ['document-extraction', documentId],
    queryFn: () => api<{ visible_text: string; hidden_text: string; pages: { number: number; width: number; height: number }[] }>(`/documents/${documentId}/extraction`, session.token),
    enabled: !!documentId,
  })
  const page = extraction.data?.pages.find(item => item.number === pageNo) ?? extraction.data?.pages[0]
  useEffect(() => { if (page && page.number !== pageNo) setPageNo(page.number) }, [page, pageNo])
  const image = useQuery({
    queryKey: ['document-page', documentId, page?.number],
    queryFn: () => apiBlob(`/documents/${documentId}/pages/${page?.number}.png`, session.token),
    enabled: !!documentId && !!page,
  })
  const imageUrl = useObjectUrl(image.data)
  return <section className="surface workspace-section">
    <div className="panel-heading"><div><h2>Evidence review</h2><p>Compare visible source text, findings, and criterion-level quotes.</p></div>
      <select aria-label="Choose candidate" value={candidateId} onChange={event => { setCandidateId(event.target.value); setSearchParams(current => { const next = new URLSearchParams(current); if (event.target.value) next.set('candidate', event.target.value); else next.delete('candidate'); return next }, { replace: true }) }}><option value="">Choose candidate</option>{candidates.data?.items.map(item => <option key={item.id} value={item.id}>{item.pseudonym}</option>)}</select>
    </div>
    {candidates.isPending || (!!candidateId && dossier.isPending) ? <LoadingRows/> :
      !candidateId ? <NoRows title="No candidate selected" text="Upload a CV or choose a candidate."/> :
      dossier.isError ? <QueryError message={dossier.error.message} retry={() => void dossier.refetch()}/> :
      <>
        <div className="evidence-layout">
          <div className="cv-preview">
            <div className="panel-heading"><strong>CV page</strong>{extraction.data?.pages.length ? <select aria-label="Choose CV page" value={pageNo} onChange={event => setPageNo(Number(event.target.value))}>{extraction.data.pages.map(item => <option value={item.number} key={item.number}>Page {item.number}</option>)}</select> : null}</div>
            {extraction.isPending || image.isPending ? <Skeleton className="cv-page-skeleton"/> : extraction.isError ? <QueryError message={extraction.error.message} retry={() => void extraction.refetch()}/> : image.isError ? <QueryError message={image.error.message} retry={() => void image.refetch()}/> :
              imageUrl && page ? <div className="cv-page">
                <img src={imageUrl} alt={`Redacted CV page ${page.number}`} />
                <svg className="evidence-overlay" viewBox={`0 0 ${page.width} ${page.height}`} preserveAspectRatio="none" aria-label="Evidence locations">
                  {dossier.data?.evidence.filter(item => item.page === page.number).flatMap((item, index) => item.boxes.map((box, boxIndex) =>
                    <rect key={`${item.criterion_id}-${index}-${boxIndex}`} x={box.x0} y={box.top} width={box.x1 - box.x0} height={box.bottom - box.top} className={`overlay-box ${item.status.toLowerCase()}`}/>))}
                  {dossier.data?.findings.filter(item => item.page === page.number).flatMap((item, index) => item.boxes.map((box, boxIndex) =>
                    <rect key={`${item.type}-${index}-${boxIndex}`} x={box.x0} y={box.top} width={box.x1 - box.x0} height={box.bottom - box.top} className="overlay-box suspicious"/>))}
                </svg>
              </div> : <NoRows title="No page image" text="This candidate has no readable CV page."/>}
            <div className="evidence-legend"><span className="sourced">Sourced claim</span><span className="needs-review">Needs review</span><span className="suspicious">Suspicious content</span></div>
          </div>
          <div className="evidence-source"><h3>Visible text</h3><pre dir="auto">{extraction.data?.visible_text || 'No visible text was extracted.'}</pre>
            <details><summary>Hidden text panel</summary><pre dir="auto">{extraction.data?.hidden_text || 'No hidden text was detected.'}</pre></details>
          </div>
        </div>
        <section className="evidence-table-section"><h3>Criterion evidence</h3>
          {dossier.data?.evidence.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Criterion</TableHead><TableHead>Quote</TableHead><TableHead>Page</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
            <TableBody>{dossier.data.evidence.map(item => <TableRow key={item.criterion_id}><TableCell dir="auto">{item.criterion}</TableCell><TableCell className="quote-cell" dir="auto">{item.quote || 'No evidence found'}{item.note && <small>{item.note}</small>}</TableCell><TableCell>{item.page ?? '—'}</TableCell><TableCell><Badge variant="outline" className={`evidence-status ${item.status.toLowerCase()}`}>{humanize(item.status)}</Badge></TableCell></TableRow>)}</TableBody></Table></div> :
            <NoRows title="No evidence entries" text="Evidence appears after the CV is analyzed against confirmed criteria."/>}
        </section>
        <section className="findings-list"><h3>Findings</h3>{dossier.data?.findings.length ? dossier.data.findings.map((item, index) =>
          <article key={`${item.type}-${index}`}><Badge variant="outline" className={`severity ${item.severity}`}>{item.severity}</Badge><strong>{humanize(item.type)}</strong><span dir="auto">{item.excerpt}</span></article>) :
          <NoRows title="No findings" text="No document findings are associated with this CV."/>}</section>
        <ChatInterviewEvidence session={session} candidateId={candidateId}/>
      </>}
  </section>
}

function RankingView({ session, caseItem }: { session: Session; caseItem: CaseItem }) {
  const client = useQueryClient()
  const ranking = useQuery({
    queryKey: ['ranking', caseItem.id],
    queryFn: () => api<Ranking>(`/cases/${caseItem.id}/ranking`, session.token),
  })
  const [selected, setSelected] = useState<string[]>([])
  const [topReviewed, setTopReviewed] = useState(false)
  const [blindMode, setBlindMode] = useState(false)
  const draft = useMutation({
    mutationFn: () => api<Ranking>(`/cases/${caseItem.id}/ranking`, session.token, { method: 'POST', body: '{}' }),
    onSuccess: async () => { toast.success('Draft ranking created.'); setSelected([]); setTopReviewed(false); await client.invalidateQueries({ queryKey: ['ranking', caseItem.id] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Ranking could not be created.'),
  })
  const shortlist = useMutation({
    mutationFn: () => api<Ranking>(`/cases/${caseItem.id}/ranking/${ranking.data?.version}/shortlist`, session.token,
      { method: 'POST', body: JSON.stringify({ candidate_ids: selected }) }),
    onSuccess: async () => { toast.success('Explicit shortlist confirmed.'); await client.invalidateQueries({ queryKey: ['ranking', caseItem.id] }); await client.invalidateQueries({ queryKey: ['workspace-candidates'] }); await client.invalidateQueries({ queryKey: ['candidate-dossier'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Shortlist could not be confirmed.'),
  })
  const rows = ranking.data?.rows ?? []
  const positionCounts = new Map<number, number>()
  for (const row of rows) positionCounts.set(row.position, (positionCounts.get(row.position) ?? 0) + 1)
  function toggle(id: string) { setSelected(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id]) }
  return <section className="surface workspace-section">
    <div className="panel-heading"><div><h2>Ranking</h2><p>Scores are an aid to review, never an automatic decision.</p></div>
      <label className="inline-switch"><Switch checked={blindMode} onCheckedChange={setBlindMode}/>Blind review</label></div>
    <div className="page-actions"><Button onClick={() => draft.mutate()} disabled={draft.isPending}>Create ranking draft</Button>
      <Button variant="outline" onClick={() => void ranking.refetch()} disabled={ranking.isFetching}><RefreshCw size={16}/>Refresh</Button></div>
    {ranking.isPending ? <LoadingRows/> : ranking.isError ? <QueryError message={ranking.error.message} retry={() => void ranking.refetch()}/> :
      rows.length ? <>
        <div className="weight-total"><span>Ranking version {ranking.data.version} · {humanize(ranking.data.status ?? '')}</span><span>{rows.length} candidates</span></div>
        <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Shortlist</TableHead><TableHead>Rank</TableHead><TableHead>Candidate</TableHead><TableHead>{blindMode ? 'Score hidden' : 'Score'}</TableHead><TableHead>Breakdown</TableHead><TableHead>Review flags</TableHead></TableRow></TableHeader>
          <TableBody>{rows.map(row => <TableRow key={row.candidate_id}>
            <TableCell><Checkbox aria-label={`Select ${row.pseudonym} for shortlist`} checked={selected.includes(row.candidate_id)} onCheckedChange={() => toggle(row.candidate_id)}/></TableCell>
            <TableCell>{(positionCounts.get(row.position) ?? 0) > 1 ? `${row.position} (tie)` : row.position}</TableCell><TableCell><span dir="auto">{row.pseudonym}</span></TableCell><TableCell>{blindMode ? '—' : row.score}</TableCell>
            <TableCell>{row.breakdown.map((part, index) => <span className="breakdown-chip" key={`${part.criterion}-${index}`}><span dir="auto">{part.criterion}</span>: {humanize(part.status)} ({part.weight}%)</span>)}</TableCell>
            <TableCell>{row.flags.length ? row.flags.map(flag => <Badge variant="outline" key={flag} className="finding-badge">{humanize(flag)}</Badge>) : 'No flags'}</TableCell>
          </TableRow>)}</TableBody></Table></div>
        <p className="honest-note" dir="auto">{ranking.data.statement ?? 'Nobody is rejected automatically.'}</p>
        {caseItem.can_edit && ranking.data.status === 'DRAFT' && <>
          <label className="review-gate"><Checkbox checked={topReviewed} onCheckedChange={value => setTopReviewed(value === true)}/>I reviewed the top three candidates and their evidence.</label>
          <Button onClick={() => shortlist.mutate()} disabled={!topReviewed || !selected.length || shortlist.isPending}>Confirm selected shortlist ({selected.length})</Button>
        </>}
      </> : <NoRows title="No ranking yet" text="Create a ranking draft after criteria and candidate evidence are ready."/>}
  </section>
}

function CompareView({ session, caseItem }: { session: Session; caseItem: CaseItem }) {
  const candidates = useCandidates(session, caseItem.id)
  const [selected, setSelected] = useState<string[]>([])
  const [compared, setCompared] = useState<{ candidates: { id: string; pseudonym: string; score: number | null; position: number | null; evidence: Dossier['evidence']; findings: Dossier['findings'] }[] } | null>(null)
  const [error, setError] = useState('')
  async function compare() {
    setError('')
    try { setCompared(await api(`/candidates/compare?candidate_ids=${encodeURIComponent(selected.join(','))}`, session.token)) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Comparison failed.') }
  }
  return <section className="surface workspace-section"><h2>Compare candidates</h2><p>Select two to four candidates from this case.</p>
    {candidates.isPending ? <LoadingRows/> : candidates.isError ? <QueryError message={candidates.error.message}/> : <>
      <div className="candidate-check-list">{candidates.data.items.map(candidate => <label key={candidate.id}><Checkbox checked={selected.includes(candidate.id)} disabled={!selected.includes(candidate.id) && selected.length >= 4}
        onCheckedChange={checked => setSelected(current => checked ? [...current, candidate.id] : current.filter(id => id !== candidate.id))}/><span dir="auto">{candidate.pseudonym}</span></label>)}</div>
      <Button onClick={() => void compare()} disabled={selected.length < 2 || selected.length > 4}>Compare {selected.length} candidates</Button>
    </>}
    {error && <QueryError message={error}/>}
    {compared && <div className="compare-grid">{compared.candidates.map(candidate => <article className="compare-card" key={candidate.id}>
      <h3 dir="auto">{candidate.pseudonym}</h3><p>Score {candidate.score ?? '—'} · Position {candidate.position ?? '—'}</p>
      <h4>Evidence</h4>{candidate.evidence.map(item => <div className="compare-evidence" key={item.criterion_id}><strong dir="auto">{item.criterion}</strong><Badge variant="outline">{humanize(item.status)}</Badge><p dir="auto">{item.quote || 'No evidence found'}</p></div>)}
      <h4>Findings</h4>{candidate.findings.length ? candidate.findings.map((item, index) => <p dir="auto" key={`${item.type}-${index}`}>{humanize(item.type)} · {item.excerpt}</p>) : <p>No findings.</p>}
    </article>)}</div>}
  </section>
}

function proposalState(proposal: Proposal) {
  if (proposal.status === 'EXECUTED') return 'sent'
  if (!proposal.approval) return 'pending'
  if (proposal.approval.decision !== 'approved') return 'rejected'
  if (!proposal.approval.matches_current_payload) return 'changed'
  if (proposal.approval.used_at) return 'used'
  if (Date.parse(proposal.approval.expires_at) <= Date.now()) return 'expired'
  return 'approved'
}

function ApprovalCountdown({ expiresAt }: { expiresAt: string }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const seconds = Math.max(0, Math.floor((Date.parse(expiresAt) - now) / 1000))
  return <span className={seconds ? 'countdown' : 'countdown danger'}>{seconds ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} remaining` : 'Approval expired'}</span>
}

function ProposalCard({ proposal, session, allowEdit = false, allowExecute = false }: { proposal: Proposal; session: Session; allowEdit?: boolean; allowExecute?: boolean }) {
  const client = useQueryClient()
  const [body, setBody] = useState(String(proposal.payload.body ?? ''))
  const [subject, setSubject] = useState(String(proposal.payload.subject ?? ''))
  const state = proposalState(proposal)
  const originalBody = String(proposal.payload.body ?? '')
  const originalSubject = String(proposal.payload.subject ?? '')
  const payloadChanged = body !== originalBody || subject !== originalSubject
  const update = useMutation({
    mutationFn: () => api<Proposal>(`/proposals/${proposal.id}`, session.token,
      { method: 'PATCH', body: JSON.stringify({ body, subject }) }),
    onSuccess: async () => { toast.success('Payload updated. Any earlier approval remains bound to its original hash.'); await client.invalidateQueries({ queryKey: ['case-proposals'] }); await client.invalidateQueries({ queryKey: ['approval-inbox'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Proposal could not be edited.'),
  })
  const execute = useMutation({
    mutationFn: () => api(`/proposals/${proposal.id}/execute`, session.token, { method: 'POST', body: '{}' }),
    onSuccess: async () => {
      toast.success('Action sent through the Action Gateway.')
      await client.invalidateQueries({ queryKey: ['case-proposals'] })
      await client.invalidateQueries({ queryKey: ['approval-inbox'] })
      await client.invalidateQueries({ queryKey: ['workspace-outbox'] })
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'The Action Gateway refused this action.'),
  })
  return <article className="proposal-card">
    <div className="panel-heading"><div><h3>{humanize(proposal.kind)} · {proposal.id}</h3><p>{formatDistanceToNowStrict(new Date(proposal.created_at), { addSuffix: true })}</p></div><Badge variant="outline" className={`state-badge ${state}`}>{humanize(state)}</Badge></div>
    <div className="hash-block"><span>Current SHA-256</span><code>{proposal.payload_sha256}</code></div>
    {proposal.approval && <div className="hash-block"><span>Manager-approved SHA-256</span><code>{proposal.approval.approved_hash}</code></div>}
    {proposal.approval && !proposal.approval.matches_current_payload && <div className="warning-box"><AlertTriangle size={18}/><span>Payload changed after approval. The Action Gateway will refuse execution until a manager approves the current hash.</span></div>}
    {proposal.approval?.expires_at && proposal.approval.decision === 'approved' && !proposal.approval.used_at && <p className="approval-time"><ApprovalCountdown expiresAt={proposal.approval.expires_at}/></p>}
    {allowEdit ? <div className="stack-form"><label>Subject<Input value={subject} onChange={event => setSubject(event.target.value)} maxLength={200}/></label><label>Exact message body<Textarea dir="auto" value={body} onChange={event => setBody(event.target.value)} maxLength={5000}/></label>
      <div className="payload-diff" aria-live="polite"><strong>{payloadChanged ? 'Unsaved payload changes' : 'Current payload preview'}</strong>
        {(payloadChanged ? [{ label: 'Subject', before: originalSubject, after: subject }, { label: 'Body', before: originalBody, after: body }] : [{ label: 'Subject', before: subject, after: subject }, { label: 'Body', before: body, after: body }]).map(change =>
          <div className="diff-row" key={change.label}><span>{change.label}</span><div><small>{payloadChanged ? 'Before' : 'Current'}</small><pre dir="auto">{change.before || '(empty)'}</pre></div>{payloadChanged && <div><small>After</small><pre dir="auto">{change.after || '(empty)'}</pre></div>}</div>)}
      </div>
      <Button variant="outline" onClick={() => update.mutate()} disabled={update.isPending}>Save changes</Button>
    </div> : <pre className="payload-preview" dir="auto">{JSON.stringify(proposal.payload, null, 2)}</pre>}
    {allowExecute && state === 'approved' && <Button onClick={() => execute.mutate()} disabled={execute.isPending}>{execute.isPending ? 'Sending through gateway…' : 'Execute approved action'}</Button>}
  </article>
}

function CaseActions({ session, caseItem }: { session: Session; caseItem: CaseItem }) {
  const client = useQueryClient()
  const candidates = useQuery({
    queryKey: ['shortlisted-candidates', caseItem.id],
    queryFn: () => api<CandidatePage>(`/candidates?case_id=${caseItem.id}&shortlisted=true&limit=100`, session.token),
  })
  const proposals = useQuery({
    queryKey: ['case-proposals', caseItem.id],
    queryFn: () => api<Proposal[]>(`/cases/${caseItem.id}/proposals`, session.token),
  })
  const [candidateId, setCandidateId] = useState('')
  const [start, setStart] = useState('')
  useEffect(() => { if (!candidateId && candidates.data?.items[0]) setCandidateId(candidates.data.items[0].id) }, [candidateId, candidates.data])
  const create = useMutation({
    mutationFn: () => api<Proposal>(`/cases/${caseItem.id}/proposals`, session.token,
      { method: 'POST', body: JSON.stringify({ candidate_id: candidateId, kind: 'interview_invite', start: start ? new Date(start).toISOString() : null, duration_minutes: 20 }) }),
    onSuccess: async () => { toast.success('Draft created. It is not sent until approved and executed through the gateway.'); setStart(''); await client.invalidateQueries({ queryKey: ['case-proposals', caseItem.id] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Proposal could not be drafted.'),
  })
  return <section className="workspace-section"><div className="panel-heading"><div><h2>Actions</h2><p>Draft, edit, and track approval without bypassing the Action Gateway.</p></div></div>
    {caseItem.can_edit && <div className="surface workspace-form"><h3>Draft an interview invite</h3>
      {candidates.data?.items.length ? <div className="stack-form">
        <label>Shortlisted candidate<select value={candidateId} onChange={event => setCandidateId(event.target.value)}>{candidates.data.items.map(candidate => <option key={candidate.id} value={candidate.id}>{candidate.pseudonym}</option>)}</select></label>
        <label>Completion deadline<input type="datetime-local" value={start} min={new Date().toISOString().slice(0, 16)} onChange={event => setStart(event.target.value)}/></label>
        <Button onClick={() => create.mutate()} disabled={!candidateId || create.isPending}>Create draft</Button>
      </div> : <NoRows title="No confirmed shortlist" text="Confirm shortlist membership before drafting candidate actions."/>}
    </div>}
    {proposals.isPending ? <LoadingRows/> : proposals.isError ? <QueryError message={proposals.error.message} retry={() => void proposals.refetch()}/> :
      proposals.data.length ? <div className="proposal-list">{proposals.data.map(proposal => <ProposalCard key={proposal.id} proposal={proposal} session={session} allowEdit={caseItem.can_edit && proposal.status !== 'EXECUTED'} allowExecute={caseItem.can_edit}/>)}</div> :
      <NoRows title="No actions drafted" text="Drafts appear here with their live approval state and payload hash."/>}
  </section>
}

function OutboxView({ session, caseId }: { session: Session; caseId: string }) {
  const outbox = useQuery({
    queryKey: ['workspace-outbox', session.user.id, caseId],
    queryFn: () => api<{ items: { id: string; case_title: string; pseudonym: string; kind: string; payload_sha256: string; delivery_status: string; created_at: string }[]; total: number }>(`/workspace/outbox?case_id=${caseId}&limit=100`, session.token),
  })
  return <section className="surface workspace-section"><h2>Outbox</h2><p>Approved actions and their delivery state. Recipient details are not shown in this view.</p>
    {outbox.isPending ? <LoadingRows/> : outbox.isError ? <QueryError message={outbox.error.message} retry={() => void outbox.refetch()}/> :
      outbox.data.items.length ? <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Action</TableHead><TableHead>Candidate</TableHead><TableHead>Delivery</TableHead><TableHead>Payload hash</TableHead><TableHead>Created</TableHead></TableRow></TableHeader>
        <TableBody>{outbox.data.items.map(item => <TableRow key={item.id}><TableCell>{humanize(item.kind)}</TableCell><TableCell dir="auto">{item.pseudonym}</TableCell><TableCell><Badge variant="outline">{humanize(item.delivery_status)}</Badge></TableCell><TableCell><code>{item.payload_sha256.slice(0, 18)}…</code></TableCell><TableCell>{new Date(item.created_at).toLocaleString()}</TableCell></TableRow>)}</TableBody></Table></div> :
      <NoRows title="Outbox is empty" text="Actions appear after manager approval and gateway execution."/>}
  </section>
}

export function CaseWorkspace({ session }: Props) {
  const { caseId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') ?? 'scorecard'
  const caseQuery = useQuery({
    queryKey: ['workspace-case', caseId],
    queryFn: () => api<CaseItem>(`/cases/${caseId}`, session.token),
    enabled: !!caseId,
  })
  const analytics = useQuery({
    queryKey: ['case-analytics', session.user.id, caseId],
    queryFn: () => api<{
      funnel: { stage: string; count: number }[]
      time_to_shortlist_seconds: number | null
      findings_by_type: { type: string; count: number }[]
    }>(`/cases/${caseId}/analytics`, session.token),
    enabled: !!caseId,
  })
  const validTabs = ['scorecard', 'candidates', 'evidence', 'ranking', 'compare', 'actions', 'outbox']
  const setTab = (tab: string) => setSearchParams(current => { const next = new URLSearchParams(current); next.set('tab', tab); return next }, { replace: true })
  if (caseQuery.isPending) return <LoadingRows/>
  if (caseQuery.isError) return <QueryError message={caseQuery.error.message} retry={() => void caseQuery.refetch()}/>
  const item = caseQuery.data
  return <section>
    <PageTitle title={item.title} description={item.description || 'Review criteria, evidence, and human decisions.'}
      actions={<Link className="text-link" to="/cases">All cases<ChevronRight size={16}/></Link>}/>
    <div className="case-meta"><Badge variant="outline">{item.criteria_confirmed ? 'Criteria confirmed' : 'Criteria need review'}</Badge><span>{item.members.length} case members</span></div>
    <section className="surface workspace-section case-analytics" aria-label="Case analytics">
      <div className="panel-heading"><div><h2>Case analytics</h2><p>Workflow counts and review signals for this case.</p></div></div>
      {analytics.isPending ? <LoadingRows count={2}/> : analytics.isError ? <QueryError message={analytics.error.message} retry={() => void analytics.refetch()}/> :
        <div className="analytics-grid">
          <div><h3>Funnel</h3>{analytics.data.funnel.map(stage => <div className="funnel-stage" key={stage.stage}><span>{stage.stage}</span><strong>{stage.count}</strong></div>)}</div>
          <div><h3>Time to shortlist</h3><p>{analytics.data.time_to_shortlist_seconds === null ? 'Not shortlisted yet' : formatDuration(analytics.data.time_to_shortlist_seconds)}</p>
            <h3>Findings by type</h3>{analytics.data.findings_by_type.length ? analytics.data.findings_by_type.map(item => <div className="funnel-stage" key={item.type}><span>{humanize(item.type)}</span><strong>{item.count}</strong></div>) : <p>No evidence findings recorded.</p>}</div>
        </div>}
    </section>
    <Tabs value={validTabs.includes(activeTab) ? activeTab : 'scorecard'} onValueChange={setTab} className="case-tabs">
      <TabsList aria-label="Case sections">{validTabs.map(tab => <TabsTrigger key={tab} value={tab}>{humanize(tab)}</TabsTrigger>)}</TabsList>
      <TabsContent value="scorecard"><Scorecard session={session} caseItem={item}/></TabsContent>
      <TabsContent value="candidates"><Candidates session={session} caseItem={item}/></TabsContent>
      <TabsContent value="evidence"><Evidence session={session} caseItem={item}/></TabsContent>
      <TabsContent value="ranking"><RankingView session={session} caseItem={item}/></TabsContent>
      <TabsContent value="compare"><CompareView session={session} caseItem={item}/></TabsContent>
      <TabsContent value="actions"><CaseActions session={session} caseItem={item}/></TabsContent>
      <TabsContent value="outbox"><OutboxView session={session} caseId={item.id}/></TabsContent>
    </Tabs>
  </section>
}

function formatDuration(seconds: number) {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return [days && `${days}d`, hours && `${hours}h`, minutes && `${minutes}m`].filter(Boolean).join(' ') || 'Less than a minute'
}

export function ApprovalsPage({ session }: Props) {
  const client = useQueryClient()
  const cases = useCases(session)
  const inbox = useQuery({
    queryKey: ['approval-inbox', session.user.id],
    queryFn: async () => {
      const accessible = await api<CaseItem[]>('/cases?limit=100', session.token)
      const all = await Promise.all(accessible.map(item => api<Proposal[]>(`/cases/${item.id}/proposals`, session.token)))
      return all.flat().map(proposal => ({ ...proposal, case_title: accessible.find(item => item.id === proposal.case_id)?.title ?? proposal.case_id }))
    },
    enabled: !!cases.data,
  })
  const decision = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' }) =>
      api<Proposal>(`/proposals/${id}/${action}`, session.token, { method: 'POST', body: JSON.stringify({}) }),
    onSuccess: async (_, variables) => { toast.success(variables.action === 'approve' ? 'The exact current payload was approved.' : 'Proposal rejected.'); await client.invalidateQueries({ queryKey: ['approval-inbox'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Decision could not be recorded.'),
  })
  if (cases.isPending || inbox.isPending) return <LoadingRows/>
  if (cases.isError) return <QueryError message={cases.error.message} retry={() => void cases.refetch()}/>
  if (inbox.isError) return <QueryError message={inbox.error.message} retry={() => void inbox.refetch()}/>
  const proposals = inbox.data ?? []
  return <section><PageTitle title="Approvals" description="Review the exact payload and SHA-256 digest before deciding."/>
    {proposals.length ? <div className="proposal-list">{proposals.map(proposal => <article className="proposal-card" key={proposal.id}>
      <div className="panel-heading"><div><h2>{humanize(proposal.kind)}</h2><p>{proposal.case_title} · {proposal.id}</p></div><Badge variant="outline">{humanize(proposalState(proposal))}</Badge></div>
      <p className="honest-note">Nobody is rejected automatically. This approval only authorizes the displayed payload.</p>
      <div className="hash-block"><span>Current payload SHA-256</span><code>{proposal.payload_sha256}</code></div>
      {proposal.approval && <div className="hash-block"><span>Previously approved SHA-256</span><code>{proposal.approval.approved_hash}</code></div>}
      {proposal.approval && !proposal.approval.matches_current_payload && <div className="warning-box" role="alert"><AlertTriangle size={18}/><span>Payload changed. Execution will be refused; review and approve the current exact content again.</span></div>}
      <pre className="payload-preview" dir="auto">{JSON.stringify(proposal.payload, null, 2)}</pre>
      {session.user.role === 'hiring_manager' && proposal.status !== 'EXECUTED' &&
        (!proposal.approval || proposal.approval.decision !== 'approved' || !proposal.approval.matches_current_payload || !!proposal.approval.used_at || Date.parse(proposal.approval.expires_at) <= Date.now()) &&
        <div className="page-actions"><Button onClick={() => decision.mutate({ id: proposal.id, action: 'approve' })} disabled={decision.isPending}><Check size={16}/>Approve this exact payload</Button><Button variant="outline" onClick={() => decision.mutate({ id: proposal.id, action: 'reject' })} disabled={decision.isPending}>Reject</Button></div>}
    </article>)}</div> : <NoRows title="No approvals to review" text="Pending actions scoped to your cases will appear here."/>}
  </section>
}

export function LedgerPage({ session }: Props) {
  const [caseId, setCaseId] = useState('')
  const [filter, setFilter] = useState('')
  const [verification, setVerification] = useState<{ ok: boolean; events: number; first_bad_seq?: number } | null>(null)
  const cases = useCases(session)
  const query = caseId ? `?case_id=${encodeURIComponent(caseId)}&limit=100` : '?limit=100'
  const ledger = useQuery({
    queryKey: ['audit-ledger', session.user.id, caseId],
    queryFn: () => api<{ events: AuditEvent[]; total: number; head_hash: string; complete_chain_visible: boolean }>(`/audit/ledger${query}`, session.token),
  })
  async function verify() {
    try { const result = await api<{ ok: boolean; events: number; first_bad_seq?: number }>('/ledger/verify', session.token); setVerification(result); if (result.ok) toast.success(`Chain intact · ${result.events} events`); else toast.error(`Chain failure at sequence ${result.first_bad_seq}`) }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Ledger verification failed.') }
  }
  async function exportAudit() {
    try {
      const result = await api<Record<string, unknown>>('/audit/export', session.token)
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = 'vouch-audit-export.json'; anchor.click(); URL.revokeObjectURL(url)
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Export failed.') }
  }
  const events = useMemo(() => (ledger.data?.events ?? []).filter(event => !filter || `${event.type} ${event.actor} ${event.subject ?? ''}`.toLowerCase().includes(filter.toLowerCase())), [ledger.data, filter])
  const canVerify = session.user.role === 'auditor' || session.user.role === 'hr_admin'
  return <section><PageTitle title="Trust ledger" description="Append-only events linked by hashes and authenticated by the ledger MAC."
    actions={<><Button variant="outline" onClick={() => void ledger.refetch()}><RefreshCw size={16}/>Refresh</Button><Button variant="outline" onClick={() => void exportAudit()}><Download size={16}/>Signed export</Button>{canVerify && <Button onClick={() => void verify()}><ShieldCheck size={16}/>Verify chain</Button>}</>}/>
    <div className="table-controls"><label>Case scope<select value={caseId} onChange={event => setCaseId(event.target.value)}><option value="">All accessible cases</option>{cases.data?.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><Input value={filter} onChange={event => setFilter(event.target.value)} placeholder="Filter events" aria-label="Filter ledger events"/></div>
    {verification && <div className={verification.ok ? 'success-box' : 'warning-box'} role="status">{verification.ok ? 'Chain verified' : 'Verification failed'} · {verification.events} events{verification.first_bad_seq ? ` · first issue at ${verification.first_bad_seq}` : ''}</div>}
    {ledger.isPending ? <LoadingRows/> : ledger.isError ? <QueryError message={ledger.error.message} retry={() => void ledger.refetch()}/> :
      <><div className="ledger-head"><span>Ledger head</span><code>{ledger.data.head_hash}</code><Badge variant="outline">{ledger.data.complete_chain_visible ? 'Full chain visible' : 'Scoped events'}</Badge></div>
        {events.length ? <div className="ledger-list">{events.map(event => <article className="ledger-event" key={event.seq}>
          <div className="ledger-seq"><strong>#{event.seq}</strong><time>{new Date(event.ts).toLocaleString()}</time></div><div><h3>{humanize(event.type)}</h3><p>{event.case_id ?? 'Global'} · {event.actor}</p></div>
          <div className="chain-link"><code>{event.prev_hash.slice(0, 14)}…</code><span>→</span><code>{event.hash.slice(0, 14)}…</code></div>
          <details><summary>Event body and MAC</summary><pre>{JSON.stringify({ body: event.body, mac: event.mac }, null, 2)}</pre></details>
        </article>)}</div> : <NoRows title="No events match" text="Try clearing the event filter or selecting another case."/>}
      </>}
  </section>
}

type SentinelResult = { id: string; name: string; severity: string; outcome: string; detection?: boolean | null; assertions: { check: string; ok: boolean; evidence?: unknown }[] }
type SentinelReport = { available?: boolean; generated_at?: string; target?: { model_mode?: string }; totals?: { scenarios: number; pass: number; fail: number; blocked: number; error: number }; results?: SentinelResult[] }

export function AssurancePage({ session }: Props) {
  const client = useQueryClient()
  const [caseId, setCaseId] = useState('')
  const [redTeam, setRedTeam] = useState<{ name: string; findings: string[]; status: string } | null>(null)
  const cases = useCases(session)
  const report = useQuery({
    queryKey: ['sentinel-report'],
    queryFn: () => api<SentinelReport>('/assurance/latest', session.token),
    refetchInterval: 3000,
  })
  const runner = useQuery({
    queryKey: ['sentinel-status'],
    queryFn: () => api<{ running: boolean }>('/assurance/status', session.token),
    refetchInterval: 1000,
  })
  const run = useMutation({
    mutationFn: () => api<{ started: boolean; running: boolean }>('/assurance/run', session.token, { method: 'POST', body: '{}' }),
    onSuccess: async () => { toast.success('SENTINEL is running against an isolated test instance.'); await client.invalidateQueries({ queryKey: ['sentinel-report'] }); await client.invalidateQueries({ queryKey: ['sentinel-status'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'SENTINEL could not be started.'),
  })
  const canRun = session.user.role === 'auditor' || session.user.role === 'hr_admin'
  async function uploadAttack(file: File) {
    if (!caseId) { toast.error('Select a case first.'); return }
    const form = new FormData(); form.append('file', file)
    try {
      const dossier = await api<Dossier>(`/cases/${caseId}/candidates`, session.token, { method: 'POST', body: form })
      setRedTeam({ name: file.name, findings: dossier.findings.map(finding => finding.type), status: dossier.document ? 'Analyzed' : 'Uploaded' })
      await client.invalidateQueries({ queryKey: ['workspace-candidates'] })
      toast.success('CV analyzed. Review the detector findings below.')
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Red-team upload failed.') }
  }
  return <section><PageTitle title="Assurance" description="Scenario results are evidence about these tests, not a guarantee of production safety."
    actions={canRun ? <Button onClick={() => run.mutate()} disabled={run.isPending || runner.data?.running}><ShieldCheck size={16}/>{runner.data?.running ? 'SENTINEL running…' : 'Run SENTINEL'}</Button> : undefined}/>
    {runner.isError && <QueryError message={runner.error.message} retry={() => void runner.refetch()}/>}
    {runner.data?.running && <div className="warning-box" role="status"><RefreshCw size={17}/>SENTINEL is running against an isolated test instance. Results will refresh automatically.</div>}
    {report.isPending ? <LoadingRows/> : report.isError ? <QueryError message={report.error.message} retry={() => void report.refetch()}/> :
      report.data.available && report.data.totals ? <div className="assurance-summary surface"><div><strong>{report.data.totals.pass}/{report.data.totals.scenarios}</strong><span>scenarios passed</span></div>
        <div><Badge variant="outline" className={report.data.totals.fail ? 'danger' : 'success'}>{report.data.totals.fail} fail · {report.data.totals.blocked} blocked · {report.data.totals.error} error</Badge>
          <p>Model mode: {report.data.target?.model_mode ?? 'unavailable'} · Last run: {report.data.generated_at ? new Date(report.data.generated_at).toLocaleString() : 'unknown'}</p></div>
      </div> : <NoRows title="No SENTINEL report yet" text="Run the assurance scenarios to create a report."/>}
    {report.data?.results && <section className="surface workspace-section"><h2>Scenario outcomes</h2><div className="scenario-list">{report.data.results.map(item => {
      const outcome = item.outcome === 'ERROR' ? 'UNOBSERVABLE' : item.outcome
      return <details className="scenario-row" key={item.id}>
      <summary><Badge variant="outline" className={`scenario-outcome ${outcome.toLowerCase()}`}>{outcome}</Badge><span>{item.id}</span><strong>{item.name}</strong><span>{item.severity}</span></summary>
      {item.assertions.map((assertion, index) => <p className={assertion.ok ? 'success' : 'danger'} key={`${assertion.check}-${index}`}>{assertion.ok ? 'PASS' : 'FAIL'} · {assertion.check}</p>)}
    </details>})}</div></section>}
    <section className="surface workspace-section red-team-panel"><div className="panel-heading"><div><h2>Red-team CV check</h2><p>Upload a synthetic attack CV to an accessible case and inspect which detector findings fire.</p></div><ShieldCheck size={22}/></div>
      {session.user.role === 'recruiter' ? <div className="stack-form"><label>Case<select value={caseId} onChange={event => setCaseId(event.target.value)}><option value="">Select a case</option>{cases.data?.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
        <label>Attack CV (PDF)<Input type="file" accept="application/pdf,.pdf" onChange={event => { const file = event.target.files?.[0]; if (file) void uploadAttack(file); event.target.value = '' }}/></label>
      </div> : <p>CV uploads require recruiter write access. Ask a recruiter to run the upload in a case; the SENTINEL runner itself uses an isolated database.</p>}
      {redTeam && <div className="success-box"><strong dir="auto">{redTeam.name}</strong><span>{redTeam.status}</span><span>Defences fired: {redTeam.findings.length ? redTeam.findings.map(humanize).join(', ') : 'No findings reported'}</span></div>}
    </section>
  </section>
}

type AdminUser = { id: string; email: string; name: string; role: string }
type Policy = { approval_ttl_minutes: number; review_weight_threshold: number }
const userSchema = z.object({ email: z.string().email(), name: z.string().trim().min(1).max(120), role: z.enum(['recruiter', 'hiring_manager', 'auditor', 'hr_admin']), password: z.string().min(12).max(200) })
const policySchema = z.object({ approval_ttl_minutes: z.coerce.number().int().min(1).max(1440), review_weight_threshold: z.coerce.number().int().min(0).max(100) })
type PolicyInput = z.input<typeof policySchema>
type PolicyOutput = z.output<typeof policySchema>

export function AdminPage({ session }: Props) {
  const client = useQueryClient()
  const users = useQuery({ queryKey: ['admin-users'], queryFn: () => api<AdminUser[]>('/admin/users', session.token), enabled: session.user.role === 'hr_admin' })
  const policy = useQuery({ queryKey: ['admin-policy'], queryFn: () => api<Policy>('/admin/policy', session.token), enabled: session.user.role === 'hr_admin' })
  const meta = useQuery({ queryKey: ['meta'], queryFn: () => api<{ data_handling: { retention_days: number; statement: string } }>('/meta') })
  const userForm = useForm<z.infer<typeof userSchema>>({ resolver: zodResolver(userSchema), defaultValues: { email: '', name: '', role: 'recruiter', password: '' } })
  const policyForm = useForm<PolicyInput, unknown, PolicyOutput>({ resolver: zodResolver(policySchema), defaultValues: { approval_ttl_minutes: 15, review_weight_threshold: 30 } })
  useEffect(() => { if (policy.data) policyForm.reset(policy.data) }, [policy.data, policyForm])
  const createUser = useMutation({
    mutationFn: (value: z.infer<typeof userSchema>) => api<AdminUser>('/admin/users', session.token, { method: 'POST', body: JSON.stringify(value) }),
    onSuccess: async () => { toast.success('User created.'); userForm.reset(); await client.invalidateQueries({ queryKey: ['admin-users'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'User could not be created.'),
  })
  const updateRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) => api<AdminUser>(`/admin/users/${id}/role`, session.token, { method: 'PATCH', body: JSON.stringify({ role }) }),
    onSuccess: async () => { toast.success('Role updated.'); await client.invalidateQueries({ queryKey: ['admin-users'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Role could not be updated.'),
  })
  const updatePolicy = useMutation({
    mutationFn: (value: PolicyOutput) => api<Policy>('/admin/policy', session.token, { method: 'PUT', body: JSON.stringify(value) }),
    onSuccess: async () => { toast.success('Policy saved.'); await client.invalidateQueries({ queryKey: ['admin-policy'] }); await client.invalidateQueries({ queryKey: ['meta'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Policy could not be saved.'),
  })
  if (session.user.role !== 'hr_admin') return <QueryError message="Only HR administrators can manage users and policy."/>
  return <section><PageTitle title="Settings" description="Manage access, approval windows, ranking thresholds, and data handling."/>
    <div className="admin-grid">
      <section className="surface workspace-section"><h2>Users and roles</h2>
        {users.isPending ? <LoadingRows/> : users.isError ? <QueryError message={users.error.message} retry={() => void users.refetch()}/> :
          <div className="table-scroll"><Table><TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Email</TableHead><TableHead>Role</TableHead></TableRow></TableHeader><TableBody>{users.data.map(user =>
            <TableRow key={user.id}><TableCell>{user.name}</TableCell><TableCell>{user.email}</TableCell><TableCell><select aria-label={`Role for ${user.name}`} value={user.role} onChange={event => updateRole.mutate({ id: user.id, role: event.target.value })}>{['recruiter', 'hiring_manager', 'auditor', 'hr_admin'].map(role => <option key={role} value={role}>{humanize(role)}</option>)}</select></TableCell></TableRow>)}</TableBody></Table></div>}
        <Separator/>
        <form className="stack-form" onSubmit={userForm.handleSubmit(value => createUser.mutate(value))}>
          <h3>Create user</h3><label>Name<Input {...userForm.register('name')}/></label><label>Email<Input type="email" {...userForm.register('email')}/></label>
          <label>Role<select {...userForm.register('role')}>{['recruiter', 'hiring_manager', 'auditor', 'hr_admin'].map(role => <option key={role} value={role}>{humanize(role)}</option>)}</select></label>
          <label>Temporary password<Input type="password" autoComplete="new-password" {...userForm.register('password')}/></label>
          {userForm.formState.errors.password && <p className="danger">Password must be at least 12 characters.</p>}
          <Button type="submit" disabled={createUser.isPending}>Create user</Button>
        </form>
      </section>
      <section className="surface workspace-section"><h2>Policy</h2><p>Changes apply to new approvals and rankings.</p>
        {policy.isError && <QueryError message={policy.error.message} retry={() => void policy.refetch()}/>}
        <form className="stack-form" onSubmit={policyForm.handleSubmit(value => updatePolicy.mutate(value))}>
          <label>Approval TTL (minutes)<Input type="number" min="1" max="1440" {...policyForm.register('approval_ttl_minutes', { valueAsNumber: true })}/></label>
          <label>Review-weight threshold (%)<Input type="number" min="0" max="100" {...policyForm.register('review_weight_threshold', { valueAsNumber: true })}/></label>
          <p>Criteria with needs-review weight above the threshold receive a review flag. Nothing is rejected automatically.</p>
          <Button type="submit" disabled={!policyForm.formState.isValid || updatePolicy.isPending}>Save policy</Button>
        </form>
        <Separator/><h2>Retention and data handling</h2>
        {meta.isPending ? <Skeleton className="h-14"/> : meta.isError ? <QueryError message={meta.error.message}/> :
          <div className="data-handling"><p>Automatic retention purge: <strong>{meta.data.data_handling.retention_days} days</strong>.</p><p>{meta.data.data_handling.statement}</p><p>Candidate erasure removes source files and analysis while retaining ledger events.</p></div>}
      </section>
    </div>
  </section>
}

function localDateTimeValue(value: Date) {
  const offset = value.getTimezoneOffset() * 60_000
  return new Date(value.getTime() - offset).toISOString().slice(0, 16)
}

function InterviewCard({ interview, caseTitle, candidateLabel, interviewerLabel, session, onUpdate }: {
  interview: Interview; caseTitle: string; candidateLabel: string; interviewerLabel: string; session: Session
  onUpdate: (id: string, values: Record<string, unknown>) => void
}) {
  const canReview = session.user.role === 'hiring_manager' && interview.interviewer_id === session.user.id
  const canManage = session.user.role === 'recruiter'
  return <article className="schedule-card">
    <div className="schedule-card-heading"><div><span className="schedule-time">{new Date(interview.scheduled_start).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}</span>
      <h2 dir="auto">{candidateLabel}</h2><p>{caseTitle} · {humanize(interview.interview_type)} · {interview.duration_minutes} min</p></div>
      <Badge variant="outline">{humanize(interview.status)}</Badge></div>
    <div className="schedule-details"><span><Users size={15}/>{interviewerLabel}</span><span><Clock3 size={15}/>{interview.timezone}</span>
      {interview.location && <span>{interview.location}</span>}</div>
    {interview.preparation_notes && <p className="schedule-note" dir="auto">{interview.preparation_notes}</p>}
    {interview.feedback && <div className="schedule-feedback"><strong>Feedback</strong><p dir="auto">{interview.feedback}</p></div>}
    {(canManage || canReview) && interview.status !== 'completed' && interview.status !== 'cancelled' &&
      <div className="schedule-actions">
        {canManage && interview.status === 'scheduled' && <Button variant="outline" onClick={() => onUpdate(interview.id, { status: 'confirmed' })}>Confirm</Button>}
        {canReview && <form className="inline-feedback" onSubmit={event => {
          event.preventDefault()
          const form = new FormData(event.currentTarget)
          onUpdate(interview.id, { status: 'completed', feedback: String(form.get('feedback') ?? '') })
        }}><label>Interview feedback<Textarea name="feedback" maxLength={4000} defaultValue={interview.feedback}/></label>
          <Button type="submit">Complete interview</Button></form>}
        {canManage && <Button variant="outline" onClick={() => onUpdate(interview.id, { status: 'cancelled' })}>Cancel interview</Button>}
      </div>}
  </article>
}

export function InterviewsPage({ session }: Props) {
  const client = useQueryClient()
  const cases = useCases(session)
  const [caseId, setCaseId] = useState('')
  const [interviewType, setInterviewType] = useState('screening')
  const [candidateId, setCandidateId] = useState('')
  const [interviewerId, setInterviewerId] = useState('')
  const [scheduledStart, setScheduledStart] = useState(() => localDateTimeValue(new Date(Date.now() + 86_400_000)))
  const [duration, setDuration] = useState('45')
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC')
  const [location, setLocation] = useState('')
  const [preparationNotes, setPreparationNotes] = useState('')
  useEffect(() => {
    if (!caseId && cases.data?.length) setCaseId(cases.data[0].id)
  }, [caseId, cases.data])
  const selectedCase = cases.data?.find(item => item.id === caseId)
  const candidates = useCandidates(session, caseId, '', 100, { shortlisted: 'true' })
  const interviews = useQuery({
    queryKey: ['interviews', session.user.id],
    queryFn: () => api<{ items: Interview[]; total: number }>('/interviews?limit=100', session.token),
    enabled: cases.isSuccess,
  })
  const create = useMutation({
    mutationFn: () => api<Interview>('/interviews', session.token, { method: 'POST', body: JSON.stringify({
      case_id: caseId, candidate_id: candidateId, interviewer_id: interviewerId, interview_type: interviewType,
      scheduled_start: new Date(scheduledStart).toISOString(), duration_minutes: Number(duration), timezone,
      location, preparation_notes: preparationNotes,
    }) }),
    onSuccess: async () => {
      toast.success('Interview scheduled. No message was sent.')
      setPreparationNotes('')
      await client.invalidateQueries({ queryKey: ['interviews'] })
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'Interview could not be scheduled.'),
  })
  const update = useMutation({
    mutationFn: ({ id, values }: { id: string; values: Record<string, unknown> }) =>
      api<Interview>(`/interviews/${id}`, session.token, { method: 'PATCH', body: JSON.stringify(values) }),
    onSuccess: async () => { toast.success('Interview updated.'); await client.invalidateQueries({ queryKey: ['interviews'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Interview could not be updated.'),
  })
  useEffect(() => {
    if (selectedCase?.members.length) {
      const current = selectedCase.members.find(member => member.id === session.user.id)
      const interviewer = current?.role === 'hiring_manager' ? current : selectedCase.members.find(member => member.role === 'hiring_manager')
      if (interviewer && !interviewerId) setInterviewerId(interviewer.id)
    }
  }, [selectedCase, interviewerId, session.user.id])
  useEffect(() => {
    if (candidates.data && !candidates.data.items.some(candidate => candidate.id === candidateId)) {
      setCandidateId(candidates.data.items[0]?.id ?? '')
    }
  }, [candidates.data, candidateId])
  if (cases.isPending || interviews.isPending) return <LoadingRows/>
  if (cases.isError) return <QueryError message={cases.error.message} retry={() => void cases.refetch()}/>
  if (interviews.isError) return <QueryError message={interviews.error.message} retry={() => void interviews.refetch()}/>
  const caseNames = new Map((cases.data ?? []).map(item => [item.id, item.title]))
  const interviewRows = interviews.data.items
  const candidateNames = new Map<string, string>()
  for (const candidate of candidates.data?.items ?? []) candidateNames.set(candidate.id, candidate.pseudonym)
  const memberNames = new Map((selectedCase?.members ?? []).map(member => [member.id, member.name]))
  const canSchedule = session.user.role === 'recruiter'
  return <section>
    <PageTitle title="Interview calendar" description="Schedule shortlisted candidates and keep interview details and feedback in one persistent, case-scoped view."
      actions={<Badge variant="outline">{interviews.data.total} interviews</Badge>}/>
    {canSchedule && <section className="surface workspace-section">
      <div className="panel-heading"><div><h2>Schedule an interview</h2><p>Scheduling records do not send invitations. Approved communication remains in the Action Gateway.</p></div><CalendarDays size={22}/></div>
      <form className="schedule-form" onSubmit={event => { event.preventDefault(); create.mutate() }}>
        <label>Case<select required value={caseId} onChange={event => { setCaseId(event.target.value); setCandidateId(''); setInterviewerId('') }}>
          <option value="">Select a case</option>{cases.data.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
        <label>Shortlisted candidate<select required value={candidateId} onChange={event => setCandidateId(event.target.value)} disabled={!caseId || candidates.isPending}>
          <option value="">Select a confirmed shortlisted candidate</option>{candidates.data?.items.map(item => <option value={item.id} key={item.id}>{item.pseudonym}</option>)}</select></label>
        <label>Interviewer<select required value={interviewerId} onChange={event => setInterviewerId(event.target.value)} disabled={!selectedCase}>
          <option value="">Select an interviewer</option>{selectedCase?.members.map(member => <option value={member.id} key={member.id}>{member.name} · {humanize(member.role)}</option>)}</select></label>
        <label>Interview type<select value={interviewType} onChange={event => setInterviewType(event.target.value)}>
          {['screening', 'technical', 'behavioral', 'final', 'other'].map(value => <option value={value} key={value}>{humanize(value)}</option>)}</select></label>
        <label>Start time<Input type="datetime-local" required value={scheduledStart} onChange={event => setScheduledStart(event.target.value)}/></label>
        <label>Duration (minutes)<Input type="number" min="15" max="240" step="15" required value={duration} onChange={event => setDuration(event.target.value)}/></label>
        <label>Time zone<Input required value={timezone} maxLength={64} onChange={event => setTimezone(event.target.value)}/></label>
        <label>Location or meeting link<Input value={location} maxLength={300} onChange={event => setLocation(event.target.value)}/></label>
        <label className="schedule-wide">Preparation notes<Textarea maxLength={4000} value={preparationNotes} onChange={event => setPreparationNotes(event.target.value)}/></label>
        <div className="schedule-wide"><Button type="submit" disabled={create.isPending || !candidateId || !interviewerId}>{create.isPending ? 'Scheduling…' : 'Schedule interview'}</Button></div>
      </form>
      {candidates.isError && <QueryError message={candidates.error.message} retry={() => void candidates.refetch()}/>}
      {selectedCase && !candidates.isPending && !candidates.isError && !candidates.data?.items.length &&
        <div className="warning-box"><AlertTriangle size={18}/><span>Confirm a ranking and shortlist candidates before scheduling.</span></div>}
    </section>}
    {!canSchedule && <div className="honest-note">Interview scheduling requires recruiter access. Assigned interviewers can record feedback here.</div>}
    {interviewRows.length ? <div className="schedule-list">{interviewRows.map(interview =>
      <InterviewCard key={interview.id} interview={interview} caseTitle={interview.case_title ?? caseNames.get(interview.case_id) ?? interview.case_id}
        candidateLabel={interview.candidate_pseudonym ?? candidateNames.get(interview.candidate_id) ?? interview.candidate_id}
        interviewerLabel={interview.interviewer_name ?? memberNames.get(interview.interviewer_id) ?? interview.interviewer_id} session={session}
        onUpdate={(id, values) => update.mutate({ id, values })}/>)}</div> :
      <NoRows title="No interviews scheduled" text="Confirmed shortlisted candidates can be scheduled here. Scheduling alone never sends an invitation."/>}
  </section>
}

export function FollowUpsPage({ session }: Props) {
  const client = useQueryClient()
  const cases = useCases(session)
  const [caseId, setCaseId] = useState('')
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [candidateId, setCandidateId] = useState('')
  const [assignedTo, setAssignedTo] = useState('')
  const [taskType, setTaskType] = useState('follow_up')
  const [priority, setPriority] = useState('normal')
  const [dueAt, setDueAt] = useState('')
  useEffect(() => {
    if (!caseId && cases.data?.length) setCaseId(cases.data[0].id)
  }, [caseId, cases.data])
  const selectedCase = cases.data?.find(item => item.id === caseId)
  const candidates = useCandidates(session, caseId, '', 100)
  const tasks = useQuery({
    queryKey: ['follow-ups', session.user.id],
    queryFn: () => api<{ items: FollowUpTask[]; total: number }>('/follow-ups?limit=100', session.token),
    enabled: cases.isSuccess,
  })
  const create = useMutation({
    mutationFn: () => api<FollowUpTask>('/follow-ups', session.token, { method: 'POST', body: JSON.stringify({
      case_id: caseId, title, description, task_type: taskType, priority,
      ...(candidateId ? { candidate_id: candidateId } : {}),
      ...(assignedTo ? { assigned_to: assignedTo } : {}),
      ...(dueAt ? { due_at: new Date(dueAt).toISOString() } : {}),
    }) }),
    onSuccess: async () => {
      toast.success('Follow-up task saved.')
      setTitle(''); setDescription(''); setDueAt('')
      await client.invalidateQueries({ queryKey: ['follow-ups'] })
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'Task could not be saved.'),
  })
  const update = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api<FollowUpTask>(`/follow-ups/${id}`, session.token, { method: 'PATCH', body: JSON.stringify({ status }) }),
    onSuccess: async () => { toast.success('Task status saved.'); await client.invalidateQueries({ queryKey: ['follow-ups'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Task could not be updated.'),
  })
  useEffect(() => {
    if (selectedCase?.members.length) {
      setAssignedTo(value => selectedCase.members.some(member => member.id === value) ? value : '')
    }
  }, [selectedCase])
  useEffect(() => {
    if (candidates.data && candidateId && !candidates.data.items.some(candidate => candidate.id === candidateId)) setCandidateId('')
  }, [candidates.data, candidateId])
  if (cases.isPending || tasks.isPending) return <LoadingRows/>
  if (cases.isError) return <QueryError message={cases.error.message} retry={() => void cases.refetch()}/>
  if (tasks.isError) return <QueryError message={tasks.error.message} retry={() => void tasks.refetch()}/>
  const caseNames = new Map((cases.data ?? []).map(item => [item.id, item.title]))
  const memberNames = new Map((cases.data ?? []).flatMap(item => item.members.map(member => [member.id, member.name] as const)))
  const candidateNames = new Map((candidates.data?.items ?? []).map(candidate => [candidate.id, candidate.pseudonym]))
  const recruiter = session.user.role === 'recruiter'
  return <section>
    <PageTitle title="Follow-up queue" description="Persistent, case-scoped reminders for review, interviews, feedback, and approved communication."
      actions={<Badge variant="outline">{tasks.data.total} tasks</Badge>}/>
    {recruiter && <section className="surface workspace-section">
      <div className="panel-heading"><div><h2>Create a follow-up</h2><p>Tasks are reminders only. Completing one does not send a message or approve an action.</p></div><ListTodo size={22}/></div>
      <form className="schedule-form" onSubmit={event => { event.preventDefault(); create.mutate() }}>
        <label>Case<select required value={caseId} onChange={event => { setCaseId(event.target.value); setCandidateId(''); setAssignedTo('') }}>
          <option value="">Select a case</option>{cases.data.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
        <label>Task title<Input required maxLength={200} value={title} onChange={event => setTitle(event.target.value)}/></label>
        <label>Task type<select value={taskType} onChange={event => setTaskType(event.target.value)}>
          {['review_cv', 'review_assessment', 'approve_communication', 'send_approved_communication', 'schedule_interview', 'confirm_interview', 'collect_feedback', 'follow_up', 'other'].map(value => <option value={value} key={value}>{humanize(value)}</option>)}</select></label>
        <label>Candidate (optional)<select value={candidateId} onChange={event => setCandidateId(event.target.value)}>
          <option value="">No candidate link</option>{candidates.data?.items.map(item => <option value={item.id} key={item.id}>{item.pseudonym}</option>)}</select></label>
        <label>Assignee (optional)<select value={assignedTo} onChange={event => setAssignedTo(event.target.value)}>
          <option value="">Unassigned</option>{selectedCase?.members.map(member => <option value={member.id} key={member.id}>{member.name} · {humanize(member.role)}</option>)}</select></label>
        <label>Priority<select value={priority} onChange={event => setPriority(event.target.value)}>
          {['low', 'normal', 'high', 'urgent'].map(value => <option value={value} key={value}>{humanize(value)}</option>)}</select></label>
        <label>Due date and time<Input type="datetime-local" value={dueAt} onChange={event => setDueAt(event.target.value)}/></label>
        <label className="schedule-wide">Description<Textarea maxLength={4000} value={description} onChange={event => setDescription(event.target.value)}/></label>
        <div className="schedule-wide"><Button type="submit" disabled={create.isPending || !caseId || !title.trim()}>{create.isPending ? 'Saving…' : 'Create task'}</Button></div>
      </form>
      {candidates.isError && <QueryError message={candidates.error.message} retry={() => void candidates.refetch()}/>}
    </section>}
    {tasks.data.items.length ? <div className="schedule-list">{tasks.data.items.map(task => {
      const canUpdate = recruiter || (session.user.role === 'hiring_manager' && task.assigned_to === session.user.id)
      const nextStatus = task.status === 'open' ? 'in_progress' : 'completed'
      return <article className={`schedule-card task-card ${task.status === 'completed' ? 'is-completed' : ''}`} key={task.id}>
        <div className="schedule-card-heading"><div><span className="schedule-time">{task.due_at ? `Due ${new Date(task.due_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : 'No due date'}</span>
          <h2 dir="auto">{task.title}</h2><p>{task.case_title ?? caseNames.get(task.case_id) ?? task.case_id} · {humanize(task.task_type)}</p></div>
          <div className="schedule-badges"><Badge variant="outline">{humanize(task.status)}</Badge><Badge variant="outline">{humanize(task.priority)}</Badge></div></div>
        {task.description && <p className="schedule-note" dir="auto">{task.description}</p>}
        <div className="schedule-details">{task.candidate_id && <span><Users size={15}/>{task.candidate_pseudonym ?? candidateNames.get(task.candidate_id) ?? task.candidate_id}</span>}
          {task.assigned_to && <span>Assigned to {task.assignee_name ?? memberNames.get(task.assigned_to) ?? task.assigned_to}</span>}
          {task.origin !== 'manual' && <span>{humanize(task.origin)} task</span>}</div>
        {canUpdate && task.status !== 'completed' && <div className="schedule-actions">
          <Button variant={nextStatus === 'completed' ? 'default' : 'outline'} disabled={update.isPending}
            onClick={() => update.mutate({ id: task.id, status: nextStatus })}>{nextStatus === 'completed' ? 'Complete task' : 'Start task'}</Button>
        </div>}
        {task.status === 'completed' && task.completed_at && <p className="schedule-note">Completed {new Date(task.completed_at).toLocaleString()}</p>}
      </article>
    })}</div> : <NoRows title="No follow-up tasks" text="Create a task to keep case work and interview follow-through visible across refreshes."/>}
  </section>
}
