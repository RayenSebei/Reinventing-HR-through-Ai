import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addDays, addMonths, addWeeks, differenceInCalendarDays, endOfMonth, endOfWeek, format, isSameMonth,
  isToday, startOfDay, startOfMonth, startOfWeek, subDays, subMonths, subWeeks,
} from 'date-fns'
import { toast } from 'sonner'
import { Bot, CalendarDays, ChevronLeft, ChevronRight, Clock3, Lock, MapPin, Plus, Sparkles, UserRound, Users } from 'lucide-react'
import { api, humanize, type Session } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import './agenda.css'

/* ---------- types (match vouch/app/agenda.py) ---------- */
export type FormatKey = 'ai_chat' | 'recruiter' | 'senior_hr'
export type FormatInfo = {
  interview_id: string; recommended: FormatKey; recommended_label: string; reasons: string[]
  decided: FormatKey | null; decided_label: string | null; decided_by: string | null; decided_at: string | null
  overridden: boolean; conducted_by: 'ai' | 'human' | null; conducted_by_set_by: string | null
  conducted_by_at: string | null; statement: string
}
export type AgendaInterview = {
  kind: 'interview'; id: string; case_id: string; candidate_id: string; interviewer_id: string
  interview_type: string; start: string; scheduled_start: string; duration_minutes: number; timezone: string
  location: string; status: string; preparation_notes: string; feedback: string; created_at: string
  completed_at: string | null; candidate_pseudonym: string; case_title: string; interviewer_name: string
  format: FormatInfo; can_edit: boolean
}
export type AgendaMeeting = {
  kind: 'meeting'; id: string; title: string; description: string; location: string; start: string
  duration_minutes: number; timezone: string; status: string; private: boolean; attendee_ids: string[]
  attendee_names: string[]; organizer_id: string; can_edit: boolean
}
type AgendaEvent = AgendaInterview | AgendaMeeting
type AgendaResponse = { from: string; to: string; events: AgendaEvent[]; fast_track_score: number }
type View = 'day' | 'week' | 'month'
type Person = { id: string; name: string; role: string }

export const FORMAT_TEXT: Record<FormatKey, { label: string; short: string }> = {
  ai_chat: { label: 'AI chat interview (first round)', short: 'AI chat' },
  recruiter: { label: 'Recruiter', short: 'Recruiter' },
  senior_hr: { label: 'Senior HR interviewer', short: 'Senior HR' },
}

const HOUR_START = 0
const HOUR_END = 24
const SCROLL_TO_HOUR = 8
const HOUR_PX = 52
const SLOT_MIN = 30

/* ---------- helpers ---------- */
const startOf = (e: AgendaEvent) => new Date(e.start)
const endOf = (e: AgendaEvent) => new Date(new Date(e.start).getTime() + e.duration_minutes * 60_000)
const dayKey = (d: Date) => format(d, 'yyyy-MM-dd')
const formatOf = (e: AgendaInterview): FormatKey => e.format.decided ?? e.format.recommended
const isMine = (e: AgendaEvent, userId: string) =>
  e.kind === 'interview' ? e.interviewer_id === userId : e.attendee_ids.includes(userId) || e.organizer_id === userId

function eventLabel(e: AgendaEvent) {
  return e.kind === 'interview' ? `${e.candidate_pseudonym} · ${humanize(e.interview_type)}` : e.title
}

function visibleRange(view: View, anchor: Date) {
  if (view === 'day') return { from: startOfDay(anchor), to: startOfDay(anchor) }
  if (view === 'week') return { from: startOfWeek(anchor, { weekStartsOn: 1 }), to: endOfWeek(anchor, { weekStartsOn: 1 }) }
  return { from: startOfWeek(startOfMonth(anchor), { weekStartsOn: 1 }), to: endOfWeek(endOfMonth(anchor), { weekStartsOn: 1 }) }
}

