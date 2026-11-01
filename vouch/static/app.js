// Vouch screens. Plain JS, no build step. All CV-derived text is inserted with
// textContent (never innerHTML), so a CV can't inject markup into the page.
"use strict";

const S = { token: null, user: null, users: [], cases: [], caseId: null, case: null, tab: "criteria",
            candidates: [], dossier: null, page: 1, viewed: new Set(), ranking: null };

// ---------- helpers ----------
const $ = (id) => document.getElementById(id);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return n;
}
const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };
const short = (h) => (h ? h.slice(0, 10) + "…" : "");
const isRole = (...r) => S.user && r.includes(S.user.role);
const PANELS = {
  criteria: ["STEP 01 / SET THE STANDARD", "Define what matters.", "A shared scorecard keeps every review focused and consistent."],
  candidates: ["STEP 02 / LOOK AT THE EVIDENCE", "Meet your candidates.", "Review each CV alongside the exact evidence behind its assessment."],
  shortlist: ["STEP 03 / MAKE A CONSIDERED CHOICE", "Build your shortlist.", "Compare the evidence, open the dossiers, and make the final call."],
  actions: ["STEP 04 / START THE CONVERSATION", "Turn a shortlist into a conversation.", "Draft an invitation. Your hiring manager approves the exact message before it can be sent."],
  ledger: ["TRANSPARENCY / EVERY STEP RECORDED", "A clear trail of decisions.", "See who did what and when, with a tamper-evident record for this role."],
  assurance: ["ASSURANCE / TEST THE GUARDRAILS", "Confidence you can inspect.", "Run the 24 synthetic attack scenarios against an isolated test instance."],
};
function emptyState(title, description) {
  return el("div", { class: "empty-state" }, el("strong", { text: title }), el("p", { text: description }));
}
async function refreshOverview() {
  const id = S.caseId;
  const [candidates, ranking, outbox] = await Promise.all([
    api("GET", `/cases/${id}/candidates`), api("GET", `/cases/${id}/ranking`), api("GET", `/cases/${id}/outbox`)
  ]);
  if (id !== S.caseId) return;
  $("candidateCount").textContent = candidates.length;
  $("criteriaCount").textContent = S.case.criteria.length;
  $("shortlistOverview").textContent = ranking.status === "CONFIRMED" ? "Confirmed" : ranking.status === "DRAFT" ? "In review" : "Not started";
  $("sentCount").textContent = outbox.length;
  const next = $("nextStep");
  const target = S.tab === "criteria" && S.case.criteria_confirmed ? ["candidates", "Review candidates →"] :
    S.tab === "candidates" && candidates.length ? ["shortlist", "Build shortlist →"] :
    S.tab === "shortlist" && ranking.status === "CONFIRMED" ? ["actions", "Draft invitation →"] : null;
  next.hidden = !target;
  if (target) { next.dataset.target = target[0]; next.textContent = target[1]; }
}

const MESSAGES = {
  APPROVAL_PAYLOAD_MISMATCH: "Blocked by the Action Gateway: the action changed after the manager approved it.",
  APPROVAL_REPLAY: "Blocked: this approval was already used. Each approval works once.",
  APPROVAL_EXPIRED: "Blocked: the approval expired. Ask the manager to approve again.",
  NO_VALID_APPROVAL: "Blocked: no manager approval exists for this action.",
  SELF_APPROVAL: "Blocked: you can't approve your own proposal.",
  FORBIDDEN_ROLE: "Not allowed for your role.",
};

async function api(method, path, body, isForm) {
  const opts = { method, headers: {} };
  if (S.token) opts.headers.Authorization = "Bearer " + S.token;
  if (isForm) opts.body = body;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch("/api" + path, opts);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) {
    const e = (data && data.error) || { code: "HTTP_" + r.status, message: r.statusText };
    const err = new Error(MESSAGES[e.code] || e.message);
    err.code = e.code; err.status = r.status;
    if (r.status === 401 && path !== "/auth/login") logout();
    throw err;
  }
  return data;
}

