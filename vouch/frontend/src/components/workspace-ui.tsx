import type { ReactNode } from 'react'
import { AlertTriangle, ArrowRight, FileSearch, Fingerprint, LoaderCircle } from 'lucide-react'
import { Button } from './ui/button'
import { Badge } from './ui/badge'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog'
import { ApiError, humanize } from '@/lib/api'

export function Notice({children,tone='neutral'}:{children:ReactNode;tone?:string}){return <div className={`workspace-notice ${tone}`}>{children}</div>}
export function Failure({error,retry}:{error:Error|null;retry?:()=>void}){return error?<div className="workspace-error" role="alert"><AlertTriangle/><div><strong>{error instanceof ApiError?humanize(error.code):'Something needs attention'}</strong><p>{error.message}</p>{retry&&<Button variant="outline" onClick={retry}>Try again</Button>}</div></div>:null}
export function Busy({label='Reading your workspace…'}:{label?:string}){return <div className="workspace-loading" role="status"><LoaderCircle className="animate-spin"/><span>{label}</span><div className="skeleton"/></div>}
export function EmptyState({title,children,action}:{title:string;children:ReactNode;action?:ReactNode}){return <div className="workspace-empty"><span className="empty-symbol"><FileSearch size={32}/></span><h2>{title}</h2><p>{children}</p>{action}</div>}
export function Status({value,tone='neutral'}:{value:string;tone?:string}){return <Badge variant="outline" className={`status-chip ${tone}`}>{humanize(value)}</Badge>}
export function Hash({value,label='SHA-256'}:{value:string;label?:string}){return <div className="hash-block"><span><Fingerprint size={14}/>{label}</span><code title={value}>{value}</code></div>}
export function Drawer({open,onClose,title,description,children,wide=false}:{open:boolean;onClose:()=>void;title:string;description:string;children:ReactNode;wide?:boolean}){return <Dialog open={open} onOpenChange={value=>{if(!value)onClose()}}><DialogContent className={`workspace-drawer ${wide?'wide':''}`}><DialogHeader><DialogTitle dir="auto">{title}</DialogTitle><DialogDescription>{description}</DialogDescription></DialogHeader>{children}</DialogContent></Dialog>}
export function NextStep({label,onClick}:{label:string;onClick:()=>void}){return <Button onClick={onClick}>{label}<ArrowRight size={17}/></Button>}