/** Lay out overlapping events side by side, like Google Calendar. */
function layoutDay(events: AgendaEvent[]) {
  const sorted = [...events].sort((a, b) => startOf(a).getTime() - startOf(b).getTime() || b.duration_minutes - a.duration_minutes)
  const placed: { event: AgendaEvent; col: number; cols: number }[] = []
  let cluster: { event: AgendaEvent; col: number }[] = []
  let clusterEnd = 0
  const flush = () => {
    const cols = Math.max(1, ...cluster.map(c => c.col + 1))
    cluster.forEach(c => placed.push({ ...c, cols }))
    cluster = []
  }
  for (const event of sorted) {
    const s = startOf(event).getTime()
    if (cluster.length && s >= clusterEnd) flush()
    const used = new Set(cluster.filter(c => endOf(c.event).getTime() > s).map(c => c.col))
    let col = 0
    while (used.has(col)) col++
    cluster.push({ event, col })
    clusterEnd = Math.max(clusterEnd, endOf(event).getTime())
  }
  flush()
  return placed
}

function useNow(intervalMs = 60_000) {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => { const t = setInterval(() => setNow(new Date()), intervalMs); return () => clearInterval(t) }, [intervalMs])
  return now
}

function localInput(d: Date) {
  const off = d.getTimezoneOffset() * 60_000
  return new Date(d.getTime() - off).toISOString().slice(0, 16)
}

