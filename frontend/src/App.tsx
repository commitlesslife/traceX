import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import './Graph.css'
import './Polish.css'
import MoneyMovementGlobe from './components/MoneyMovementGlobe'
import TransactionGraph from './components/TransactionGraph'

type User = { id: string; username: string; role: string; display_name: string }
type CaseRow = { case_id: string; complaint_id: string; status: string; disposition: string; created_at: string; victim_account: string; disputed_transaction_ref: string; disputed_amount: string; reported_time: string; match_status: string; latest_trace_id?: string | null }
type TraceNode = { account_id: string; pseudonymous_key: string; institution_id: string; is_operating_institution: boolean; traced_in: string; traced_out: string; unmoved_traced_value: string; available_balance?: string | null; balance_status: string; freezable_estimate?: string | null; confidence: string; min_hop: number; is_terminal: boolean; termination_reason?: string | null; evidence_ids: string[] }
type TraceEdge = { transaction_id: string; source_account: string; destination_account: string; timestamp_utc: string; raw_amount: string; attributed_amount: string; fraction: string; confidence: string; hop: number; channel: string; is_terminal: boolean; evidence_id: string }
type Trace = { trace_id: string; case_id: string; seed_transaction_id: string; seed_amount: string; victim_account: string; nodes: TraceNode[]; edges: TraceEdge[]; boundaries: {boundary_account:string;institution_name:string;crossed_amount:string;last_transaction_id:string;timestamp_utc:string;reason:string}[]; total_unmoved_value: string; crossed_boundary_value: string; is_synthetic: boolean; complete: boolean; result_hash: string }
type Tx = Record<string, unknown> & { transaction_id?: string; amount?: string; timestamp_utc?: string; channel?: string; status?: string; source_account?: string; destination_account?: string }
type Rec = { id: string; case_id: string; trace_id: string; total_recommended_amount: string; status: string; justification: string; author_id: string; selected_accounts: { account_id: string; amount: number; basis: string }[]; decided_by_id?: string; decision_reason?: string; decided_at?: string; document_hash?: string }