function banner(msg, kind = "bad") {
  const b = $("banner");
  if (!msg) { b.hidden = true; return; }
  b.className = "banner " + kind; b.textContent = msg; b.hidden = false;
  if (kind !== "bad") setTimeout(() => { if (b.textContent === msg) b.hidden = true; }, 5000);
}
async function guard(fn) { try { banner(null); await fn(); } catch (e) { banner((e.code ? e.code + " · " : "") + e.message); } }

// ---------- auth ----------
function saveSession() { try { sessionStorage.setItem("vouch", JSON.stringify({ token: S.token, user: S.user })); } catch (_) {} }
function loadSession() { try { const s = JSON.parse(sessionStorage.getItem("vouch") || "null"); if (s) { S.token = s.token; S.user = s.user; } } catch (_) {} }
function logout() { S.token = null; S.user = null; try { sessionStorage.removeItem("vouch"); } catch (_) {} render(); }

async function login(email, password) {
  const r = await api("POST", "/auth/login", { email, password });
  S.token = r.token; S.user = r.user; saveSession(); S.viewed.clear();
  await boot();
}

// ---------- boot / render ----------
async function boot() {
  render();
  if (!S.token) return;
  S.users = await api("GET", "/users");
  await loadCases();
  if (S.caseId && S.cases.some((c) => c.id === S.caseId)) await openCase(S.caseId, S.tab);
  else if (S.cases.length) await openCase(S.cases[0].id, S.tab);
}

function render() {
  const logged = !!S.token;
  $("login").hidden = logged; $("workspace").hidden = !logged; $("who").hidden = !logged;
  if (!logged) return;
  const who = clear($("who"));
  who.append(el("span", { class: "user-avatar", "aria-hidden": "true", text: S.user.name.slice(0, 1) }), el("span", { class: "user-name", text: S.user.name }), el("span", { class: "pill", text: S.user.role.replace(/_/g, " ") }));
  const sw = el("select", { "aria-label": "Switch user", onchange: async (e) => { if (e.target.value) await guard(() => login(e.target.value, "demo1234")); } },
    el("option", { value: "", text: "Switch demo user…" }),
    [["recruiter", "Recruiter"], ["manager", "Hiring manager"], ["auditor", "Auditor"], ["admin", "HR admin"]].map(([m, label]) => el("option", { value: m + "@vouch.demo", text: label })));
  who.append(sw, el("button", { type: "button", onclick: logout, text: "Sign out" }));
  $("newCaseBtn").hidden = !isRole("recruiter");
}

async function loadCases() {
  S.cases = await api("GET", "/cases");
  $("caseCount").textContent = S.cases.length;
  const ul = clear($("caseList"));
  for (const c of S.cases) {
    ul.append(el("li", {}, el("button", { type: "button", "aria-current": c.id === S.caseId ? "true" : null,
      onclick: () => guard(() => openCase(c.id, "criteria")) }, c.title)));
  }
}

async function openCase(id, tab) {
  S.caseId = id; S.case = await api("GET", "/cases/" + id); S.dossier = null;
  $("dossier").hidden = true;
  $("noCase").hidden = true; $("caseView").hidden = false;
  $("caseTitle").textContent = S.case.title; $("caseDesc").textContent = S.case.description;
  document.querySelectorAll("#caseList button").forEach((b) => b.setAttribute("aria-current", b.textContent === S.case.title ? "true" : "false"));
  await showTab(tab || "criteria");
}