/* ---------- main component ---------- */
export function Agenda({ session, onNewInterview, renderInterview }: {
  session: Session
  onNewInterview?: (start: Date) => void
  renderInterview: (interview: AgendaInterview) => React.ReactNode
}) {
  const client = useQueryClient()
  const [view, setView] = useState<View>(() => (typeof window !== 'undefined' && window.innerWidth < 760 ? 'day' : 'week'))
  const [anchor, setAnchor] = useState(() => new Date())
  const [show, setShow] = useState({ interviews: true, meetings: true, onlyMine: false })
  const [selected, setSelected] = useState<AgendaEvent | null>(null)
  const [createAt, setCreateAt] = useState<Date | null>(null)
  const range = visibleRange(view, anchor)
  const agenda = useQuery({
    queryKey: ['agenda', session.user.id, dayKey(range.from), dayKey(range.to)],
    queryFn: () => api<AgendaResponse>(`/agenda?from=${dayKey(range.from)}&to=${dayKey(range.to)}`, session.token),
  })
  const events = useMemo(() => (agenda.data?.events ?? []).filter(e =>
    (e.kind === 'interview' ? show.interviews : show.meetings) && (!show.onlyMine || isMine(e, session.user.id)),
  ), [agenda.data, show, session.user.id])
  const byDay = useMemo(() => {
    const map = new Map<string, AgendaEvent[]>()
    for (const e of events) { const k = dayKey(startOf(e)); map.set(k, [...(map.get(k) ?? []), e]) }
    return map
  }, [events])
  // keep the open detail panel in sync with fresh data
  const selectedFresh = selected ? (agenda.data?.events.find(e => e.id === selected.id && e.kind === selected.kind) ?? selected) : null

  const move = (dir: -1 | 1) => setAnchor(a =>
    view === 'day' ? (dir > 0 ? addDays(a, 1) : subDays(a, 1))
      : view === 'week' ? (dir > 0 ? addWeeks(a, 1) : subWeeks(a, 1))
        : (dir > 0 ? addMonths(a, 1) : subMonths(a, 1)))
  const title = view === 'month' ? format(anchor, 'MMMM yyyy')
    : view === 'day' ? format(anchor, 'EEEE d MMMM yyyy')
      : isSameMonth(range.from, range.to) ? `${format(range.from, 'd')} – ${format(range.to, 'd MMMM yyyy')}`
        : `${format(range.from, 'd MMM')} – ${format(range.to, 'd MMM yyyy')}`
  const canAdd = session.user.role !== 'auditor'
  const openCreate = (when: Date) => {
    if (!canAdd) return
    if (when.getTime() <= Date.now()) { toast.error('Pick a time in the future.'); return }
    setCreateAt(when)
  }
  const refresh = () => client.invalidateQueries({ queryKey: ['agenda'] })

  return <section className="agenda surface" aria-label="Interview and meeting calendar">
    <div className="agenda-toolbar">
      <div className="agenda-nav">
        <Button variant="outline" onClick={() => setAnchor(new Date())}>Today</Button>
        <Button variant="ghost" size="icon" aria-label="Previous" onClick={() => move(-1)}><ChevronLeft/></Button>
        <Button variant="ghost" size="icon" aria-label="Next" onClick={() => move(1)}><ChevronRight/></Button>
        <h2 className="agenda-title" aria-live="polite">{title}</h2>
      </div>
      <div className="agenda-controls">
        {canAdd && <Button onClick={() => {
          const next = new Date(); next.setSeconds(0, 0); next.setMinutes(next.getMinutes() < 30 ? 30 : 60)
          const day = new Date(anchor); day.setHours(10, 0, 0, 0)
          openCreate(view === 'day' && day.getTime() > next.getTime() ? day : next)
        }}><Plus size={16}/>New</Button>}
        <div className="agenda-views" role="tablist" aria-label="Calendar view">
          {(['day', 'week', 'month'] as View[]).map(v =>
            <button key={v} role="tab" aria-selected={view === v} className={view === v ? 'active' : ''} onClick={() => setView(v)}>{humanize(v)}</button>)}
        </div>
      </div>
    </div>
    <div className="agenda-filters">
      <label><input type="checkbox" checked={show.interviews} onChange={e => setShow(s => ({ ...s, interviews: e.target.checked }))}/>Interviews</label>
      <label><input type="checkbox" checked={show.meetings} onChange={e => setShow(s => ({ ...s, meetings: e.target.checked }))}/>Internal meetings</label>
      <label><input type="checkbox" checked={show.onlyMine} onChange={e => setShow(s => ({ ...s, onlyMine: e.target.checked }))}/>Only mine</label>
      <Legend/>
    </div>
    {agenda.isError && <div className="warning-box" role="alert">Could not load the calendar: {agenda.error.message} <Button variant="outline" onClick={() => void agenda.refetch()}>Retry</Button></div>}
    {view === 'month'
      ? <MonthGrid anchor={anchor} range={range} byDay={byDay} onPick={setSelected} onDay={d => { setAnchor(d); setView('day') }} onCreate={openCreate}/>
      : <TimeGrid days={view === 'day' ? [range.from] : Array.from({ length: 7 }, (_, i) => addDays(range.from, i))}
          byDay={byDay} onPick={setSelected} onCreate={openCreate} loading={agenda.isPending}/>}

    <EventSheet event={selectedFresh} session={session} onClose={() => setSelected(null)} onChanged={refresh} renderInterview={renderInterview}/>
    <CreateDialog at={createAt} session={session} onClose={() => setCreateAt(null)} onCreated={refresh}
      onNewInterview={onNewInterview && session.user.role === 'recruiter' ? (d => { setCreateAt(null); onNewInterview(d) }) : undefined}/>
  </section>
}

function Legend() {
  return <div className="agenda-legend" aria-label="Colour legend">
    <span><i className="sw fmt-ai_chat"/>AI chat</span>
    <span><i className="sw fmt-recruiter"/>Recruiter</span>
    <span><i className="sw fmt-senior_hr"/>Senior HR</span>
    <span><i className="sw kind-meeting"/>Meeting</span>
    <span><i className="sw kind-busy"/>Busy</span>
    <span className="legend-note">Dashed border = format suggested, not yet decided</span>
  </div>
}

