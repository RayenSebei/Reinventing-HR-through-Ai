import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { api, type Session } from './api'

export type Criterion = {id?:string;label:string;kind:string;weight:number;aliases:string[]}
export type HiringCase = {id:string;title:string;description:string;status:string;created_at:string;criteria:Criterion[];criteria_confirmed:boolean;can_edit:boolean;members:{id:string;name:string;role:string}[]}
export type Candidate = {id:string;pseudonym:string;display_name:string;document_id:string;filename:string;finding_types:string[]}
export type Box = {x0:number;x1:number;top:number;bottom:number}
export type Evidence = {criterion_id:string;criterion:string;kind:string;weight:number;status:string;quote:string|null;page:number|null;source:string;note:string;boxes:Box[]}
export type Finding = {type:string;severity:string;page:number|null;excerpt:string;boxes:Box[]}
export type Dossier = {candidate_id:string;case_id:string;pseudonym:string;document:{id:string;sha256:string;pages:number;filename:string}|null;evidence:Evidence[];findings:Finding[];statement:string}
export type Extraction = {document_id:string;sha256:string;visible_text:string;hidden_text:string;pages:{number:number;width:number;height:number}[]}
export type RankRow = {candidate_id:string;pseudonym:string;position:number;score:number;breakdown:{criterion:string;weight:number;status:string}[];flags:string[];justification:string}
export type Ranking = {case_id:string;version:number|null;status:string|null;rows:RankRow[];statement?:string}
export type Payload = {case_id:string;candidate_id:string;kind:string;recipient:string;start:string|null;duration_minutes:number;subject:string;body:string}
export type Proposal = {id:string;case_id:string;candidate_id:string;kind:string;payload:Payload;payload_sha256:string;created_by:string;status:string;created_at:string;updated_at:string;approval:null|{id:string;decision:string;approver_id:string;approved_hash:string;expires_at:string;used_at:string|null;matches_current_payload:boolean}}
export type LedgerEvent = {seq:number;ts:string;actor:string;type:string;case_id:string|null;subject:string|null;hash:string;body:Record<string,unknown>}
export type Outbox = {id:string;proposal_id:string;payload:Payload;delivery_status:string;delivery_detail:string;created_at:string}
export type View = ''|'criteria'|'candidates'|'shortlist'|'actions'|'ledger'|'assurance'
export type WorkspaceProps = {session:Session;caseId:string;navigate:(view:View,caseId?:string)=>void}
export function route() {
  const params = new URLSearchParams(window.location.hash.slice(1))
  const raw=params.get('view')??''
  const view:View=['criteria','candidates','shortlist','actions','ledger','assurance'].includes(raw)?raw as View:''
  return {view,caseId:params.get('case')??''}
}
export function workspaceUrl(view:string,caseId='') {const p=new URLSearchParams();if(view)p.set('view',view);if(caseId)p.set('case',caseId);return '#'+p.toString()}
export function useResource<T>(path:string,session:Session,enabled=true,interval?:number) {
  return useQuery({queryKey:['workspace',session.user.id,path],queryFn:({signal})=>api<T>(path,session.token,{signal}),enabled,retry:false,refetchInterval:interval})
}
export async function allPages<T>(path:string,token:string,signal?:AbortSignal):Promise<T[]> {
  const rows:T[]=[]
  for(let offset=0;;offset+=100){const page=await api<T[]>(`${path}?limit=100&offset=${offset}`,token,{signal});rows.push(...page);if(page.length<100)return rows}
}
export function useCandidates(caseId:string,session:Session){return useQuery({queryKey:['workspace',session.user.id,'candidates',caseId],queryFn:({signal})=>allPages<Candidate>(`/cases/${caseId}/candidates`,session.token,signal),enabled:!!caseId,retry:false})}
export function useAction(session:Session) {
  const client=useQueryClient();const [busy,setBusy]=useState(false);const [error,setError]=useState<Error|null>(null)
  async function run<T>(path:string,method='POST',body:unknown={},message?:string):Promise<T|undefined>{
    setBusy(true);setError(null)
    try {const result=await api<T>(path,session.token,{method,body:body instanceof FormData?body:JSON.stringify(body)});await client.invalidateQueries();if(message)toast.success(message);return result}
    catch(e){const failure=e instanceof Error?e:new Error('Request failed');setError(failure);toast.error(failure.message);await client.invalidateQueries();return undefined}
    finally{setBusy(false)}
  }
  return {busy,error,run,clearError:()=>setError(null)}
}
export const evidenceTone=(status:string)=>status==='SOURCED'?'success':status==='NEEDS_REVIEW'?'warning':'neutral'
export function proposalState(p:Proposal,now=Date.now()) {
  if(p.status==='EXECUTED')return 'Sent'
  const a=p.approval
  if(a?.decision==='rejected')return 'Rejected'
  if(!a)return 'Drafted'
  if(a.used_at)return 'Used'
  if(!a.matches_current_payload)return 'Changed'
  if(Date.parse(a.expires_at)<=now)return 'Expired'
  return 'Approved'
}
