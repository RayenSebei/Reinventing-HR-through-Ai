import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { AlertTriangle, BookOpen, CalendarDays, Check, Clock3, Link2, Mail, Paperclip, RefreshCw, Reply, Send, ShieldCheck, Sparkles, Upload } from 'lucide-react'
import { api, humanize, type Session } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { LoadingRows, NoRows, PageTitle, QueryError } from './WorkspacePages'
import './assistants.css'

type Props = { session: Session }
type Finding = { type: string; severity: string; detail: string }
type LinkCheck = { url: string; host: string; verdict: string; reasons: string[] }
type InboxItem = {
  id: string; sender_name: string; sender_email: string; subject: string; received_at: string
  category: string; category_label: string; urgency: string; summary: string; findings: Finding[]; links: LinkCheck[]
  status: string; source: string; candidate: { id: string; pseudonym: string } | null; case: { id: string; title: string } | null
  reply_proposal_id: string | null; suggested_action: string; safe_text?: string
}
type Digest = {
  generated_at: string; groups: { category: string; label: string; count: number; urgent: number; items: InboxItem[] }[]
  totals: { messages: number; urgent: number; flagged: number; matched: number }; method: string
}
type ReplyProposal = { id: string; kind: string; status: string; payload: { subject?: string; body?: string }; sensitive_topic?: boolean }
type Slot = { start: string; end: string; local_label: string }
type AwaitingItem = {
  outbox_id: string; case_id: string; case_title: string; candidate_id: string; pseudonym: string; kind: string
  sent_at: string; days_waiting: number; due_at: string; overdue: boolean; follow_up_proposal_id: string | null
}
type HrAnswer = {
  abstained: boolean; reason: string | null; answer: string; method: string
  citation: { doc: string; doc_title: string; section: string; id: string } | null
  related: { doc_title: string; section: string; id: string }[]; confidence?: string
}

const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
const severityClass = (severity: string) => severity === 'high' ? 'danger' : severity === 'medium' ? 'warning' : ''