/* ---------- week / day grid ---------- */
function TimeGrid({ days, byDay, onPick, onCreate, loading }: {
  days: Date[]; byDay: Map<string, AgendaEvent[]>; onPick: (e: AgendaEvent) => void; onCreate: (d: Date) => void; loading: boolean
}) {
  const now = useNow()
  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => {
    scroller.current?.scrollTo({ top: (SCROLL_TO_HOUR - HOUR_START) * HOUR_PX - 14 })
  }, [])
  const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i)
  const cols = `56px repeat(${days.length}, minmax(0, 1fr))`
  return <div className="agenda-grid-wrap">
    <div className="agenda-head" style={{ gridTemplateColumns: cols }}>
      <div/>
      {days.map(d => <div key={dayKey(d)} className={`agenda-dayhead${isToday(d) ? ' today' : ''}`}>
        <span>{format(d, 'EEE')}</span><strong>{format(d, 'd')}</strong></div>)}
    </div>
    <div className="agenda-scroll" ref={scroller} aria-busy={loading}>
      <div className="agenda-body" style={{ gridTemplateColumns: cols, height: hours.length * HOUR_PX }}>
        <div className="agenda-hours">{hours.map(h => <span key={h} style={{ top: (h - HOUR_START) * HOUR_PX }}>{format(new Date(2000, 0, 1, h), 'HH:mm')}</span>)}</div>
        {days.map(d => {
          const placed = layoutDay(byDay.get(dayKey(d)) ?? [])
          return <div key={dayKey(d)} className={`agenda-col${isToday(d) ? ' today' : ''}`}
            onClick={ev => {
              if (ev.target !== ev.currentTarget) return
              const y = ev.nativeEvent.offsetY
              const minutes = Math.floor((y / HOUR_PX) * 60 / SLOT_MIN) * SLOT_MIN
              const when = new Date(d); when.setHours(HOUR_START, 0, 0, 0); when.setMinutes(minutes)
              onCreate(when)
            }}
            title="Click an empty slot to add a meeting or an interview">
            {hours.map(h => <div key={h} className="agenda-hourline" style={{ top: (h - HOUR_START) * HOUR_PX }}/>)}
            {isToday(d) && now.getHours() >= HOUR_START && now.getHours() < HOUR_END &&
              <div className="agenda-now" style={{ top: (now.getHours() - HOUR_START + now.getMinutes() / 60) * HOUR_PX }} aria-hidden/>}
            {placed.map(({ event, col, cols: n }) => {
              const s = startOf(event)
              const top = Math.max(0, (s.getHours() - HOUR_START + s.getMinutes() / 60) * HOUR_PX)
              const height = Math.max(22, Math.min(event.duration_minutes / 60 * HOUR_PX, (HOUR_END - HOUR_START) * HOUR_PX - top) - 2)
              return <EventBlock key={event.kind + event.id} event={event} onPick={onPick}
                style={{ top, height, left: `calc(${(col / n) * 100}% + 2px)`, width: `calc(${100 / n}% - 4px)` }}/>
            })}
          </div>
        })}
      </div>
    </div>
  </div>
}

function eventClass(e: AgendaEvent) {
  if (e.kind === 'meeting') return e.private ? 'kind-busy' : 'kind-meeting'
  return `fmt-${formatOf(e)}${e.format.decided ? '' : ' suggested'}${e.status === 'completed' ? ' done' : ''}`
}

function EventBlock({ event, onPick, style }: { event: AgendaEvent; onPick: (e: AgendaEvent) => void; style: React.CSSProperties }) {
  const s = startOf(event)
  const time = `${format(s, 'HH:mm')}–${format(endOf(event), 'HH:mm')}`
  const conducted = event.kind === 'interview' ? event.format.conducted_by : null
  return <button type="button" className={`agenda-event ${eventClass(event)}${event.duration_minutes < 45 ? ' short' : ''}`} style={style} onClick={() => onPick(event)}
    aria-label={`${eventLabel(event)}, ${format(s, 'EEEE d MMMM HH:mm')}`}>
    <span className="ev-title" dir="auto">
      {event.kind === 'meeting' && event.private && <Lock size={11}/>}
      {conducted === 'ai' && <Bot size={11} aria-label="Interviewed by AI chat"/>}
      {conducted === 'human' && <UserRound size={11} aria-label="Interviewed by a person"/>}
      {eventLabel(event)}
    </span>
    <span className="ev-time">{time}</span>
    {event.kind === 'interview' && event.duration_minutes >= 60 && <span className="ev-sub">{FORMAT_TEXT[formatOf(event)].short}{event.format.decided ? '' : ' · suggested'}</span>}
    {event.kind === 'meeting' && event.private && event.duration_minutes >= 60 && <span className="ev-sub" dir="auto">{event.attendee_names.join(', ')}</span>}
  </button>
}