const api = async <T,>(path: string, token?: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(`/api/v1${path}`, { ...init, headers: { ...(init?.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) } })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`)
  return r.json()
}
const money = (v?: string | number) => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(Number(v || 0))
const short = (v?: string) => v ? `${v.slice(0,7)}…${v.slice(-4)}` : '—'
const time = (v?: string) => v ? new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(v) ? v : `${v}Z`).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'}) : 'Time not supplied'
const confidenceLabel = (value: string) => { const percent = Number(value) * 100; return percent > 0 && percent < 1 ? '<1% confidence' : `${Math.round(percent)}% confidence` }
const initials = (v?: string) => (v || 'TX').split(/[ _-]/).map(x=>x[0]).join('').slice(0,2).toUpperCase()

function Login({ onLogin }: { onLogin: (u:string,p:string)=>Promise<void> }) {
  const [username,setUsername]=useState('analyst_priya'),[password,setPassword]=useState('analyst123'),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const submit=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{await onLogin(username,password)}catch(err){setError(err instanceof Error?err.message:'Sign-in failed')}finally{setBusy(false)}}
  return <main className="login-shell"><div className="login-brand"><div className="brand-mark"><NavIcon name="investigation"/></div><span>TRACE<span className="brand-x">X</span></span></div><section className="login-card"><div className="eyebrow"><i className="live-dot"/> INVESTIGATION WORKSPACE</div><h1>Welcome back<span>.</span></h1><p className="login-intro">Sign in to review reported fraud and trace transaction evidence.</p><form onSubmit={submit}><label>Username<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username"/></label><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></label>{error&&<p className="form-error">{error}</p>}<button className="button primary full" disabled={busy}>{busy?'Signing in…':'Sign in securely'}</button></form><div className="login-foot">◈ Demo environment · synthetic records</div></section><aside className="login-aside"><div className="aside-grid">{Array.from({length:9},(_,i)=><i key={i}/>)}</div><span>FOLLOW THE EVIDENCE</span><p>Trace the movement.<br/>See where the trail ends.</p></aside></main>
}

function TraceAttribution({ trace, transactionId }: { trace: Trace | null; transactionId: string }) {
  const edge = trace?.edges.find(item => item.transaction_id === transactionId)
  if (!edge) return null
  return <div className="drawer-attribution"><div><span>ATTRIBUTED TO REPORTED PAYMENT</span><b>{money(edge.attributed_amount)}</b></div><p>The ledger amount above is the full transfer. This share follows the disputed payment through the trace.</p></div>
}

function NavIcon({ name }: { name: 'overview' | 'cases' | 'investigation' }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'overview' ? <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></> :
     name === 'cases' ? <><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></> :
     <><circle cx="5" cy="12" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="18" cy="19" r="2"/><path d="m7 11 9-5M7 13l9 5"/></>}
  </svg>
}

function MetricIcon({ index }: { index: number }) {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {index === 0 ? <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></> : index === 1 ? <><path d="M3 12h4l2-4 4 8 2-4h6"/></> : index === 2 ? <><path d="M4 17h16M6 14l4-4 3 2 5-6"/><path d="M15 6h3v3"/></> : <><path d="M12 2 4 6v6c0 5 3.4 8.2 8 10 4.6-1.8 8-5 8-10V6Z"/><path d="m9 12 2 2 4-4"/></>}
  </svg>
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('tracex-token') || '')
  const [user, setUser] = useState<User | null>(null)
  const [cases, setCases] = useState<CaseRow[]>([])
  const [selected, setSelected] = useState<CaseRow | null>(null)
  const [trace, setTrace] = useState<Trace | null>(null)
  const [screen, setScreen] = useState<'overview' | 'cases' | 'investigation'>('overview')
  const [graphMode, setGraphMode] = useState<'network' | 'globe'>('network')
  const [playing, setPlaying] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [selectedTx, setSelectedTx] = useState<Tx | null>(null)

  // Recommendation & Approval State
  const [recommendations, setRecommendations] = useState<Rec[]>([])
  const [showDraftModal, setShowDraftModal] = useState(false)
  const [showReviewModal, setShowReviewModal] = useState<Rec | null>(null)
  const [targetAccount, setTargetAccount] = useState('')
  const [draftAmount, setDraftAmount] = useState('')
  const [justification, setJustification] = useState('Victim funds retained after downstream dispersion.')
  const [reviewReason, setReviewReason] = useState('Verified attribution fractions and ledger timestamps. Approved.')

  const load = async (t: string) => {
    const [me, c] = await Promise.all([api<User>('/auth/me', t), api<{ cases: CaseRow[] }>('/cases', t)])
    setUser(me)
    setCases(c.cases)
    if (c.cases[0]) {
      setSelected(c.cases[0])
      if (c.cases[0].latest_trace_id) {
        const tr = await api<Trace>(`/traces/${c.cases[0].latest_trace_id}`, t)
        setTrace(tr)
      }
    }
    loadRecs(t)
  }

  const loadRecs = async (t: string) => {
    try {
      const r = await api<{ recommendations: Rec[] }>('/recommendations?status_filter=', t)
      setRecommendations(r.recommendations)
    } catch {
      // Ignore background refresh failure
    }
  }

  useEffect(() => {
    if (token) load(token).catch(e => { localStorage.removeItem('tracex-token'); setToken(''); setError(e.message) })
  }, [])

  const signIn = async (username: string, password: string) => {
    const form = new URLSearchParams({ username, password })
    const result = await api<{ access_token: string }>('/auth/login', undefined, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: form })
    localStorage.setItem('tracex-token', result.access_token)
    setToken(result.access_token)
    await load(result.access_token)
  }

  const switchRole = async (targetRole: 'analyst' | 'supervisor') => {
    const creds = targetRole === 'analyst' ? { u: 'analyst_priya', p: 'analyst123' } : { u: 'supervisor_rajesh', p: 'supervisor123' }
    setError('')
    try {
      await signIn(creds.u, creds.p)
      setNotice(`Switched active user to ${creds.u} (${targetRole})`)
      setTimeout(() => setNotice(''), 3500)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Switch failed')
    }
  }

  const run = async (c: CaseRow) => {
    setBusy(true); setError(''); setSelected(c); setScreen('investigation')
    try {
      const tr = await api<Trace>(`/complaints/${c.complaint_id}/traces`, token, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ max_hops: 8, horizon_hours: 72, min_amount: '1000.00' }) })
      setTrace(tr)
      loadRecs(token)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Trace failed')
    } finally {
      setBusy(false)
    }
  }

  const inspect = async (id: string) => {
    try {
      setSelectedTx(await api<Tx>(`/transactions/${encodeURIComponent(id)}`, token))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Transaction details unavailable')
    }
  }

  const logout = () => {
    localStorage.removeItem('tracex-token')
    setToken('')
    setUser(null)
    setTrace(null)
  }

  // Recommendation Drafting Handler
  const openDraft = () => {
    if (!trace || !selected) {
      setError('Run a trace first before drafting a freeze recommendation.')
      return
    }
    // Pick the first operating account with unmoved funds
    const candidate = trace.nodes.find(n => n.is_operating_institution && Number(n.unmoved_traced_value) > 0 && n.account_id !== trace.victim_account)
    if (candidate) {
      setTargetAccount(candidate.account_id)
      const maxAllowed = candidate.balance_status === 'known' && candidate.freezable_estimate ? candidate.freezable_estimate : candidate.unmoved_traced_value
      setDraftAmount(String(maxAllowed))
    }
    setShowDraftModal(true)
  }

  const submitDraft = async (e: FormEvent) => {
    e.preventDefault()
    if (!selected || !trace) return
    setError('')
    try {
      const res = await api<{ recommendation_id: string }>(`/cases/${selected.case_id}/recommendations`, token, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trace_id: trace.trace_id,
          selected_accounts: [{ account_id: targetAccount, amount: parseFloat(draftAmount), basis: 'unmoved_traced_value' }],
          justification,
        }),
      })
      setShowDraftModal(false)
      setNotice(`Recommendation drafted successfully: ${res.recommendation_id}`)
      setTimeout(() => setNotice(''), 4500)
      loadRecs(token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Draft submission failed')
    }
  }

  // Supervisor Independent Decision Handler
  const decideRecommendation = async (recId: string, decision: 'approved' | 'rejected') => {
    setError('')
    try {
      const res = await api<{ document_hash?: string; decided_by: string; status: string }>(`/recommendations/${recId}/decision`, token, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reason: reviewReason }),
      })
      setShowReviewModal(null)
      setNotice(`Recommendation ${decision.toUpperCase()} by ${res.decided_by}! Hash: ${res.document_hash?.slice(0, 14)}…`)
      setTimeout(() => setNotice(''), 5500)
      loadRecs(token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review action failed')
    }
  }

  // JSON Export Handler with Content Hash
  const exportCasePack = async () => {
    if (!selected) return
    setError('')
    try {
      const data = await api<{ export_metadata: { content_hash: string } }>(`/cases/${selected.case_id}/exports`, token, {
        method: 'POST',
      })
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selected.case_id}-EXPORT-${data.export_metadata.content_hash.slice(0, 8)}.json`
      a.click()
      setNotice(`Export generated with verified SHA-256 hash!`)
      setTimeout(() => setNotice(''), 4000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    }
  }

  if (!token || !user) return <Login onLogin={signIn} />

  const shown = cases.filter(c => `${c.case_id} ${c.victim_account} ${c.disputed_transaction_ref}`.toLowerCase().includes(query.toLowerCase()))
  const seedEdge: TraceEdge | null = trace ? { transaction_id: trace.seed_transaction_id, source_account: trace.victim_account, destination_account: trace.nodes.find(node => node.min_hop === 1)?.account_id || '', timestamp_utc: '', raw_amount: trace.seed_amount, attributed_amount: trace.seed_amount, fraction: '1', confidence: '1', hop: 0, channel: 'REPORTED', is_terminal: false, evidence_id: '' } : null
  const caseRecs = selected ? recommendations.filter(r => r.case_id === selected.case_id) : []

  const SideNav = () => (
    <aside className="sidebar">
      <div className="brand-lockup">
        <div className="brand-mark"><NavIcon name="investigation"/></div>
        <div>
          <div className="brand-name">TRACE<span>X</span></div>
          <div className="brand-caption">FRAUD INVESTIGATION</div>
        </div>
      </div>
      <div className="sidebar-divider"/>
      <div className="nav-group">
        <div className="nav-heading">WORKSPACE</div>
        {(['overview','cases','investigation'] as const).map(v => (
          <button key={v} onClick={() => setScreen(v)} className={`nav-item ${screen === v ? 'active' : ''}`}>
            <span className="nav-icon"><NavIcon name={v}/></span>
            {v === 'overview' ? 'Overview' : v === 'cases' ? 'Case queue' : 'Investigation'}
            {v === 'cases' && <span className="nav-count">{cases.length}</span>}
          </button>
        ))}
      </div>
      <div className="sidebar-spacer"/>
      <div className="demo-badge">
        <i className="live-dot"/>
        <div><b>Demo environment</b><span>Ledger fixture · synthetic data</span></div>
      </div>
      <button className="user-menu" onClick={logout}>
        <span className="avatar">{initials(user.display_name)}</span>
        <span className="user-meta"><b>{user.display_name}</b><span>{user.role} · Sign out</span></span>
      </button>
    </aside>
  )

  const selectCase = (c: CaseRow) => { setSelected(c); setTrace(null); setScreen('investigation') }

  return (
    <div className="app-shell">
      <SideNav/>
      <main className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <span>TRACE-X</span><span>›</span>
            <b>{screen === 'overview' ? 'Overview' : screen === 'cases' ? 'Case queue' : 'Investigation'}</b>
          </div>
          <div className="top-actions">
            {/* Quick 1-click Role Switcher for 2-person rule demo */}
            <div className="role-switcher-group" title="Quickly switch roles for two-person review demonstration">
              <span className="switcher-label">DEMO ACTOR:</span>
              <button
                type="button"
                className={`switcher-pill ${user.role === 'analyst' ? 'active-pill' : ''}`}
                onClick={() => void switchRole('analyst')}
              >
                Priya (Analyst)
              </button>
              <button
                type="button"
                className={`switcher-pill ${user.role === 'supervisor' ? 'active-pill' : ''}`}
                onClick={() => void switchRole('supervisor')}
              >
                Rajesh (Supervisor)
              </button>
            </div>
            <span className="environment-tag"><i className="live-dot"/>LOCAL DEMO</span>
            <span className="top-avatar" title={`${user.display_name} (${user.role})`}>{initials(user.display_name)}</span>
          </div>
        </header>

        <section className="page-content">
          {error && <div className="form-error" role="alert">{error}<button onClick={() => setError('')}> ×</button></div>}
          {notice && <div className="form-notice" role="status"><span>✓</span> {notice}</div>}

          {screen === 'overview' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">OPERATIONS <span>/</span> OVERVIEW</div>
                  <h1>Fraud response overview</h1>
                  <p>Review reported payment trails and move from intake to evidence.</p>
                </div>
                <button className="button primary" onClick={() => setScreen('cases')}>Open case queue →</button>
              </div>
              <div className="metrics-grid">
                {[
                  { t: 'Open cases', v: cases.length, d: 'Reported and awaiting review' },
                  { t: 'Trace ready', v: cases.filter(c => c.latest_trace_id).length, d: 'Cases with saved ledger traces' },
                  { t: 'Selected exposure', v: trace ? money(trace.seed_amount) : '—', d: 'Reported amount in current case' },
                  { t: 'Visible recovery', v: trace ? money(trace.total_unmoved_value) : '—', d: 'Value remaining in visible accounts' }
                ].map((m, i) => (
                  <article className="metric-card" key={m.t}>
                    <div className={`metric-icon tone-${['blue','amber','green','violet'][i]}`}><MetricIcon index={i}/></div>
                    <div className="metric-title">{m.t}</div>
                    <div className="metric-value">{m.v}</div>
                    <div className="metric-detail">{m.d}</div>
                  </article>
                ))}
              </div>
              <section className="surface queue-surface">
                <div className="section-heading">
                  <div>
                    <div className="eyebrow">PRIORITY QUEUE</div>
                    <h2>Reported cases</h2>
                    <p>Open a case to review the complaint and start a ledger trace.</p>
                  </div>
                  <button className="text-button" onClick={() => setScreen('cases')}>View all →</button>
                </div>
                <CaseTable rows={cases.slice(0, 5)} onSelect={selectCase} onTrace={run}/>
              </section>
            </>
          )}

          {screen === 'cases' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">WORKSPACE <span>/</span> CASES</div>
                  <h1>Case queue</h1>
                  <p>Reported payment complaints ready for investigation.</p>
                </div>
                <label className="search-box">
                  <span>⌕</span>
                  <input placeholder="Search cases or accounts" value={query} onChange={e => setQuery(e.target.value)}/>
                </label>
              </div>
              <section className="surface queue-surface">
                <CaseTable rows={shown} onSelect={selectCase} onTrace={run}/>
              </section>
            </>
          )}

          {screen === 'investigation' && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">CASEWORK <span>/</span> INVESTIGATION</div>
                  <h1>{selected?.case_id || 'Investigation'}</h1>
                  <p>Follow ledger-supported movements, draft freeze recommendations, and request independent review.</p>
                </div>
                <div className="account-table-actions">
                  <button className="button secondary" onClick={() => setScreen('cases')}>← Case queue</button>
                  {selected && <button className="button primary" onClick={() => void run(selected)} disabled={busy}>{busy ? 'Tracing…' : 'Run ledger trace'}</button>}
                  {trace && <button className="button subtle action-highlight" onClick={openDraft}>✍ Draft recommendation</button>}
                  {selected && <button className="button subtle" onClick={exportCasePack} title="Export verified JSON case bundle with SHA-256 hash">⬇ Export pack</button>}
                </div>
              </div>

              {selected && (
                <div className="context-strip">
                  <div className="context-item">
                    <span>REPORTED SOURCE</span>
                    <b>{short(selected.victim_account)}</b>
                    <small>{selected.victim_account}</small>
                  </div>
                  <div className="context-divider"/>
                  <div className="context-item">
                    <span>DISPUTED PAYMENT</span>
                    <b>{money(selected.disputed_amount)}</b>
                    <small>{selected.disputed_transaction_ref}</small>
                  </div>
                  <div className="context-divider"/>
                  <div className="context-item">
                    <span>INTAKE CHANNEL</span>
                    <b>{selected.match_status === 'matched' ? 'Ledger reference matched' : 'Reference unresolved'}</b>
                    <small>{selected.complaint_id}</small>
                  </div>
                  <div className="context-divider"/>
                  <div className="context-item">
                    <span>TRACE STATUS</span>
                    <b className={trace ? 'text-green' : 'text-muted'}>{trace ? 'Trace available' : 'Awaiting trace'}</b>
                    <small>{trace?.trace_id || 'Run trace to load evidence'}</small>
                  </div>
                </div>
              )}

              {/* Recommendations & Approval Panel (if any exist for this case) */}
              {caseRecs.length > 0 && (
                <section className="surface recommendation-surface">
                  <div className="section-heading compact">
                    <div>
                      <div className="eyebrow">CASE RECOMMENDATIONS &amp; APPROVALS</div>
                      <h2>Independent Review Workflow</h2>
                    </div>
                  </div>
                  <div className="rec-cards-grid">
                    {caseRecs.map(rec => (
                      <div key={rec.id} className={`rec-card-box status-${rec.status}`}>
                        <div className="rec-card-header">
                          <span className="rec-id-tag">{rec.id}</span>
                          <span className={`status-pill ${rec.status === 'approved' ? 'status-green' : rec.status === 'rejected' ? 'status-red' : 'status-amber'}`}>
                            <i className="live-dot"/>{rec.status.toUpperCase()}
                          </span>
                        </div>
                        <div className="rec-card-body">
                          <div><strong>Recommended Total:</strong> {money(rec.total_recommended_amount)}</div>
                          <div><strong>Author:</strong> <span className="mono">{rec.author_id}</span></div>
                          <div className="rec-justification">"{rec.justification}"</div>
                          {rec.document_hash && (
                            <div className="rec-doc-hash">
                              <span>✓ Verified Document Hash:</span>
                              <code>{rec.document_hash.slice(0, 20)}…</code>
                            </div>
                          )}
                        </div>
                        <div className="rec-card-actions">
                          {rec.status === 'draft' && (
                            <button className="button small primary" onClick={() => setShowReviewModal(rec)}>
                              Review &amp; Decide →
                            </button>
                          )}
                          {rec.status === 'approved' && (
                            <span className="approved-badge">Approved for legal case pack</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="surface graph-surface">
                <div className="section-heading graph-heading">
                  <div>
                    <div className="eyebrow">TRANSACTION NETWORK</div>
                    <h2>Movement of funds</h2>
                    <p>{graphMode === 'globe' ? 'India faces forward. Drag to rotate and select a route to inspect its transaction.' : 'Source flows left to right. Click a link or account to inspect its transaction record.'}</p>
                  </div>
                  <div className="graph-header-tools">
                    <button className={`graph-control-mode ${graphMode === 'network' ? 'chosen' : ''}`} onClick={() => setGraphMode('network')}>Network</button>
                    <button className={`graph-control-mode ${graphMode === 'globe' ? 'chosen' : ''}`} onClick={() => setGraphMode('globe')}>Globe</button>
                    {graphMode === 'network' && (
                      <button className="graph-control" aria-label={playing ? 'Pause network movement' : 'Play network movement'} onClick={() => setPlaying(!playing)}>
                        {playing ? 'Ⅱ' : '▶'}
                      </button>
                    )}
                  </div>
                </div>
                {trace ? (
                  graphMode === 'network' ? (
                    <TransactionGraph trace={trace} playing={playing} onInspect={inspect}/>
                  ) : (
                    <>
                      <MoneyMovementGlobe trace={trace} playing={playing} onTogglePlaying={() => setPlaying(v => !v)} onInspect={inspect}/>
                      <button className="graph-control-mode globe-network-return" onClick={() => setGraphMode('network')}>← Network</button>
                    </>
                  )
                ) : (
                  <div className="graph-empty">
                    <h3>{busy ? 'Building the transaction trail…' : 'No trace loaded'}</h3>
                    <p>Select a case and run the trace to draw its linked transaction evidence.</p>
                  </div>
                )}
              </section>

              {trace && (
                <section className="surface timeline-surface">
                  <div className="section-heading">
                    <div>
                      <div className="eyebrow">TRANSFER SEQUENCE</div>
                      <h2>Hop timeline</h2>
                      <p>Transfers are grouped by ledger hop. Select a transfer to inspect its record.</p>
                    </div>
                    <div className="timeline-summary">
                      <span>{trace.edges.length} traced movements</span>
                      <b>{money(trace.seed_amount)} reported</b>
                    </div>
                  </div>
                  <div className="timeline-scroll">
                    <div className="timeline-board">
                      {Array.from({ length: Math.max(1, ...trace.edges.map(e => e.hop + 1)) }, (_, hop) => (
                        <div className="hop-column" key={hop}>
                          <div className="hop-head">
                            <span>{hop === 0 ? 'REPORTED' : `HOP ${hop}`}</span>
                            <i/>
                          </div>
                          <div className="hop-cards">
                            {(hop === 0 ? (seedEdge ? [seedEdge] : []) : trace.edges.filter(e => e.hop === hop)).map(e => (
                              <button className={`hop-card ${e.is_terminal ? 'hop-boundary' : ''}`} key={e.transaction_id} onClick={() => void inspect(e.transaction_id)}>
                                <span className="hop-card-top">
                                  {e.channel}
                                  <span className="confidence">{hop === 0 ? 'Reported payment' : confidenceLabel(e.confidence)}</span>
                                </span>
                                <b>{money(e.attributed_amount)}</b>
                                <span className="hop-account-pair">{short(e.source_account)} → {short(e.destination_account)}</span>
                                <small>{time(e.timestamp_utc)}</small>
                                {e.is_terminal && <em>Last visible movement · institution boundary</em>}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>
              )}
            </>
          )}
        </section>
      </main>

      {/* Transaction Inspection Drawer */}
      {selectedTx && (
        <div className="transaction-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setSelectedTx(null) }}>
          <section className="transaction-drawer" role="dialog" aria-modal="true" aria-label="Transaction details">
            <div className="drawer-header">
              <div>
                <div className="eyebrow">TRANSACTION EVIDENCE</div>
                <h2>{String(selectedTx.transaction_id || 'Transaction')}</h2>
              </div>
              <button className="icon-button" onClick={() => setSelectedTx(null)}>×</button>
            </div>
            <div className="drawer-amount">
              <span>LEDGER TRANSACTION AMOUNT</span>
              <b>{money(String(selectedTx.amount || '0'))}</b>
              <small>{String(selectedTx.status || 'Recorded')} · {String(selectedTx.channel || 'Transfer')}</small>
            </div>
            <TraceAttribution trace={trace} transactionId={String(selectedTx.transaction_id || '')}/>
            <div className="drawer-fields">
              <div><span>TIME</span><b>{time(String(selectedTx.timestamp_utc || ''))}</b></div>
              <div><span>CHANNEL</span><b>{String(selectedTx.channel || '—')}</b></div>
              <div><span>FROM ACCOUNT</span><b className="mono">{String(selectedTx.source_key || selectedTx.source_account_id || '—')}</b></div>
              <div><span>TO ACCOUNT</span><b className="mono">{String(selectedTx.destination_key || selectedTx.destination_account_id || '—')}</b></div>
              <div><span>STATUS</span><b>{String(selectedTx.status || '—')}</b></div>
              <div><span>DATASET</span><b>{String(selectedTx.dataset_id || '—')}</b></div>
            </div>
          </section>
        </div>
      )}

      {/* Draft Recommendation Modal */}
      {showDraftModal && trace && (
        <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setShowDraftModal(false) }}>
          <div className="modal-card">
            <div className="modal-head">
              <div>
                <div className="eyebrow">ANALYST ACTION</div>
                <h2>Draft Freeze Recommendation</h2>
              </div>
              <button className="icon-button" onClick={() => setShowDraftModal(false)}>×</button>
            </div>
            <p className="modal-copy">Select an in-scope account holding victim funds. Recommended amount is strictly validated against the upper-bound freezable estimate.</p>
            <form onSubmit={submitDraft}>
              <label>
                Target Account
                <select value={targetAccount} onChange={e => {
                  setTargetAccount(e.target.value)
                  const n = trace.nodes.find(node => node.account_id === e.target.value)
                  if (n) setDraftAmount(String(n.freezable_estimate || n.unmoved_traced_value))
                }}>
                  {trace.nodes.filter(n => n.is_operating_institution && Number(n.unmoved_traced_value) > 0 && n.account_id !== trace.victim_account).map(n => (
                    <option key={n.account_id} value={n.account_id}>
                      {n.account_id} ({n.pseudonymous_key}) — Max {money(n.freezable_estimate || n.unmoved_traced_value)} ({n.balance_status === 'known' ? 'Balance Known' : 'Balance Unknown'})
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Recommended Amount (₹)
                <input type="number" step="0.01" value={draftAmount} onChange={e => setDraftAmount(e.target.value)} required/>
              </label>

              <label>
                Investigator Justification
                <textarea rows={3} value={justification} onChange={e => setJustification(e.target.value)} required/>
              </label>

              <div className="modal-caution">
                <i className="live-dot"/>
                <span>Drafting creates a proposal only. Enforces two-person review rule before generating exportable legal document.</span>
              </div>

              <div className="modal-actions">
                <button type="button" className="button secondary" onClick={() => setShowDraftModal(false)}>Cancel</button>
                <button type="submit" className="button primary">Submit Draft for Review</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Supervisor Review Modal */}
      {showReviewModal && (
        <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setShowReviewModal(null) }}>
          <div className="modal-card">
            <div className="modal-head">
              <div>
                <div className="eyebrow">INDEPENDENT SUPERVISOR REVIEW</div>
                <h2>Review Recommendation {showReviewModal.id}</h2>
              </div>
              <button className="icon-button" onClick={() => setShowReviewModal(null)}>×</button>
            </div>
            <div className="decision-summary">
              <span>PROPOSED RESTRICTION</span>
              <b>{money(showReviewModal.total_recommended_amount)}</b>
              <small>Author: {showReviewModal.author_id} &bull; Case: {showReviewModal.case_id}</small>
            </div>
            <p className="modal-copy"><strong>Analyst Justification:</strong> "{showReviewModal.justification}"</p>

            <label>
              Supervisor Written Reason (Required for Audit Trail)
              <input type="text" value={reviewReason} onChange={e => setReviewReason(e.target.value)} required/>
            </label>

            <div className="modal-caution">
              <i className="live-dot"/>
              <span>Separation of duty: The author cannot approve this draft. Approval generates a verifiable case document with zero automatic banking calls.</span>
            </div>

            <div className="modal-actions split-actions">
              <button type="button" className="button danger" onClick={() => void decideRecommendation(showReviewModal.id, 'rejected')}>
                Reject Draft
              </button>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button type="button" className="button secondary" onClick={() => setShowReviewModal(null)}>Cancel</button>
                <button type="button" className="button primary" onClick={() => void decideRecommendation(showReviewModal.id, 'approved')}>
                  ✓ Approve Document
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const scenarioMeta: Record<string, { label: string; tone: string }> = {
  'CASE-2026-0891': { label: 'Pooled inflow · compact', tone: 'teal' },
  'CASE-2026-0888': { label: 'Six-hop branching', tone: 'blue' },
  'CASE-2026-0877': { label: 'Eight-hop ladder', tone: 'violet' },
  'CASE-2026-0866': { label: 'Two boundaries · seven hops', tone: 'coral' },
}

function CaseTable({ rows, onSelect, onTrace }: { rows: CaseRow[]; onSelect: (c: CaseRow) => void; onTrace: (c: CaseRow) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>CASE</th>
            <th>REPORTED ACCOUNT</th>
            <th>DISPUTED AMOUNT</th>
            <th>STATUS</th>
            <th>REPORTED</th>
            <th>ACTION</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(c => (
            <tr className="click-row" key={c.case_id} onClick={() => onSelect(c)}>
              <td>
                <b>{c.case_id}</b>
                <span className={`case-scenario scenario-${scenarioMeta[c.case_id]?.tone ?? 'teal'}`}>
                  {scenarioMeta[c.case_id]?.label ?? c.complaint_id}
                </span>
              </td>
              <td><b>{short(c.victim_account)}</b><span>{c.disputed_transaction_ref}</span></td>
              <td className="money-cell">{money(c.disputed_amount)}</td>
              <td><span className="status-pill"><i className="live-dot"/>{c.status}</span></td>
              <td>{time(c.reported_time)}</td>
              <td>
                <button className="button subtle" onClick={e => { e.stopPropagation(); void onTrace(c) }}>
                  {c.latest_trace_id ? 'Open trace' : 'Investigate'} →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="empty-state">No reported cases match that search.</p>}
    </div>
  )
}