async function showTab(tab) {
  S.tab = tab; banner(null);
  document.querySelectorAll(".tabs button").forEach((b) => { b.setAttribute("aria-selected", b.dataset.tab === tab ? "true" : "false"); b.tabIndex = b.dataset.tab === tab ? 0 : -1; });
  document.querySelectorAll("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== tab));
  const [eyebrow, title, description] = PANELS[tab];
  $("panelEyebrow").textContent = eyebrow; $("panelTitle").textContent = title; $("panelDescription").textContent = description;
  if (tab === "actions" && isRole("hiring_manager")) {
    $("panelTitle").textContent = "Give the next step your approval.";
    $("panelDescription").textContent = "Review the recipient, interview time, and exact message. Your approval applies only to that content.";
  }
  await ({ criteria: renderCriteria, candidates: renderCandidates, shortlist: renderShortlist,
           actions: renderActions, ledger: renderLedger, assurance: renderAssurance })[tab]();
  await refreshOverview();
}

// ---------- 1. criteria ----------
function critRow(c = { label: "", kind: "skill", weight: 0 }) {
  const editable = S.case.can_edit;
  const kinds = ["skill", "experience", "education", "project", "certification", "other"];
  const tr = el("tr", {},
    el("td", {}, el("input", { value: c.label, maxlength: 200, disabled: !editable, "aria-label": "Criterion", oninput: sumWeights })),
    el("td", {}, el("select", { disabled: !editable, "aria-label": "Type", onchange: sumWeights }, kinds.map((k) => el("option", { value: k, selected: k === c.kind, text: k })))),
    el("td", {}, el("input", { type: "number", min: 0, max: 100, value: c.weight, disabled: !editable, "aria-label": "Weight", oninput: sumWeights })),
    el("td", {}, editable ? el("button", { type: "button", onclick: () => { tr.remove(); sumWeights(); }, text: "Remove" }) : ""));
  return tr;
}
function sumWeights() {
  const total = [...$("critBody").querySelectorAll("input[type=number]")].reduce((a, i) => a + (+i.value || 0), 0);
  const p = $("weightSum"); p.textContent = "Total weight: " + total + "%"; p.className = "pill " + (total === 100 ? "ok" : "warn");
  $("saveCrit").disabled = total !== 100;
  $("confirmCrit").disabled = total !== 100 || !criteriaMatchSaved();
}
function criteriaMatchSaved() {
  return JSON.stringify(readCriteria()) === JSON.stringify(S.case.criteria.map(({ label, kind, weight }) => ({ label, kind, weight })));
}
async function renderCriteria() {
  const body = clear($("critBody"));
  S.case.criteria.forEach((c) => body.append(critRow(c)));
  if (!S.case.criteria.length && S.case.can_edit) body.append(critRow());
  sumWeights();
  $("critActions").hidden = !S.case.can_edit;
  $("critStatus").textContent = S.case.criteria_confirmed ? "✓ Scorecard confirmed. You’re ready to review candidates." : S.case.can_edit ? "Save your changes, then confirm the scorecard to start reviewing CVs." : "The recruiter needs to confirm this scorecard before candidate review begins.";
  $("critStatus").className = S.case.criteria_confirmed ? "confirmed" : "muted";
}
function readCriteria() {
  return [...$("critBody").querySelectorAll("tr")].map((tr) => {
    const [l, k, w] = tr.querySelectorAll("input,select");
    return { label: l.value.trim(), kind: k.value, weight: +w.value };
  }).filter((c) => c.label);
}

// ---------- 2. candidates & dossier ----------
async function renderCandidates() {
  $("uploadForm").hidden = !S.case.can_edit;
  S.candidates = await api("GET", `/cases/${S.caseId}/candidates`);
  const body = clear($("candBody"));
  if (!S.candidates.length) body.append(el("tr", {}, el("td", { colspan: 3, class: "empty-cell" }, el("strong", { text: "Your candidate list starts here." }), el("p", { text: "Upload a PDF CV above to see its evidence and any review alerts." }))));
  $("uploadForm").querySelector("button[type=submit]").disabled = !S.case.criteria_confirmed;
  if (!S.case.criteria_confirmed) $("uploadStatus").textContent = "Confirm your scorecard in Criteria before uploading.";
  for (const c of S.candidates) {
    const alerts = c.finding_types.filter((t) => t !== "MODEL_FALLBACK");
    body.append(el("tr", { class: "clickable", "data-candidate": c.id, tabindex: 0, "aria-selected": S.dossier && S.dossier.candidate_id === c.id ? "true" : "false",
      onclick: () => guard(() => openDossier(c.id)), onkeydown: (e) => { if (e.key === "Enter") guard(() => openDossier(c.id)); } },
      el("td", {}, el("b", { text: c.pseudonym }), el("div", { class: "muted small", text: c.display_name })),
      el("td", { class: "small", text: c.filename || "" }),
      el("td", {}, alerts.length ? alerts.map((t) => el("span", { class: "chip high", text: t.replace(/_/g, " ").toLowerCase() })) : el("span", { class: "chip SOURCED", text: "no alerts" }))));
  }
  if (S.dossier) await drawDossier();
}

async function openDossier(id) {
  S.dossier = await api("GET", `/candidates/${id}/dossier`); S.page = 1; S.viewed.add(id);
  document.querySelectorAll("#candBody tr").forEach((tr) => tr.setAttribute("aria-selected", tr.dataset.candidate === id ? "true" : "false"));
  await drawDossier();
}

async function drawDossier() {
  const d = S.dossier; $("dossier").hidden = false;
  $("dosTitle").textContent = d.pseudonym; $("dosSha").textContent = d.document ? "sha256 " + short(d.document.sha256) : "";
  $("dosStatement").textContent = d.statement;
  const ev = clear($("evList"));
  for (const e of d.evidence) {
    ev.append(el("li", {}, el("span", { class: "chip " + e.status, text: e.status.replace("_", " ") }),
      el("b", { text: e.criterion }), el("span", { class: "muted small", text: ` · weight ${e.weight} · ${e.source}` + (e.page ? ` · page ${e.page}` : "") }),
      e.quote ? el("q", { text: e.quote }) : null, e.note ? el("div", { class: "muted small", text: e.note }) : null));
  }
  const fd = clear($("fdList"));
  if (!d.findings.length) fd.append(el("li", { class: "muted", text: "No alerts on this document." }));
  for (const f of d.findings) {
    fd.append(el("li", {}, el("span", { class: "chip " + f.severity, text: f.type.replace(/_/g, " ") }),
      f.page ? el("span", { class: "muted small", text: "page " + f.page + " · " }) : null, el("span", { text: f.excerpt })));
  }
  await drawPage();
}

async function drawPage() {
  const d = S.dossier; if (!d.document) return;
  const n = d.document.pages; S.page = Math.min(Math.max(1, S.page), n);
  $("pageNo").textContent = `Page ${S.page} of ${n}`; $("prevPage").disabled = S.page <= 1; $("nextPage").disabled = S.page >= n;
  const [blob, ext] = await Promise.all([api("GET", `/documents/${d.document.id}/pages/${S.page}.png`), api("GET", `/documents/${d.document.id}/extraction`)]);
  const img = $("pageImg"); const old = img.src; img.src = URL.createObjectURL(blob); if (old.startsWith("blob:")) URL.revokeObjectURL(old);
  const pg = ext.pages.find((p) => p.number === S.page);
  const ov = clear($("overlay"));
  const place = (b, cls) => {   // CSSOM styles (allowed by the page's CSP), not style attributes
    const n = el("div", { class: "box " + cls });
    n.style.left = (b.x0 / pg.width) * 100 + "%"; n.style.top = (b.top / pg.height) * 100 + "%";
    n.style.width = ((b.x1 - b.x0) / pg.width) * 100 + "%"; n.style.height = ((b.bottom - b.top) / pg.height) * 100 + "%";
    ov.append(n);
  };
  d.evidence.filter((e) => e.page === S.page).forEach((e) => e.boxes.forEach((b) => place(b, "ev")));
  d.findings.filter((f) => f.page === S.page).forEach((f) => f.boxes.forEach((b) => place(b, "hid")));
}

// ---------- 3. shortlist ----------
async function renderShortlist() {
  S.ranking = await api("GET", `/cases/${S.caseId}/ranking`);
  $("draftRank").hidden = !S.case.can_edit; $("confirmRank").hidden = !S.case.can_edit;
  const st = $("rankState");
  st.textContent = S.ranking.status ? `Version ${S.ranking.version} · ${S.ranking.status.toLowerCase()}` : "No ranking yet";
  st.className = "pill " + (S.ranking.status === "CONFIRMED" ? "ok" : S.ranking.status ? "warn" : "");
  const body = clear($("rankBody"));
  if (!S.ranking.rows.length) body.append(el("tr", {}, el("td", { colspan: 6, class: "empty-cell" }, el("strong", { text: "A thoughtful shortlist starts with evidence." }), el("p", { text: "Add candidate CVs, then rank them against your scorecard." }))));
  for (const r of S.ranking.rows) {
    body.append(el("tr", {},
      el("td", { text: r.position }), el("td", {}, el("button", { type: "button", class: "dossier-link", text: r.pseudonym + " ↗", "aria-label": "Review dossier for " + r.pseudonym, onclick: () => guard(async () => { await showTab("candidates"); await openDossier(r.candidate_id); $("dossier").scrollIntoView({ block: "start" }); }) }), S.viewed.has(r.candidate_id) ? el("div", { class: "muted small", text: "Dossier reviewed" }) : null),
      el("td", { class: "mono", text: r.score }),
      el("td", {}, r.breakdown.map((b) => el("div", { class: "small" }, el("span", { class: "chip " + b.status, text: b.status.replace("_", " ") }), `${b.criterion} (${b.weight})`))),
      el("td", {}, r.flags.map((f) => el("span", { class: "chip medium", text: f.replace(/_/g, " ").toLowerCase() }))),
      el("td", { class: "small", text: r.justification })));
  }
  // Against automation bias: the recruiter must open the top dossiers before confirming.
  const top = S.ranking.rows.slice(0, 3).map((r) => r.candidate_id);
  const missing = top.filter((id) => !S.viewed.has(id));
  const btn = $("confirmRank");
  btn.disabled = !(S.ranking.status === "DRAFT") || missing.length > 0;
  $("confirmHint").textContent = S.ranking.status !== "DRAFT" ? "" :
    missing.length ? `Review the top ${top.length} candidate dossiers before confirming (${missing.length} left in Candidates).` : "All top dossiers reviewed. Ready to confirm.";
}

// ---------- 4. actions ----------
async function renderActions() {
  const rk = await api("GET", `/cases/${S.caseId}/ranking`);
  const sel = clear($("propCand"));
  const confirmed = rk.status === "CONFIRMED" ? rk.rows : [];
  confirmed.forEach((r) => sel.append(el("option", { value: r.candidate_id, text: `${r.pseudonym} (score ${r.score})` })));
  $("propForm").hidden = !(S.case.can_edit && confirmed.length);
  if (!$("propStart").value) {
    const d = new Date(Date.now() + 3 * 864e5); d.setUTCHours(10, 0, 0, 0);
    $("propStart").value = d.toISOString().slice(0, 16);
  }
  const props = await api("GET", `/cases/${S.caseId}/proposals`);
  const list = clear($("propList"));
  if (!props.length) list.append(emptyState(confirmed.length ? "Your next conversation starts here." : "First, agree on your shortlist.", confirmed.length ? "Choose a candidate above and draft an invitation for your manager to review." : "Review the candidate dossiers and confirm the shortlist. You can then draft invitations here."));
  for (const p of props.slice().reverse()) list.append(propCard(p));
  const out = await api("GET", `/cases/${S.caseId}/outbox`);
  const ol = clear($("outList"));
  if (!out.length) ol.append(el("li", { class: "empty-state" }, el("strong", { text: "No invitations sent yet." }), el("p", { text: "Messages appear here after manager approval and a successful send." })));
  for (const o of out) {
    const retry = (o.delivery_status === "DELIVERY_FAILED" || o.delivery_status === "HELD_OUTBOUND_DISABLED") && S.case.can_edit
      ? el("button", { type: "button", onclick: () => guard(async () => { const r = await api("POST", `/outbox/${o.id}/retry`, {}); banner("Retry: " + r.delivery_status + " (same approved content).", r.delivery_status === "DELIVERED" ? "ok" : "warn"); await renderActions(); }), text: "Retry sending" })
      : null;
    ol.append(el("li", {}, el("b", { text: o.payload.subject }), el("div", { class: "small muted", text: `to ${o.payload.recipient} · ${o.delivery_status} · ${o.created_at}` }), retry));
  }
  $("sentCount").textContent = out.length;
}

function propCard(p) {
  const a = p.approval; const pl = p.payload;
  const stateCls = p.status === "EXECUTED" ? "ok" : p.status === "APPROVED" ? "ok" : p.status === "REJECTED" ? "bad" : "warn";
  const card = el("article", { class: "card prop" },
    el("div", { class: "row between" }, el("b", { text: pl.subject }), el("span", { class: "pill " + stateCls, text: p.status.replace(/_/g, " ").toLowerCase() })),
    el("div", { class: "meta" }, el("span", { text: "to " + pl.recipient }), pl.start ? el("span", { text: "when " + pl.start }) : null,
      el("span", { class: "mono", text: "payload " + short(p.payload_sha256) })),
    el("pre", { text: pl.body }));
  if (a) {
    card.append(el("div", { class: "meta" },
      el("span", { text: `${a.decision} by ${a.approver_id}` }), el("span", { class: "mono", text: "approved " + short(a.approved_hash) }),
      el("span", { text: a.used_at ? "used " + a.used_at : "expires " + a.expires_at }),
      a.matches_current_payload ? el("span", { class: "chip SOURCED", text: "matches current payload" }) : el("span", { class: "chip FAIL", text: "does NOT match current payload" })));
  }
  const btns = el("div", { class: "row" });
  if (p.status !== "EXECUTED") {
    if (isRole("hiring_manager")) {
      btns.append(el("button", { type: "button", class: "primary", onclick: () => guard(async () => { await api("POST", `/proposals/${p.id}/approve`); banner("Approved. The approval is bound to this exact content.", "ok"); await renderActions(); }), text: "Approve this exact content" }),
        el("button", { type: "button", class: "danger", onclick: () => guard(async () => { await api("POST", `/proposals/${p.id}/reject`); await renderActions(); }), text: "Reject" }));
    }
    if (S.case.can_edit && pl.start) {
      btns.append(el("button", { type: "button", onclick: () => guard(async () => {
        const d = new Date(pl.start); d.setUTCHours(d.getUTCHours() + 2);
        await api("PATCH", `/proposals/${p.id}`, { start: d.toISOString().replace(/\.\d{3}Z$/, "Z") });
        banner("Interview time changed by 2 hours. The earlier approval no longer matches this content.", "warn"); await renderActions();
      }), text: "Change time (+2 h)" }));
    }
    if (isRole("recruiter", "hiring_manager")) {
      btns.append(el("button", { type: "button", class: "primary", onclick: () => guard(async () => {
        await api("POST", `/proposals/${p.id}/execute`); banner("Sent through the Action Gateway.", "ok"); await renderActions();
      }), text: "Send through the gateway" }));
    }
  }
  card.append(btns);
  return card;
}

// ---------- ledger ----------
async function renderLedger() {
  $("verifyLedger").hidden = !isRole("auditor", "hr_admin");
  const rows = await api("GET", `/ledger?case_id=${encodeURIComponent(S.caseId)}`);
  const body = clear($("ledgerBody"));
  for (const r of rows) body.append(el("tr", {}, el("td", { text: r.seq }), el("td", { class: "mono", text: r.ts }), el("td", { text: r.actor }),
    el("td", {}, el("b", { text: r.type.replace(/_/g, " ").toLowerCase() })), el("td", { class: "mono", text: short(r.hash) })));
}

// ---------- assurance ----------
let pollTimer = null;
async function renderAssurance() {
  const rep = await api("GET", "/assurance/latest");
  const sum = clear($("assSummary")); const body = clear($("assBody"));
  if (!rep.available) { sum.append(el("p", { class: "muted", text: "No run yet. Press the button to run the attacks." })); return; }
  const t = rep.totals;
  const stat = (label, v) => el("div", { class: "stat" }, el("b", { text: v }), el("span", { class: "muted small", text: label }));
  sum.append(stat("attacks run", `${t.executed}/${t.scenarios}`), stat("blocked (pass)", t.pass), stat("got through (fail)", t.fail),
    stat("could not run", t.blocked + t.error), stat("critical failures", rep.critical_failures.length), stat("last run (UTC)", rep.generated_at.replace("T", " ").replace("Z", "")));
  for (const r of rep.results) body.append(el("tr", {}, el("td", { class: "mono", text: r.id }), el("td", {}, el("span", { class: "chip " + r.severity, text: r.severity })),
    el("td", {}, el("span", { class: "chip " + r.outcome, text: r.outcome })), el("td", { text: r.detection === null || r.detection === undefined ? "" : r.detection ? "yes" : "no" }), el("td", { text: r.name })));
}
async function runAssurance() {
  await api("POST", "/assurance/run", {});
  const st = $("assState"); st.textContent = "Running…"; st.className = "pill warn"; $("runAssurance").disabled = true;
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const s = await api("GET", "/assurance/status");
      if (!s.running) { clearInterval(pollTimer); st.textContent = "Finished"; st.className = "pill ok"; $("runAssurance").disabled = false; if (S.tab === "assurance") await renderAssurance(); }
    } catch (_) { clearInterval(pollTimer); }
  }, 1500);
}