/* ---------- month grid ---------- */
function MonthGrid({ anchor, range, byDay, onPick, onDay, onCreate }: {
  anchor: Date; range: { from: Date; to: Date }; byDay: Map<string, AgendaEvent[]>
  onPick: (e: AgendaEvent) => void; onDay: (d: Date) => void; onCreate: (d: Date) => void
}) {
  const count = differenceInCalendarDays(range.to, range.from) + 1
  const days = Array.from({ length: count }, (_, i) => addDays(range.from, i))
  return <div className="agenda-month">
    {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => <div key={d} className="month-dow">{d}</div>)}
    {days.map(d => {
      const list = [...(byDay.get(dayKey(d)) ?? [])].sort((a, b) => startOf(a).getTime() - startOf(b).getTime())
      return <div key={dayKey(d)} className={`month-cell${isSameMonth(d, anchor) ? '' : ' other'}${isToday(d) ? ' today' : ''}`}
        onDoubleClick={() => { const w = new Date(d); w.setHours(10, 0, 0, 0); onCreate(w) }}>
        <button type="button" className="month-date" onClick={() => onDay(d)} aria-label={`Open ${format(d, 'EEEE d MMMM')}`}>{format(d, 'd')}</button>
        {list.slice(0, 3).map(e => <button type="button" key={e.kind + e.id} className={`month-chip ${eventClass(e)}`} onClick={() => onPick(e)}>
          <b>{format(startOf(e), 'HH:mm')}</b> <span dir="auto">{eventLabel(e)}</span></button>)}
        {list.length > 3 && <button type="button" className="month-more" onClick={() => onDay(d)}>+{list.length - 3} more</button>}
      </div>
    })}
  </div>
}

/* ---------- detail panel ---------- */
function EventSheet({ event, session, onClose, onChanged, renderInterview }: {
  event: AgendaEvent | null; session: Session; onClose: () => void; onChanged: () => void
  renderInterview: (i: AgendaInterview) => React.ReactNode
}) {
  return <Sheet open={!!event} onOpenChange={open => { if (!open) onClose() }}>
    <SheetContent className="agenda-sheet">
      {event?.kind === 'interview' && <>
        <SheetHeader>
          <SheetTitle dir="auto">{event.candidate_pseudonym}</SheetTitle>
          <SheetDescription>{format(startOf(event), 'EEEE d MMMM, HH:mm')}–{format(endOf(event), 'HH:mm')} · {event.case_title}</SheetDescription>
        </SheetHeader>
        <div className="sheet-body">
          <FormatPanel interview={event} session={session} onChanged={onChanged}/>
          {renderInterview(event)}
        </div>
      </>}
      {event?.kind === 'meeting' && <MeetingDetail meeting={event} session={session} onChanged={() => { onChanged(); onClose() }}/>}
    </SheetContent>
  </Sheet>
}

