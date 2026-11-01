import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import { ArrowRight, BriefcaseBusiness, CalendarDays, Check, ChevronRight, CircleCheck, Clock3, FileCheck2, Fingerprint, LayoutDashboard, ListTodo, LogOut, Mail, Moon, RefreshCw, Search, Settings, ShieldCheck, ShieldX, Sun, Users, X, Menu, AlertTriangle, Link2, Send, Presentation } from 'lucide-react'
import { useReducedMotion } from 'motion/react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Toaster } from '@/components/ui/sonner'
import { api, ApiError, readSession, roleName, humanize, timeLabel, type Session, type User, type Meta, type Overview, type Attention } from '@/lib/api'
import { AdminPage, ApprovalsPage, AssurancePage, CandidatesPage, CaseWorkspace, CasesPage, FollowUpsPage, InboxPage, InterviewsPage, LedgerPage } from '@/pages/WorkspacePages'

const NAV = [
  {label:'Overview', icon:LayoutDashboard, path:'/', section:'Workspace'},
  {label:'Recruitment',icon:BriefcaseBusiness,path:'/cases',section:'Workspace'},
  {label:'Candidates',icon:Users,path:'/candidates',section:'Workspace'},
  {label:'AI Inbox',icon:Mail,path:'/inbox',section:'Workspace'},
  {label:'Interviews',icon:CalendarDays,path:'/interviews',section:'Workspace'},
  {label:'Follow-ups',icon:ListTodo,path:'/follow-ups',section:'Workspace'},
  {label:'Approvals',icon:FileCheck2,path:'/approvals',section:'Governance'},
  {label:'Audit Ledger',icon:Link2,path:'/ledger',section:'Governance'},
  {label:'Security & Assurance',icon:ShieldCheck,path:'/assurance',section:'Governance'},
  {label:'Settings',icon:Settings,path:'/admin',section:'Administration',role:'hr_admin'},
]
const DEMO_SCRIPT = [
  { time: '00:00–01:00', title: 'Command center', detail: 'Start with the hiring funnel, pending approvals, and current assurance status.', path: '/' },
  { time: '01:00–02:00', title: 'Case and criteria', detail: 'Open a case and explain how job-related criteria are weighted and confirmed.', path: '/cases' },
  { time: '02:00–03:00', title: 'Evidence review', detail: 'Show sourced quotes, page locations, hidden text, and detector findings.', path: '/cases' },
  { time: '03:00–04:00', title: 'Human approval', detail: 'Review the exact payload and hash; edit it to demonstrate approval binding.', path: '/approvals' },
  { time: '04:00–05:00', title: 'Trust and assurance', detail: 'Verify the ledger chain and review SENTINEL scenario outcomes.', path: '/ledger' },
]
function Logo() { return <Link to="/" className="logo" aria-label="Vouch home"><svg viewBox="0 0 36 36" aria-hidden="true"><path d="M9 10l9 17 9-17M14 14l4 7 4-7"/></svg><span>vouch<span className="logo-period">.</span></span></Link> }
function Count({value}:{value:number}) {
  const reduce = useReducedMotion(); const [shown,setShown] = useState(value); const previous = useRef(value)
  useEffect(() => {
    if (reduce) { previous.current = value; return }
    const from = previous.current; const start = performance.now(); let frame = 0
    const step = (now:number) => { const progress=Math.min((now-start)/350,1); setShown(Math.round(from+(value-from)*(1-Math.pow(1-progress,3)))); if(progress<1) frame=requestAnimationFrame(step) }
    frame=requestAnimationFrame(step); previous.current=value; return () => cancelAnimationFrame(frame)
  },[value,reduce])
  return <span aria-label={String(value)}>{reduce ? value : shown}</span>
}
function sparklinePoints(values:number[]) {
  const maximum=Math.max(1,...values)
  return values.map((value,index)=>`${values.length===1?50:index/(values.length-1)*100},${22-value/maximum*18}`).join(' ')
}
function greeting(date = new Date()) {
  const hour = date.getHours()
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}
function dashboardDate(date = new Date()) {
  return new Intl.DateTimeFormat(undefined, { weekday:'long', month:'long', day:'numeric' }).format(date)
}
function Login({onLogin,showDemo}:{onLogin:(session:Session)=>void;showDemo:boolean}) {
  const [busy,setBusy]=useState(false); const [error,setError]=useState(''); const [email,setEmail]=useState('')
  async function signIn(email:string,password:string) {
    setBusy(true);setError('')
    try { onLogin(await api<Session>('/auth/login',undefined,{method:'POST',body:JSON.stringify({email,password})})) }
    catch(e) {setError(e instanceof Error ? e.message : 'Sign-in failed. Try again.')}
    finally {setBusy(false)}
  }
  return <div className="login-page"><header><Logo/><span className="muted">Secure hiring workspace</span></header><main className="login-layout"><section className="login-intro"><ShieldCheck size={48}/><h1>Every decision.<br/>A reason to trust it.</h1><p>Bring the evidence, approvals, and safeguards behind your hiring decisions into one clear view.</p><div className="login-principles"><span><Check/><span>Evidence you can trace</span></span><span><Check/><span>People in control</span></span><span><Check/><span>Approval before action</span></span></div><p className="honest-note">Nobody is rejected automatically.</p></section><section className="login-panel"><h2>Welcome to Vouch</h2><p className="muted">Sign in to your command center.</p><form onSubmit={e=>{e.preventDefault();const data=new FormData(e.currentTarget);void signIn(email,String(data.get('password')))}}><label>Email<input name="email" type="email" autoComplete="username" required placeholder="you@company.com" value={email} onChange={event=>setEmail(event.target.value)}/></label><label>Password<input name="password" type="password" autoComplete="current-password" required placeholder="Your password"/></label>{error&&<div role="alert" className="error-box">{error}</div>}<Button disabled={busy} type="submit" className="primary-action">{busy?'Signing in…':'Sign in'}<ArrowRight/></Button></form>{showDemo&&<div className="demo-accounts"><h3>Demo accounts</h3><p>Select an account and enter the password configured for this demo.</p><div>{[['recruiter@vouch.demo','Recruiter'],['manager@vouch.demo','Hiring manager'],['auditor@vouch.demo','Auditor'],['admin@vouch.demo','HR admin']].map(([value,label])=><Button key={value} variant="outline" disabled={busy} onClick={()=>setEmail(value)}>{label}<ArrowRight size={16}/></Button>)}</div></div>}<p className="honest-note">Use synthetic CVs for the demo.</p></section></main></div>
}
function Loading() {return <div className="dashboard-loading" aria-label="Loading dashboard" role="status"><div className="skeleton skeleton-title"/><div className="skeleton-kpis">{[0,1,2,3].map(i=><div key={i} className="skeleton"/>)}</div><div className="skeleton skeleton-chart"/><span className="muted">Reading your workspace…</span></div>}
function Empty({title,children}:{title:string;children:React.ReactNode}) { return <div className="empty-message"><CircleCheck size={24}/><strong>{title}</strong><p>{children}</p></div> }
function ApprovalClock({expires}:{expires:string}) {
  const [now,setNow]=useState(Date.now())
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[])
  const seconds=Math.max(0,Math.floor((Date.parse(expires)-now)/1000))
  return <span className={seconds ? 'countdown' : 'countdown danger'}><Clock3 size={14}/>{seconds?`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} left`:'Approval expired'}</span>
}
function Dashboard({data,session,caseId}:{data:Overview;session:Session;caseId:string}) {
  const [verifying,setVerifying]=useState(false); const [verification,setVerification]=useState('')
  const metrics=[
    {label:'CVs analysed',value:data.kpis.cvs_analysed,icon:Users,note:'Evidence ready for review',tone:'',trend:data.activity_trends.cvs_analysed,to:caseId?`/cases/${caseId}?tab=candidates`:'/cases'},
    {label:'Security findings',value:data.kpis.security_alerts,icon:ShieldCheck,note:'Signals for a human review',tone:'teal',trend:data.activity_trends.security_alerts,to:caseId?`/cases/${caseId}?tab=evidence`:'/cases'},
    {label:'Pending approvals',value:data.kpis.pending_approval,icon:Clock3,note:'Pending, changed or expired',tone:'amber',trend:data.activity_trends.approval_activity,to:'/approvals'},
    {label:'Outbox entries',value:data.kpis.gateway_sent,icon:Send,note:'Recorded after gateway execution',tone:'',trend:data.activity_trends.gateway_sent,to:caseId?`/cases/${caseId}?tab=outbox`:'/cases'},
  ]
  const stagePath=(stage:string)=>caseId?`/cases/${caseId}?tab=${stage==='Shortlisted'?'ranking':stage==='Sent'?'outbox':stage==='Drafted'||stage==='Approved'?'actions':'candidates'}`:'/cases'
  async function verify() {setVerifying(true);try {const result=await api<{ok:boolean;events:number;first_bad_seq?:number}>('/ledger/verify',session.token);const text=result.ok?`Chain intact · ${result.events} events checked`:`Chain broken at event ${result.first_bad_seq}`;setVerification(text);if(result.ok)toast.success(text);else toast.error(text)}catch(e){toast.error(e instanceof Error?e.message:'Verification failed')}finally{setVerifying(false)}}
  function attentionLink(item:Attention) { return item.kind==='approval'?'/approvals':`/cases/${item.case_id}?tab=${item.kind==='shortlist'?'ranking':'scorecard'}` }
  const assurance=data.assurance; const total=assurance.total??0; const passes=assurance.pass??0
  const highAlerts=(data.alerts_by_severity.high??0)+(data.alerts_by_severity.critical??0)
  const maxPipeline=Math.max(1,...data.pipeline.map(stage=>stage.count))
  const approvalAttention=data.attention.some(item=>item.kind==='approval')
  const caseAttention=data.attention.find(item=>item.case_id)
  const attentionDestination=approvalAttention?'/approvals':caseAttention?attentionLink(caseAttention):'/ledger'
  const attentionAction=approvalAttention?'Open approval workspace':caseAttention?'Review this case':'Open trust ledger'
  return <>
    <div className="metric-grid">{metrics.map(({label,value,icon:Icon,note,tone,trend,to})=><Link className={`metric metric-link ${tone}`} to={to} key={label}><div className="metric-label">{label}<Icon size={19}/></div><div className="metric-value"><Count value={value}/></div><p>{note}</p><div className="metric-trend"><svg viewBox="0 0 100 24" role="img" aria-label={`${label} daily activity for the past seven days`}><polyline className="sparkline-line" points={sparklinePoints(trend)}/></svg><span>7-day activity</span></div><span className="metric-open">Open details<ArrowRight size={14}/></span></Link>)}</div>
    <div className="summary-line"><span><BriefcaseBusiness/><strong>{data.kpis.cases}</strong> accessible cases</span><span><ShieldX/><strong>{data.kpis.gateway_refusals}</strong> gateway refusals</span><span><Link2/><strong>{data.kpis.ledger_events}</strong> ledger events</span><span className="summary-end"><span className="status-dot"/>Data refreshed {timeLabel(data.generated_at)}</span></div>
    <div className="dashboard-grid">
      <section className="surface pipeline-panel"><div className="panel-heading"><div><h2>From CV to conversation</h2><p>Every stage, with human decisions in between.</p></div><Badge variant="outline">Hiring pipeline</Badge></div>
        <div className="pipeline-funnel" role="list" aria-label="Hiring pipeline counts">{data.pipeline.map(stage=><Link className="pipeline-stage" role="listitem" to={stagePath(stage.stage)} key={stage.stage}><div><span>{stage.stage}</span><strong>{stage.count}</strong></div><progress className="pipeline-progress" max={maxPipeline} value={stage.count} aria-label={`${stage.stage}: ${stage.count} ${stage.unit}`}/><small>{stage.unit}</small></Link>)}</div>
        <div className="panel-footnote"><Fingerprint size={16}/>Stages count CVs, candidates, and actions as labelled. Nobody is rejected automatically.</div>
      </section>
      <section className="surface attention-panel"><div className="panel-heading"><div><h2>Needs your attention</h2><p>Your next decisions, in one place.</p></div><span className="number-badge">{data.attention_total}</span></div>
        <div className="attention-list">{data.attention.length?data.attention.slice(0,4).map(item=>item.kind==='verify'?<div key={item.id} className="attention-item"><span className="attention-icon"><Link2/></span><div><strong>Check the trust ledger</strong><p>Verify the full chain of recorded events.</p>{verification&&<p role="status">{verification}</p>}<Button variant="outline" disabled={verifying} onClick={()=>void verify()}>{verifying?'Verifying chain…':'Verify chain'}<ShieldCheck size={16}/></Button></div></div>:<Link className="attention-item" to={attentionLink(item)} key={item.id}><span className="attention-icon"><FileCheck2/></span><div><strong>{item.title}</strong><p dir="auto">{item.case_title}</p>{item.expires_at&&<ApprovalClock expires={item.expires_at}/>}</div><ChevronRight size={17}/></Link>):<Empty title="You’re up to date">New decisions will appear here as your team reviews candidates.</Empty>}</div>
        <Link className="panel-link" to={attentionDestination}>{attentionAction}<ArrowRight size={17}/></Link>
      </section>
      <section className="surface shield-panel"><div className="panel-heading"><div><h2>The evidence shield</h2><p>Suspicious content, brought into view.</p></div><ShieldCheck className="teal-text" size={24}/></div>
        {data.alerts_by_type.length?<><div className="shield-total"><strong>{data.kpis.security_alerts}</strong><span>findings caught<br/><small>{highAlerts} high or critical severity</small></span></div><div className="alert-list">{data.alerts_by_type.slice(0,4).map(alert=><div key={alert.type}><span className={`severity-mark ${alert.max_severity}`}/><span>{humanize(alert.type)}</span><strong>{alert.count}</strong><Badge variant="outline" className={`severity ${alert.max_severity}`}>{alert.max_severity}</Badge></div>)}</div></>:<Empty title="No security findings yet">Upload CVs to inspect hidden text, injection phrases, and other review signals.</Empty>}
        <Link className="panel-link" to={caseId?`/cases/${caseId}?tab=evidence`:'/cases'}>Inspect candidate evidence<ArrowRight size={17}/></Link>
      </section>
      <section className="surface activity-panel"><div className="panel-heading"><div><h2>A trail you can follow</h2><p>Recent activity from your accessible cases.</p></div><Link className="text-link" to={caseId?`/ledger?case_id=${caseId}`:'/ledger'}>View ledger<ArrowRight size={16}/></Link></div><ol className="activity-list">{data.recent_events.slice(0,5).map(event=><li key={event.seq}><span className={`event-icon ${event.type==='EXECUTION_DENIED'?'danger':''}`}>{event.type==='EXECUTION_DENIED'?<ShieldX size={17}/>:<Check size={17}/>}</span><div><strong>{humanize(event.type)}</strong><p><span dir="auto">{event.actor_name}</span><span className="activity-role">{roleName(event.actor_role)}</span></p></div><time dateTime={event.ts} title={new Date(event.ts).toLocaleString()}>{timeLabel(event.ts)}</time></li>)}</ol>{!data.recent_events.length&&<Empty title="Your activity will appear here">Create a case to begin a traceable hiring workflow.</Empty>}</section>
      <section className="surface assurance-panel"><div className="panel-heading"><div><h2>Tested under pressure</h2><p>Vouch Assurance · powered by SENTINEL</p></div><ShieldCheck size={23}/></div>{assurance.available?<><div className="assurance-result"><svg viewBox="0 0 128 128" role="img" aria-label={`${passes} of ${total} scenarios passed`}><circle cx="64" cy="64" r="53" className="gauge-track"/><circle cx="64" cy="64" r="53" className="gauge-value" strokeDasharray={`${total?passes/total*333:0} 333`} transform="rotate(-90 64 64)"/><path d="M47 64l11 11 24-25" className="gauge-check"/></svg><div><strong>{passes}<span> / {total}</span></strong><p>scenarios passed</p><Badge variant="outline" className={(assurance.fail??0)>0?'danger':'success'}>{(assurance.fail??0)>0?`${assurance.fail} failures`:'No failures in this run'}</Badge></div></div><div className="assurance-meta"><span>Test model <code>{assurance.model_mode}</code></span><span>Last run <time>{assurance.generated_at?new Date(assurance.generated_at).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'Unavailable'}</time></span></div></>:<Empty title="No test report yet">Run SENTINEL in the Assurance workspace to see real results.</Empty>}<p className="test-disclaimer">Results describe self-authored synthetic tests only.</p><Link className="panel-link" to="/assurance">Explore the test results<ArrowRight size={17}/></Link></section>
    </div><footer className="dashboard-footer"><span><ShieldCheck size={16}/>The agent executes. The human decides.</span><span>Evidence is sourced from candidate claims, never independently verified.</span></footer>
  </>
}
export default function App() {
  const [session,setSession]=useState<Session|null>(readSession)
  const client=useQueryClient()
  const location=useLocation()
  const navigate=useNavigate()
  const [caseId,setCaseId]=useState('')
  const [commandOpen,setCommandOpen]=useState(false)
  const [mobileNav,setMobileNav]=useState(false)
  const [presenterMode,setPresenterMode]=useState(false)
  const [demoStep,setDemoStep]=useState(0)
  const [theme,setTheme]=useState<'dark'|'light'>(()=>{try{return localStorage.getItem('vouch-theme')==='dark'?'dark':'light'}catch{return 'light'}})
  useEffect(()=>{document.documentElement.classList.toggle('dark',theme==='dark');document.documentElement.dataset.theme=theme;try{localStorage.setItem('vouch-theme',theme)}catch{/* Theme remains usable without storage. */}},[theme])
  useEffect(()=>{const handler=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setCommandOpen(open=>!open)}};document.addEventListener('keydown',handler);return()=>document.removeEventListener('keydown',handler)},[])
  const meta=useQuery({queryKey:['meta'],queryFn:()=>api<Meta>('/meta'),refetchInterval:30_000})
  const identity=useQuery({queryKey:['identity',session?.token],queryFn:()=>api<User>('/auth/me',session!.token),enabled:!!session,retry:false})
  const home=location.pathname==='/'
  const overview=useQuery({queryKey:['overview',session?.user.id,caseId],queryFn:({signal})=>api<Overview>('/dashboard/overview'+(caseId?'?case_id='+encodeURIComponent(caseId):''),session!.token,{signal}),enabled:!!session&&!!identity.data&&home,refetchInterval:15_000,retry:(count,error)=>!(error instanceof ApiError&&[401,403,404].includes(error.status))&&count<1})
  const allCases=useQuery({queryKey:['overview-cases',session?.user.id],queryFn:({signal})=>api<Overview>('/dashboard/overview',session!.token,{signal}),enabled:!!session&&!!identity.data&&home&&!!caseId,refetchInterval:30_000})
  function authenticate(value:Session|null){client.clear();setCaseId('');setSession(value);if(value)sessionStorage.setItem('vouch',JSON.stringify(value));else sessionStorage.removeItem('vouch')}
  const sessionExpired=identity.error instanceof ApiError&&identity.error.status===401
  if(!session||sessionExpired) return <><Login onLogin={authenticate} showDemo={meta.data?.demo_mode===true}/><Toaster theme={theme}/></>
  if(identity.isPending) return <><Loading/><Toaster theme={theme}/></>
  const activeSession=session
  const currentUser=identity.data??activeSession.user
  const visibleNav=NAV.filter(item=>!item.role||item.role===currentUser.role)
  const cases=(caseId?allCases.data:overview.data)?.cases??[]
  const pending=overview.data?.kpis.pending_approval
  const currentItem=visibleNav.find(item=>item.path==='/'?location.pathname==='/':location.pathname.startsWith(item.path))
  const currentPage=currentItem?.label??'Workspace'
  const currentSection=currentItem?.section??'Workspace'
  const appProps={session:{...activeSession,user:currentUser}}
  async function verifyFromPalette(){
    try {const result=await api<{ok:boolean;events:number;first_bad_seq?:number}>('/ledger/verify',activeSession.token);if(result.ok)toast.success(`Chain intact · ${result.events} events`);else toast.error(`Chain failure at sequence ${result.first_bad_seq}`)}
    catch(error){toast.error(error instanceof Error?error.message:'Ledger verification failed.')}
  }
  async function startAssurance(){
    try {await api('/assurance/run',activeSession.token,{method:'POST',body:'{}'});toast.success('SENTINEL is running against an isolated instance.')}
    catch(error){toast.error(error instanceof Error?error.message:'SENTINEL could not be started.')}
  }
  return <div className={`app-shell ${presenterMode?'presenter-mode':''}`}><Link className="skip-link" to="#main">Skip to main content</Link>
    <aside className={`sidebar ${mobileNav?'mobile-open':''}`}>
      <div className="sidebar-brand"><Logo/><Button variant="ghost" size="icon" className="mobile-close" aria-label="Close navigation" onClick={()=>setMobileNav(false)}><X/></Button></div>
      <div className="sidebar-tagline">Secure hiring workspace</div>
      <nav aria-label="Main navigation">{['Workspace','Governance','Administration'].map(section=>{
        const items=visibleNav.filter(item=>item.section===section)
        return items.length>0&&<div className="nav-group" key={section}><span className="nav-section-label">{section}</span>{items.map(({label,icon:Icon,path})=><NavLink key={label} to={path} end={path==='/'} onClick={()=>setMobileNav(false)}
          className={({isActive})=>`nav-link ${isActive?'active':''}`}><Icon size={19}/><span>{label}</span>{path==='/approvals'&&pending!==undefined&&pending>0&&<span className="nav-count">{pending}</span>}<ArrowRight className="nav-arrow" size={13}/></NavLink>)}</div>
      })}</nav>
      <div className="sidebar-bottom">
        <div className="sidebar-user"><span className="avatar">{currentUser.name.slice(0,1)}</span><div><strong>{currentUser.name.split(' (')[0]}</strong><span>{roleName(currentUser.role)}</span></div><Button variant="ghost" size="icon" aria-label="Sign out" onClick={()=>authenticate(null)}><LogOut size={18}/></Button></div>
      </div>
    </aside>
    <div className="main-shell">
      <header className="app-header"><Button variant="ghost" size="icon" className="mobile-menu" aria-label="Open navigation" onClick={()=>setMobileNav(true)}><Menu/></Button>
        <div className="breadcrumb"><span>{currentSection}</span>{currentItem&&<><ChevronRight size={15}/><strong>{currentPage}</strong></>}</div>
        <div className="header-actions"><Button variant="ghost" className="presenter-toggle" aria-pressed={presenterMode} onClick={()=>{setPresenterMode(value=>!value);setDemoStep(0)}}><Presentation size={17}/>{presenterMode?'Exit presenter':'Presenter mode'}</Button><Button variant="ghost" className="search-trigger" aria-label="Open command palette" onClick={()=>setCommandOpen(true)}><Search size={17}/><span>Search anything</span><kbd>Ctrl K</kbd></Button>
          <Button variant="ghost" size="icon" aria-label={`Switch to ${theme==='dark'?'light':'dark'} theme`} onClick={()=>setTheme(theme==='dark'?'light':'dark')}>{theme==='dark'?<Sun size={19}/>:<Moon size={19}/>}</Button>
        </div>
      </header>
      <main id="main" className="dashboard-content">
        {presenterMode&&<section className="presenter-guide" aria-label="Five minute demo script">
          <progress className="presenter-progress" value={demoStep+1} max={DEMO_SCRIPT.length} aria-label={`Demo step ${demoStep+1} of ${DEMO_SCRIPT.length}`}/>
          <div className="presenter-guide-content"><span className="presenter-time">{DEMO_SCRIPT[demoStep].time}</span><div><strong>{demoStep+1}. {DEMO_SCRIPT[demoStep].title}</strong><p>{DEMO_SCRIPT[demoStep].detail}</p></div>
            <div className="page-actions"><Button variant="outline" disabled={demoStep===0} onClick={()=>setDemoStep(index=>Math.max(0,index-1))}>Previous</Button><Button variant="outline" onClick={()=>navigate(DEMO_SCRIPT[demoStep].path)}>Open step</Button><Button disabled={demoStep===DEMO_SCRIPT.length-1} onClick={()=>setDemoStep(index=>Math.min(DEMO_SCRIPT.length-1,index+1))}>Next</Button></div>
          </div>
        </section>}
        {home ? <><div className="page-title overview-hero"><div className="overview-welcome"><span className="overview-date">{dashboardDate()}</span><h1>{greeting()}, {currentUser.name.split(' (')[0].split(' ')[0]}.</h1><p>Here’s your hiring overview. People stay in control of every decision.</p></div><div className="page-actions">
          <label className="case-selector"><span className="sr-only">Filter dashboard by case</span><select aria-label="Filter dashboard by case" value={caseId} onChange={event=>setCaseId(event.target.value)}><option value="">All accessible cases</option>{cases.map(item=><option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
          <Button variant="outline" size="icon" aria-label="Refresh dashboard" disabled={overview.isFetching} onClick={()=>void overview.refetch()}><RefreshCw size={18} className={overview.isFetching?'animate-spin':''}/></Button>
        </div></div><div className="system-status" aria-label="Live system configuration">{meta.data?<><span><span className="status-dot"/>Model <strong>{meta.data.model_mode}</strong></span><span><Send size={14}/>Delivery <strong>{meta.data.n8n_delivery?'Configured':'Sandbox only'}</strong></span><span><Clock3 size={14}/>Approval window <strong>{meta.data.approval_minutes} min</strong></span></>:<span>Configuration {meta.isError?'unavailable':'loading…'}</span>}<span className="read-only-note"><Fingerprint size={14}/>Human approval required</span></div>
          {identity.isError||overview.isError?<section className="error-box" role="alert"><AlertTriangle/><h2>We couldn’t load your workspace.</h2><p>{(identity.error??overview.error)?.message}</p><Button onClick={()=>{void identity.refetch();void overview.refetch()}}>Try again</Button></section>:overview.data?<Dashboard data={overview.data} session={appProps.session} caseId={caseId}/>:<Loading/>}
        </> : <Routes>
          <Route path="/cases" element={<CasesPage {...appProps}/>}/>
          <Route path="/candidates" element={<CandidatesPage {...appProps}/>}/>
          <Route path="/inbox" element={<InboxPage {...appProps}/>}/>
          <Route path="/cases/:caseId" element={<CaseWorkspace {...appProps}/>}/>
          <Route path="/approvals" element={<ApprovalsPage {...appProps}/>}/>
          <Route path="/interviews" element={<InterviewsPage {...appProps}/>}/>
          <Route path="/follow-ups" element={<FollowUpsPage {...appProps}/>}/>
          <Route path="/ledger" element={<LedgerPage {...appProps}/>}/>
          <Route path="/assurance" element={<AssurancePage {...appProps}/>}/>
          <Route path="/admin" element={<AdminPage {...appProps}/>}/>
          <Route path="/settings" element={<Navigate to="/admin" replace/>}/>
          <Route path="*" element={<Navigate to="/" replace/>}/>
        </Routes>}
      </main>
    </div>
    <CommandDialog open={commandOpen} onOpenChange={setCommandOpen} title="Go to workspace" description="Search for a workspace or action.">
      <CommandInput placeholder="Where would you like to go?"/><CommandList><CommandEmpty>No matching destination.</CommandEmpty><CommandGroup heading="Workspace">
        {visibleNav.map(({label,icon:Icon,path})=><CommandItem key={label} onSelect={()=>{setCommandOpen(false);navigate(path)}}><Icon size={18}/>{label}</CommandItem>)}
        <CommandItem onSelect={()=>{setTheme(theme==='dark'?'light':'dark');setCommandOpen(false)}}><Sun/>Toggle theme</CommandItem>
        <CommandItem onSelect={()=>{setCommandOpen(false);void client.invalidateQueries()}}><RefreshCw/>Refresh current view</CommandItem>
        {(currentUser.role==='auditor'||currentUser.role==='hr_admin')&&<><CommandItem onSelect={()=>{setCommandOpen(false);void verifyFromPalette()}}><ShieldCheck/>Verify ledger chain</CommandItem><CommandItem onSelect={()=>{setCommandOpen(false);void startAssurance()}}><ShieldCheck/>Run SENTINEL</CommandItem></>}
      </CommandGroup></CommandList>
    </CommandDialog>
    <Toaster theme={theme}/>
  </div>
}