// ---------- wiring ----------
document.addEventListener("DOMContentLoaded", () => {
  // Keep wide evidence tables usable on narrow screens without widening the page.
  document.querySelectorAll("table.grid").forEach((table) => {
    const wrap = el("div", { class: "table-wrap", tabindex: 0, role: "region", "aria-label": table.closest("[data-panel]").dataset.panel + " table" });
    table.before(wrap); wrap.append(table);
  });
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    panel.id = "panel-" + panel.dataset.panel; panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", "tab-" + panel.dataset.panel);
  });
  ["propCand", "propKind", "propStart"].forEach((id) => {
    const input = $(id); const label = document.querySelector(`label[for="${id}"]`);
    const field = el("div", { class: "form-field" }); label.before(field); field.append(label, input);
  });
  $("nextStep").addEventListener("click", () => guard(() => showTab($("nextStep").dataset.target)));
  document.querySelector(".tabs").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    const tabs = [...document.querySelectorAll(".tabs button")]; const current = tabs.indexOf(document.activeElement);
    if (current < 0) return; e.preventDefault();
    const index = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (current + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[index].focus(); guard(() => showTab(tabs[index].dataset.tab));
  });
  $("loginForm").addEventListener("submit", async (e) => {
    e.preventDefault(); const err = $("loginError"); err.hidden = true;
    try { await login($("email").value, $("password").value); } catch (x) { err.textContent = x.message; err.hidden = false; }
  });
  document.querySelectorAll("[data-quick]").forEach((b) => b.addEventListener("click", async () => {
    const err = $("loginError"); err.hidden = true;
    try { await login(b.dataset.quick, "demo1234"); } catch (x) { err.textContent = x.message; err.hidden = false; }
  }));
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => guard(() => showTab(b.dataset.tab))));

  $("newCaseBtn").addEventListener("click", () => {
    const s = clear($("ncManager"));
    S.users.filter((u) => u.role === "hiring_manager").forEach((u) => s.append(el("option", { value: u.id, text: u.name })));
    $("newCaseForm").hidden = false; $("ncTitle").focus();
  });
  $("ncCancel").addEventListener("click", () => ($("newCaseForm").hidden = true));
  $("newCaseForm").addEventListener("submit", (e) => { e.preventDefault(); guard(async () => {
    const c = await api("POST", "/cases", { title: $("ncTitle").value, description: $("ncDesc").value, manager_id: $("ncManager").value || null });
    $("newCaseForm").hidden = true; $("newCaseForm").reset(); await loadCases(); await openCase(c.id, "criteria");
  }); });

  $("addCrit").addEventListener("click", () => { $("critBody").append(critRow()); sumWeights(); });
  $("saveCrit").addEventListener("click", () => guard(async () => {
    S.case = await api("PUT", `/cases/${S.caseId}/criteria`, { criteria: readCriteria() }); await renderCriteria(); await refreshOverview(); banner("Criteria saved. Confirm them to start.", "ok");
  }));
  $("confirmCrit").addEventListener("click", () => guard(async () => {
    S.case = await api("POST", `/cases/${S.caseId}/criteria/confirm`); await renderCriteria(); await refreshOverview(); banner("Criteria confirmed.", "ok");
  }));

  $("uploadForm").addEventListener("submit", (e) => { e.preventDefault(); guard(async () => {
    const files = [...$("cvFiles").files]; if (!files.length) throw new Error("Choose at least one PDF.");
    if (files.some((f) => !f.name.toLowerCase().endsWith(".pdf"))) throw new Error("Please choose PDF files only.");
    if (files.some((f) => f.size > 5 * 1024 * 1024)) throw new Error("Each PDF must be 5 MB or smaller.");
    const button = $("uploadForm").querySelector("button[type=submit]"); button.disabled = true;
    let completed = 0;
    try {
      let last = null;
      for (const f of files) {
        $("uploadStatus").textContent = `Reviewing ${completed + 1} of ${files.length}: ${f.name}…`;
        const fd = new FormData(); fd.append("file", f); last = await api("POST", `/cases/${S.caseId}/candidates`, fd, true); completed++;
      }
      $("uploadStatus").textContent = `✓ ${completed} CV${completed === 1 ? "" : "s"} reviewed. Select a candidate to explore the evidence.`;
      $("uploadForm").reset(); await openDossier(last.candidate_id);   // opening it through the API is what counts as a review
    } catch (error) {
      $("uploadStatus").textContent = `Upload stopped. ${completed} of ${files.length} CVs completed. ${error.message}`;
      throw error;
    } finally { button.disabled = false; await renderCandidates(); await refreshOverview(); }
  }); });
  $("prevPage").addEventListener("click", () => guard(async () => { S.page--; await drawPage(); }));
  $("nextPage").addEventListener("click", () => guard(async () => { S.page++; await drawPage(); }));

  $("draftRank").addEventListener("click", () => guard(async () => { await api("POST", `/cases/${S.caseId}/ranking`, {}); await renderShortlist(); await refreshOverview(); }));
  $("confirmRank").addEventListener("click", () => guard(async () => {
    await api("POST", `/cases/${S.caseId}/ranking/${S.ranking.version}/confirm`, {}); await renderShortlist(); await refreshOverview(); banner("Shortlist confirmed by you.", "ok");
  }));

  $("propForm").addEventListener("submit", (e) => { e.preventDefault(); guard(async () => {
    const v = $("propStart").value; const kind = $("propKind").value; const cand = $("propCand").value;
    const contact = await api("GET", `/candidates/${cand}/contact`);
    if (!contact.confirmed_email) {
      const typed = window.prompt("Confirm the email address for this candidate.\nIt was " + (contact.source === "cv_text" ? "read from the CV, which the candidate wrote" : "not found in the CV") + ". Check it before confirming:", contact.source === "cv_text" ? contact.suggested_email : "");
      if (!typed) { banner("Nothing drafted: the email address was not confirmed.", "warn"); return; }
      await api("POST", `/candidates/${cand}/contact/confirm`, { email: typed.trim() });
    }
    await api("POST", `/cases/${S.caseId}/proposals`, { candidate_id: cand, kind, start: kind === "interview_invite" && v ? v + ":00Z" : null });
    banner("Drafted. Nothing is sent until the hiring manager approves it.", "ok"); await renderActions();
  }); });

  $("verifyLedger").addEventListener("click", () => guard(async () => {
    const v = await api("GET", "/ledger/verify"); const s = $("ledgerState");
    s.textContent = v.ok ? `Intact: ${v.events} events, chain verified` : `Broken at event #${v.first_bad_seq}`; s.className = "pill " + (v.ok ? "ok" : "bad");
  }));
  $("runAssurance").addEventListener("click", () => guard(runAssurance));

  loadSession();
  const destination = new URLSearchParams(window.location.search);
  if (destination.has("case")) S.caseId = destination.get("case");
  if (Object.hasOwn(PANELS, destination.get("tab"))) S.tab = destination.get("tab");
  guard(boot);
});