export function FormatPanel({ interview, session, onChanged }: { interview: AgendaInterview; session: Session; onChanged: () => void }) {
  const f = interview.format
  const current = f.decided ?? f.recommended
  const [choice, setChoice] = useState<FormatKey>(current)
  useEffect(() => setChoice(f.decided ?? f.recommended), [f.decided, f.recommended])
  const isRecruiter = session.user.role === 'recruiter' && interview.can_edit
  const canRecordConducted = isRecruiter || (session.user.role === 'hiring_manager' && interview.interviewer_id === session.user.id)
  const decide = useMutation({
    mutationFn: (fmt: FormatKey) => api<FormatInfo>(`/interviews/${interview.id}/format`, session.token, { method: 'POST', body: JSON.stringify({ format: fmt }) }),
    onSuccess: r => { toast.success(`Interview format set: ${FORMAT_TEXT[r.decided ?? r.recommended].label}.`); onChanged() },
    onError: e => toast.error(e instanceof Error ? e.message : 'Could not save the format.'),
  })
  const conducted = useMutation({
    mutationFn: (by: 'ai' | 'human') => api<FormatInfo>(`/interviews/${interview.id}/conducted-by`, session.token, { method: 'POST', body: JSON.stringify({ by }) }),
    onSuccess: r => { toast.success(r.conducted_by === 'human' ? 'Recorded: interviewed by a person.' : 'Recorded: interviewed by the AI chat.'); onChanged() },
    onError: e => toast.error(e instanceof Error ? e.message : 'Could not save.'),
  })
  return <div className="format-panel">
    <div className="format-head">
      <div><span className="eyebrow"><Sparkles size={13}/>Recommended interview format</span>
        <h3><i className={`sw fmt-${f.recommended}`}/>{FORMAT_TEXT[f.recommended].label}</h3></div>
      {f.decided
        ? <Badge variant="outline" className="decided">Decided: {FORMAT_TEXT[f.decided].short}{f.overridden ? ' (changed by a person)' : ''}</Badge>
        : <Badge variant="outline" className="pending">Suggestion · waiting for a recruiter</Badge>}
    </div>
    <ul className="format-reasons">{f.reasons.map(r => <li key={r} dir="auto">{r}</li>)}</ul>
    {isRecruiter && interview.status !== 'cancelled' && <div className="format-decide">
      <div className="format-options" role="radiogroup" aria-label="Interview format">
        {(Object.keys(FORMAT_TEXT) as FormatKey[]).map(k =>
          <label key={k} className={choice === k ? 'on' : ''}>
            <input type="radio" name={`fmt-${interview.id}`} checked={choice === k} onChange={() => setChoice(k)}/>
            <i className={`sw fmt-${k}`}/>{FORMAT_TEXT[k].short}{k === f.recommended ? ' · suggested' : ''}</label>)}
      </div>
      <Button disabled={decide.isPending || choice === f.decided} onClick={() => decide.mutate(choice)}>
        {choice === f.recommended && !f.decided ? 'Accept suggestion' : 'Save format'}</Button>
    </div>}
    <div className="conducted">
      <span className="eyebrow">Interviewed by</span>
      <div className="conducted-state" aria-live="polite">
        {f.conducted_by === 'ai' && <span className="state ai"><Bot size={15}/>AI chat interview</span>}
        {f.conducted_by === 'human' && <span className="state human"><UserRound size={15}/>A person (real employee)</span>}
        {!f.conducted_by && <span className="state none">Not interviewed yet</span>}
      </div>
      {canRecordConducted && f.conducted_by !== 'human' && interview.status !== 'cancelled' && <div className="conducted-actions">
        {!f.conducted_by && <Button variant="outline" disabled={conducted.isPending} onClick={() => conducted.mutate('ai')}><Bot size={15}/>Mark as done by AI chat</Button>}
        <Button disabled={conducted.isPending} onClick={() => conducted.mutate('human')}><UserRound size={15}/>
          {f.conducted_by === 'ai' ? 'Change to: interviewed by a person' : 'Mark as done by a person'}</Button>
      </div>}
      {f.conducted_by === 'human' && <p className="muted small">Once a person has interviewed the candidate, this can’t be changed back to AI.</p>}
    </div>
    <p className="honest-note">{f.statement}</p>
  </div>
}

function MeetingDetail({ meeting, session, onChanged }: { meeting: AgendaMeeting; session: Session; onChanged: () => void }) {
  const cancel = useMutation({
    mutationFn: () => api(`/meetings/${meeting.id}`, session.token, { method: 'DELETE' }),
    onSuccess: () => { toast.success('Meeting cancelled.'); onChanged() },
    onError: e => toast.error(e instanceof Error ? e.message : 'Could not cancel.'),
  })
  return <>
    <SheetHeader>
      <SheetTitle dir="auto">{meeting.private ? <><Lock size={16}/> Busy</> : meeting.title}</SheetTitle>
      <SheetDescription>{format(startOf(meeting), 'EEEE d MMMM, HH:mm')}–{format(endOf(meeting), 'HH:mm')} · internal meeting</SheetDescription>
    </SheetHeader>
    <div className="sheet-body meeting-detail">
      {meeting.private && <p className="honest-note">You are not invited, so only the time and the people are shown.</p>}
      {meeting.location && <p><MapPin size={15}/><span dir="auto">{meeting.location}</span></p>}
      <p><Users size={15}/><span dir="auto">{meeting.attendee_names.join(', ')}</span></p>
      <p><Clock3 size={15}/>{meeting.duration_minutes} min · {meeting.timezone}</p>
      {meeting.description && <p className="meeting-notes" dir="auto">{meeting.description}</p>}
      {meeting.can_edit && <Button variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}>Cancel meeting</Button>}
    </div>
  </>
}