// ---------------------------------------------------------------------------------------------
// F1 + F2: AI Inbox (digest, triage, security flags, grounded reply drafts)
// ---------------------------------------------------------------------------------------------
export function InboxPage({ session }: Props) {
  const client = useQueryClient()
  const allowed = session.user.role === 'recruiter' || session.user.role === 'hr_admin'
  const [status, setStatus] = useState<'new' | 'handled' | 'all'>('new')
  const [selectedId, setSelectedId] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const digest = useQuery({
    queryKey: ['inbox', status],
    queryFn: () => api<Digest>(`/inbox?status=${status}`, session.token),
    enabled: allowed,
  })
  const items = (digest.data?.groups ?? []).flatMap(group => group.items)
  useEffect(() => {
    if (items.length && !items.some(item => item.id === selectedId)) setSelectedId(items[0].id)
  }, [items, selectedId])
  const upload = useMutation({
    mutationFn: (file: File) => { const form = new FormData(); form.append('file', file); return api<InboxItem>('/inbox/messages', session.token, { method: 'POST', body: form }) },
    onSuccess: async message => {
      toast.success('Email added and analysed. Links and attachments were not opened.')
      setStatus('new')
      await client.invalidateQueries({ queryKey: ['inbox'] })   // refetch first, so the new message is in the list
      setSelectedId(message.id)
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'The email could not be added.'),
  })
  if (!allowed) return <section><PageTitle title="AI Inbox" description="Candidate email triage for the recruitment team."/>
    <div className="honest-note">The inbox is available to recruiters and HR admins. Hiring managers review the resulting drafts in Approvals.</div></section>
  return <section>
    <PageTitle title="AI Inbox" description="Every message is summarised, sorted by urgency and checked for phishing and hidden instructions. Replies are drafts until a manager approves them."
      actions={<>
        <input ref={fileInput} type="file" accept=".eml,message/rfc822" hidden onChange={event => { const file = event.target.files?.[0]; if (file) upload.mutate(file); event.target.value = '' }}/>
        <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={upload.isPending}><Upload size={16}/>{upload.isPending ? 'Analysing…' : 'Add an email (.eml)'}</Button>
        <Button variant="outline" onClick={() => void digest.refetch()} disabled={digest.isFetching}><RefreshCw size={16}/>Refresh</Button>
      </>}/>
    <div className="warning-box inbox-demo-notice" role="note"><Mail size={18}/><span><strong>No mailbox is connected.</strong> All messages and summaries are synthetic demo data or emails you add as .eml files. Triage and summaries use rules, not an AI model; links and attachments are never opened.</span></div>
    {digest.isPending ? <LoadingRows/> : digest.isError ? <QueryError message={digest.error.message} retry={() => void digest.refetch()}/> : <>
      <div className="digest-stats">
        <div className="digest-stat"><strong>{digest.data.totals.messages}</strong><span>{status === 'handled' ? 'handled' : status === 'all' ? 'messages' : 'new messages'}</span></div>
        <div className="digest-stat urgent"><strong>{digest.data.totals.urgent}</strong><span>urgent</span></div>
        <div className="digest-stat flagged"><strong>{digest.data.totals.flagged}</strong><span>with security flags</span></div>
        <div className="digest-stat"><strong>{digest.data.totals.matched}</strong><span>from confirmed candidates</span></div>
        <div className="digest-status" role="group" aria-label="Show messages">{(['new', 'handled', 'all'] as const).map(value =>
          <Button key={value} size="sm" variant={status === value ? 'default' : 'outline'} onClick={() => setStatus(value)}>{humanize(value)}</Button>)}</div>
      </div>
      <div className="inbox-layout">
        <section className="surface inbox-list-panel" aria-label="Messages by category">
          {digest.data.groups.length ? digest.data.groups.map(group => <div key={group.category} className="digest-group">
            <h3 className={`digest-group-title cat-${group.category}`}>{group.category === 'security_review' ? <AlertTriangle size={14}/> : <Mail size={14}/>}{group.label}<span>{group.count} {group.count === 1 ? 'message' : 'messages'}{group.urgent ? ` · ${group.urgent} urgent` : ''}</span></h3>
            {group.items.map(item => <button key={item.id} type="button" className={`inbox-message ${selectedId === item.id ? 'selected' : ''}`}
              onClick={() => setSelectedId(item.id)} aria-pressed={selectedId === item.id}>
              <span className="inbox-message-heading"><strong dir="auto">{item.sender_name || item.sender_email}</strong><time>{new Date(item.received_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</time></span>
              <span className="inbox-message-subject" dir="auto">{item.urgency === 'high' && <Badge variant="outline" className="danger mini">Urgent</Badge>}{item.subject}</span>
              <span className="inbox-message-preview" dir="auto">{item.summary}</span>
            </button>)}
          </div>) : <NoRows title="Inbox is clear" text={status === 'new' ? 'No new messages. Switch to "All" to see handled ones.' : 'No messages here yet.'}/>}
        </section>
        {selectedId ? <MessageDetail key={selectedId} id={selectedId} session={session}/> :
          <section className="surface inbox-detail"><NoRows title="Select a message" text="Choose a message to see its summary, security checks and a reply draft."/></section>}
      </div>
      <p className="muted small assist-footnote">{digest.data.method}</p>
    </>}
  </section>
}

function MessageDetail({ id, session }: { id: string; session: Session }) {
  const client = useQueryClient()
  const message = useQuery({ queryKey: ['inbox-message', id], queryFn: () => api<InboxItem>(`/inbox/messages/${id}`, session.token) })
  const reply = useQuery({
    queryKey: ['reply-proposal', message.data?.reply_proposal_id],
    queryFn: () => api<ReplyProposal>(`/proposals/${message.data?.reply_proposal_id}`, session.token),
    enabled: !!message.data?.reply_proposal_id,
  })
  const draft = useMutation({
    mutationFn: () => api<{ proposal: ReplyProposal; created: boolean }>(`/inbox/messages/${id}/reply`, session.token, { method: 'POST', body: JSON.stringify({ timezone: browserZone() }) }),
    onSuccess: async result => {
      toast.success(result.proposal.sensitive_topic ? 'Neutral holding reply drafted: the message touches a sensitive topic.' : 'Reply drafted. It is sent only after the hiring manager approves it.')
      await client.invalidateQueries({ queryKey: ['inbox-message', id] }); await client.invalidateQueries({ queryKey: ['inbox'] })
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'The reply could not be drafted.'),
  })
  const setStatus = useMutation({
    mutationFn: (status: 'new' | 'handled') => api<InboxItem>(`/inbox/messages/${id}/status`, session.token, { method: 'POST', body: JSON.stringify({ status }) }),
    onSuccess: async (_, status) => { toast.success(status === 'handled' ? 'Marked as handled.' : 'Moved back to new.'); await client.invalidateQueries({ queryKey: ['inbox'] }); await client.invalidateQueries({ queryKey: ['inbox-message', id] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Status could not be changed.'),
  })
  if (message.isPending) return <section className="surface inbox-detail"><LoadingRows count={3}/></section>
  if (message.isError) return <section className="surface inbox-detail"><QueryError message={message.error.message} retry={() => void message.refetch()}/></section>
  const m = message.data
  const flagged = m.category === 'security_review'
  const canDraft = session.user.role === 'recruiter' && !flagged && !!m.candidate
  return <section className="surface inbox-detail">
    <div className="panel-heading"><div>
      <div className="badge-row"><Badge variant="outline" className={flagged ? 'danger' : ''}>{m.category_label}</Badge>{m.urgency === 'high' && <Badge variant="outline" className="danger">Urgent</Badge>}{m.source === 'demo' && <Badge variant="outline">Synthetic message</Badge>}{m.status === 'handled' && <Badge variant="outline" className="success">Handled</Badge>}</div>
      <h2 dir="auto">{m.subject}</h2>
      <p dir="auto">{m.sender_name ? `${m.sender_name} · ` : ''}{m.sender_email}</p>
      <p className="muted small">{m.candidate ? <>Confirmed candidate: <strong>{m.candidate.pseudonym}</strong>{m.case && <> · <Link to={`/cases/${m.case.id}`}>{m.case.title}</Link></>}</> : 'Not a confirmed candidate address'}</p>
    </div><Mail size={21}/></div>
    <section className="inbox-suggestion"><h3><Sparkles size={16}/> Summary</h3><p dir="auto">{m.summary}</p><small>Taken from the message itself (first sentences, personal data hidden). Nothing is invented.</small></section>
    {(m.findings.length > 0 || m.links.length > 0) && <section className={`inbox-suggestion security-checks ${flagged ? 'flagged' : ''}`}>
      <h3><ShieldCheck size={16}/> Security checks</h3>
      {m.findings.length ? <ul className="finding-list">{m.findings.map((f, index) => <li key={`${f.type}-${index}`}><Badge variant="outline" className={severityClass(f.severity)}>{humanize(f.type)}</Badge><span>{f.detail}</span></li>)}</ul> : <p className="muted small">No warning signs found.</p>}
      {m.links.length > 0 && <ul className="link-list">{m.links.map(link => <li key={link.url}><Link2 size={14}/><code dir="ltr">{link.host || link.url}</code>
        <Badge variant="outline" className={link.verdict === 'suspicious' ? 'danger' : ''}>{link.verdict === 'suspicious' ? 'Suspicious' : 'Not verified'}</Badge>
        {link.reasons.length > 0 && <span className="muted small">{link.reasons.join('; ')}</span>}</li>)}</ul>}
      <small>Links are shown as text and were never opened.</small>
    </section>}
    <details className="inbox-original"><summary><Paperclip size={14}/> Message text (cleaned: hidden text, quoted history and invisible characters removed)</summary>
      <div className="inbox-message-body" dir="auto">{m.safe_text || '(no readable text)'}</div></details>
    <section className="inbox-suggestion"><h3><Reply size={16}/> Suggested next step</h3><p>{m.suggested_action}</p>
      {reply.data ? <div className="reply-draft">
        <div className="badge-row"><Badge variant="outline">{humanize(reply.data.status)}</Badge>{reply.data.sensitive_topic && <Badge variant="outline" className="warning">Sensitive topic</Badge>}</div>
        <p className="reply-subject">{reply.data.payload.subject}</p><pre className="payload-preview" dir="auto">{reply.data.payload.body}</pre>
        <small>Drafted only from the candidate's record, the calendar and fixed wording. The hiring manager approves this exact text in <Link to="/approvals">Approvals</Link> before it can be sent.</small>
      </div> : <div className="page-actions">
        {canDraft && <Button onClick={() => draft.mutate()} disabled={draft.isPending}><Send size={16}/>{draft.isPending ? 'Drafting…' : 'Draft a reply'}</Button>}
        {!canDraft && !flagged && !m.candidate && <span className="muted small">Replies are drafted only to confirmed candidate addresses.</span>}
        {flagged && <span className="muted small">Vouch does not draft replies to flagged messages.</span>}
      </div>}
      <div className="page-actions">{m.status === 'new'
        ? <Button variant="outline" onClick={() => setStatus.mutate('handled')} disabled={setStatus.isPending}><Check size={16}/>Mark as handled</Button>
        : <Button variant="outline" onClick={() => setStatus.mutate('new')} disabled={setStatus.isPending}>Move back to new</Button>}</div>
    </section>
  </section>
}

// ---------------------------------------------------------------------------------------------
// F4: free interview slots (used inside the Schedule interview dialog)
// ---------------------------------------------------------------------------------------------
export function SlotSuggestions({ session, caseId, candidateId, interviewerId, duration, timezone, onPick }: {
  session: Session; caseId: string; candidateId: string; interviewerId: string; duration: number; timezone: string; onPick: (start: Date) => void
}) {
  const [asked, setAsked] = useState(false)
  const [picked, setPicked] = useState('')
  const ready = !!caseId && !!candidateId && !!interviewerId && duration >= 15 && duration % 15 === 0
  const params = new URLSearchParams({ candidate_id: candidateId, interviewer_id: interviewerId, duration: String(duration), timezone: timezone || 'UTC' })
  const slots = useQuery({
    queryKey: ['slots', caseId, candidateId, interviewerId, duration, timezone],
    queryFn: () => api<{ slots: Slot[]; rules: string }>(`/cases/${caseId}/slots?${params.toString()}`, session.token),
    enabled: asked && ready,
  })
  return <div className="slot-suggest schedule-wide">
    <div className="slot-head"><span><CalendarDays size={15}/> Free times in the interviewer's and candidate's calendars</span>
      <Button type="button" size="sm" variant="outline" onClick={() => { setAsked(true); void slots.refetch() }} disabled={!ready || slots.isFetching}>
        <Sparkles size={14}/>{slots.isFetching ? 'Looking…' : 'Suggest free times'}</Button></div>
    {!ready && <p className="muted small">Choose a case, a shortlisted candidate, an interviewer and a duration in steps of 15 minutes.</p>}
    {slots.isError && <p className="error-text">{slots.error.message}</p>}
    {slots.data && (slots.data.slots.length
      ? <div className="slot-chips" role="group" aria-label="Suggested free times">{slots.data.slots.map(slot =>
          <button type="button" key={slot.start} className={`slot-chip ${picked === slot.start ? 'on' : ''}`} aria-pressed={picked === slot.start}
            onClick={() => { setPicked(slot.start); onPick(new Date(slot.start)) }}><Clock3 size={13}/>{slot.local_label}</button>)}</div>
      : <p className="muted small">No free time found in the next days. Try a shorter duration.</p>)}
    {slots.data && <p className="muted small">{slots.data.rules}</p>}
  </div>
}

// ---------------------------------------------------------------------------------------------
// F3: messages without a reply (shown on the Follow-ups page)
// ---------------------------------------------------------------------------------------------
export function AwaitingReplies({ session }: Props) {
  const client = useQueryClient()
  const data = useQuery({
    queryKey: ['awaiting-reply'],
    queryFn: () => api<{ items: AwaitingItem[]; total: number; overdue: number; wait_days: number; statement: string }>('/follow-ups/awaiting-reply', session.token),
  })
  const replied = useMutation({
    mutationFn: (oid: string) => api(`/outbox/${oid}/replied`, session.token, { method: 'POST', body: '{}' }),
    onSuccess: async () => { toast.success('Reply recorded.'); await client.invalidateQueries({ queryKey: ['awaiting-reply'] }) },
    onError: error => toast.error(error instanceof Error ? error.message : 'Could not record the reply.'),
  })
  const followUp = useMutation({
    mutationFn: (oid: string) => api<{ proposal: { id: string }; created: boolean }>(`/outbox/${oid}/follow-up`, session.token, { method: 'POST', body: '{}' }),
    onSuccess: async result => {
      toast.success(result.created ? 'Follow-up drafted and added to your tasks. The hiring manager must approve it before it is sent.' : 'A follow-up draft already exists.')
      await client.invalidateQueries({ queryKey: ['awaiting-reply'] }); await client.invalidateQueries({ queryKey: ['follow-ups'] }); await client.invalidateQueries({ queryKey: ['approval-inbox'] })
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'Could not draft the follow-up.'),
  })
  const canAct = session.user.role === 'recruiter'
  return <section className="surface workspace-section awaiting-replies">
    <div className="panel-heading"><div><h2>Waiting for a reply</h2><p>Messages sent through the gateway that the candidate has not answered. After {data.data?.wait_days ?? 3} days they are flagged for a follow-up.</p></div>
      {data.data && <Badge variant="outline" className={data.data.overdue ? 'warning' : ''}>{data.data.overdue} overdue · {data.data.total} waiting</Badge>}</div>
    {data.isPending ? <LoadingRows count={2}/> : data.isError ? <QueryError message={data.error.message} retry={() => void data.refetch()}/> :
      data.data.items.length ? <div className="awaiting-list">{data.data.items.map(item => <article key={item.outbox_id} className={`awaiting-item ${item.overdue ? 'overdue' : ''}`}>
        <div><strong dir="auto">{item.pseudonym}</strong><span className="muted small"> · {humanize(item.kind)} · {item.case_title}</span>
          <p className="small">{item.days_waiting === 0 ? 'Sent today' : `Sent ${item.days_waiting} day${item.days_waiting === 1 ? '' : 's'} ago`}
            {item.overdue ? <Badge variant="outline" className="warning mini">No reply yet · follow up</Badge> : <span className="muted"> · follow-up due {new Date(item.due_at).toLocaleDateString()}</span>}</p></div>
        {canAct && <div className="page-actions">
          <Button size="sm" variant="outline" onClick={() => replied.mutate(item.outbox_id)} disabled={replied.isPending}><Check size={14}/>They replied</Button>
          {item.follow_up_proposal_id
            ? <Link className="button-link" to="/approvals">Follow-up awaiting approval</Link>
            : <Button size="sm" onClick={() => followUp.mutate(item.outbox_id)} disabled={followUp.isPending}><Send size={14}/>Draft follow-up</Button>}
        </div>}
      </article>)}</div> : <NoRows title="Nobody is waiting" text="Sent messages without a reply appear here."/>}
    {data.data && <p className="muted small">{data.data.statement}</p>}
  </section>
}

// ---------------------------------------------------------------------------------------------
// F5: HR assistant for employee questions
// ---------------------------------------------------------------------------------------------
const SAMPLE_QUESTIONS = ['How many days of annual leave do I get?', 'Can I work from home?', 'How do I get my expenses reimbursed?',
  'I received a suspicious email asking for my password', 'Combien de jours de congés par an ?']

export function HrAssistantPage({ session }: Props) {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<{ question: string; result: HrAnswer }[]>([])
  const handbook = useQuery({
    queryKey: ['hr-handbook'],
    queryFn: () => api<{ company: string; documents: { title: string; sections: string[] }[] }>('/hr/handbook', session.token),
  })
  const ask = useMutation({
    mutationFn: (q: string) => api<HrAnswer>('/hr/ask', session.token, { method: 'POST', body: JSON.stringify({ question: q }) }),
    onSuccess: (result, q) => { setHistory(current => [{ question: q, result }, ...current].slice(0, 20)); setQuestion('') },
    onError: error => toast.error(error instanceof Error ? error.message : 'The question could not be answered.'),
  })
  const submit = (q: string) => { const value = q.trim(); if (value.length >= 3) ask.mutate(value) }
  return <section>
    <PageTitle title="HR Assistant" description="Ask a question about leave, remote work, expenses, training or conduct. Every answer quotes the HR handbook and names its section."/>
    <div className="hr-layout">
      <section className="surface hr-chat">
        <form className="hr-ask" onSubmit={event => { event.preventDefault(); submit(question) }}>
          <Input value={question} maxLength={500} placeholder="Ask about leave, remote work, expenses…" aria-label="Your question" onChange={event => setQuestion(event.target.value)}/>
          <Button type="submit" disabled={ask.isPending || question.trim().length < 3}>{ask.isPending ? 'Searching…' : 'Ask'}</Button>
        </form>
        <div className="hr-samples">{SAMPLE_QUESTIONS.map(sample => <button type="button" key={sample} className="slot-chip" onClick={() => submit(sample)}>{sample}</button>)}</div>
        {history.length ? <div className="hr-history">{history.map((entry, index) => <article key={`${entry.question}-${index}`} className={`hr-answer ${entry.result.abstained ? 'abstained' : ''}`}>
          <p className="hr-question" dir="auto">{entry.question}</p>
          {entry.result.citation && <p className="hr-citation"><BookOpen size={14}/>{entry.result.citation.doc_title} › <strong>{entry.result.citation.section}</strong>{entry.result.confidence && <Badge variant="outline" className="mini">{entry.result.confidence} match</Badge>}</p>}
          <blockquote dir="auto">{entry.result.answer}</blockquote>
          {entry.result.abstained && <p className="muted small">{entry.result.reason === 'personal' ? 'Private matters go to HR in person.' : 'Not in the handbook, so no answer was guessed.'}</p>}
          {entry.result.related.length > 0 && <p className="muted small">See also: {entry.result.related.map(r => `${r.doc_title} › ${r.section}`).join(' · ')}</p>}
        </article>)}</div> : <NoRows title="Ask your first question" text="Answers come only from the handbook. If the handbook doesn't cover it, the assistant says so."/>}
        <p className="muted small assist-footnote">Answers quote the handbook of Northwind Demo Ltd, a fictional company. No AI model; questions are not stored (the ledger keeps only a hash).</p>
      </section>
      <aside className="surface hr-handbook"><h2><BookOpen size={16}/> Handbook</h2>
        {handbook.isPending ? <LoadingRows count={3}/> : handbook.isError ? <QueryError message={handbook.error.message}/> :
          handbook.data.documents.map(doc => <div key={doc.title}><h3>{doc.title}</h3><ul>{doc.sections.map(section => <li key={section}>{section}</li>)}</ul></div>)}
      </aside>
    </div>
  </section>
}