/* ---------- create dialog ---------- */
function CreateDialog({ at, session, onClose, onCreated, onNewInterview }: {
  at: Date | null; session: Session; onClose: () => void; onCreated: () => void; onNewInterview?: (d: Date) => void
}) {
  const [title, setTitle] = useState('')
  const [start, setStart] = useState('')
  const [duration, setDuration] = useState('30')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [attendees, setAttendees] = useState<string[]>([])
  useEffect(() => { if (at) { setStart(localInput(at)); setTitle(''); setDescription(''); setLocation(''); setAttendees([]) } }, [at])
  const people = useQuery({ queryKey: ['users'], queryFn: () => api<Person[]>('/users', session.token), enabled: !!at })
  const create = useMutation({
    mutationFn: () => api<AgendaMeeting>('/meetings', session.token, { method: 'POST', body: JSON.stringify({
      title, start: new Date(start).toISOString(), duration_minutes: Number(duration),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', location, description, attendee_ids: attendees,
    }) }),
    onSuccess: () => { toast.success('Meeting added to the calendar. No invitation was emailed.'); onCreated(); onClose() },
    onError: e => toast.error(e instanceof Error ? e.message : 'Could not add the meeting.'),
  })
  return <Dialog open={!!at} onOpenChange={o => { if (!o) onClose() }}>
    <DialogContent className="agenda-create">
      <DialogHeader>
        <DialogTitle>{at ? format(at, 'EEEE d MMMM, HH:mm') : ''}</DialogTitle>
        <DialogDescription>Add an internal meeting (not about recruitment){onNewInterview ? ', or schedule an interview' : ''}.</DialogDescription>
      </DialogHeader>
      {onNewInterview && at && <Button variant="outline" className="create-interview" onClick={() => onNewInterview(new Date(start || at))}>
        <CalendarDays size={16}/>Schedule a candidate interview at this time</Button>}
      <form className="stack-form" onSubmit={e => { e.preventDefault(); create.mutate() }}>
        <label>Meeting title<Input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Weekly HR team sync"/></label>
        <div className="row-2">
          <label>Start<Input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)}/></label>
          <label>Duration<select value={duration} onChange={e => setDuration(e.target.value)}>
            {[15, 30, 45, 60, 90, 120, 180, 240].map(m => <option key={m} value={m}>{m < 60 ? `${m} min` : `${m / 60} h`}</option>)}</select></label>
        </div>
        <label>Room or link<Input maxLength={300} value={location} onChange={e => setLocation(e.target.value)}/></label>
        <fieldset className="attendees"><legend>Invite colleagues</legend>
          {people.data?.filter(p => p.id !== session.user.id && p.role !== 'auditor').map(p =>
            <label key={p.id}><input type="checkbox" checked={attendees.includes(p.id)}
              onChange={e => setAttendees(a => e.target.checked ? [...a, p.id] : a.filter(x => x !== p.id))}/>{p.name}</label>)}
        </fieldset>
        <label>Notes (visible to invited people only)<Textarea maxLength={4000} value={description} onChange={e => setDescription(e.target.value)}/></label>
        <p className="honest-note">People who are not invited will only see “Busy”. Nobody is emailed.</p>
        <Button type="submit" disabled={create.isPending || !title.trim()}>{create.isPending ? 'Adding…' : 'Add meeting'}</Button>
      </form>
    </DialogContent>
  </Dialog>
}
