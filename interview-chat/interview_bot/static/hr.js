"use strict";
// HR dashboard. All data is rendered with textContent (no innerHTML), because CV text and
// candidate answers are untrusted input.
(function () {
  const $ = (id) => document.getElementById(id);
  let token = null, me = null, jobId = null, selected = null;

  function el(tag, attrs, ...children) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === undefined || v === null || v === false) return;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    });
    children.flat().forEach((c) => { if (c !== null && c !== undefined && c !== false) n.append(c instanceof Node ? c : String(c)); });
    return n;
  }
  const fmt = (ts) => ts ? new Date(ts * 1000).toLocaleString() : "";
  const chip = (text, kind) => el("span", { class: "chip " + (kind || "") }, text);
  const setErr = (msg) => { $("app-error").textContent = msg || ""; };

  async function api(path, opts) {
    opts = opts || {};
    const headers = { Authorization: "Bearer " + token };
    let body = opts.body;
    if (body && !(body instanceof FormData)) { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
    const res = await fetch("api/" + path, { method: opts.method || "GET", headers, body });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) { logout(); throw new Error("Session expired, sign in again"); }
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
  }

  // ------------------------------------------------------------ auth
  async function login() {
    $("login-error").textContent = "";
    try {
      const res = await fetch("api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $("username").value.trim(), password: $("password").value }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Login failed");
      token = data.token; me = data.user;
      try { sessionStorage.setItem("ib_staff", JSON.stringify({ token, me })); } catch (e) { /* ignore */ }
      start();
    } catch (e) { $("login-error").textContent = e.message; }
  }
  function logout() {
    token = null; me = null;
    try { sessionStorage.removeItem("ib_staff"); } catch (e) { /* ignore */ }
    $("app-view").classList.add("hidden"); $("login-view").classList.remove("hidden");
  }
  function canWrite() { return me && me.role !== "auditor"; }

  // ------------------------------------------------------------ tabs
  function showTab(name) {
    document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    ["candidates", "approvals", "outbox", "audit"].forEach((t) => $("tab-" + t).classList.toggle("hidden", t !== name));
    setErr("");
    if (name === "approvals") loadApprovals();
    if (name === "outbox") loadOutbox();
    if (name === "audit") loadAudit();
    if (name === "candidates") loadShortlist();
  }

  // ------------------------------------------------------------ candidates
  async function loadJobs() {
    const jobs = await api("jobs");
    const sel = $("job-select"); sel.textContent = "";
    jobs.forEach((j) => sel.append(el("option", { value: j.id }, `${j.title} (${j.candidates})`)));
    jobId = jobs.length ? jobs[0].id : null;
    if (jobId) await loadShortlist();
  }

  async function loadShortlist() {
    if (!jobId) return;
    const [sl, list] = await Promise.all([api(`jobs/${jobId}/shortlist`), api(`jobs/${jobId}/candidates`)]);
    const byId = Object.fromEntries(list.map((c) => [c.id, c]));
    const box = $("shortlist"); box.textContent = "";
    box.append(el("div", { class: "callout small" }, sl.notice));
    const rows = [];
    sl.candidates.forEach((c) => rows.push(row(c.id, c.alias, byId[c.id], `#${c.suggested_position}`,
      `${c.counts.with_evidence}/${c.counts.total} (must ${c.counts.must_have_with_evidence}/${c.counts.must_have_total})`, c.flags)));
    sl.without_report.forEach((c) => rows.push(row(c.id, c.alias, byId[c.id], "–", "report not generated", [])));
    box.append(el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Order"), el("th", {}, "Candidate"),
      el("th", {}, "Evidence"), el("th", {}, "Status"))), el("tbody", {}, rows)));
  }

  function row(id, alias, info, pos, evidence, flags) {
    info = info || {};
    const tags = [];
    if (info.hidden_content) tags.push(chip("hidden text in CV", "danger"));
    if ((flags || []).includes("interview_manipulation_attempt")) tags.push(chip("manipulation attempt", "danger"));
    if ((flags || []).includes("short_answers")) tags.push(chip("short answers", "warn"));
    return el("tr", { class: "clickable" + (selected === id ? " selected" : ""), onclick: () => openCandidate(id) },
      el("td", {}, pos), el("td", {}, alias, el("div", {}, tags)), el("td", { class: "small" }, evidence),
      el("td", { class: "small" }, info.status || "", info.interview_state ? el("div", { class: "muted" }, "interview: " + info.interview_state) : ""));
  }

  async function openCandidate(id, reveal) {
    selected = id; setErr("");
    const c = await api(`candidates/${id}` + (reveal ? "?reveal=1" : ""));
    const d = $("detail"); d.textContent = "";
    const head = el("div", { class: "row" }, el("h2", {}, c.alias), chip(c.status),
      c.interview ? chip("interview " + c.interview.state, c.interview.state === "completed" ? "ok" : "") : null,
      el("span", { class: "spacer" }),
      c.name ? el("span", { class: "small" }, `${c.name} · ${c.email}`)
             : (canWrite() ? el("button", { type: "button", onclick: () => openCandidate(id, true),
                 title: "Identity stays hidden during evaluation to reduce bias. Revealing is logged." }, "Reveal identity") : null));
    d.append(head);

    // Hidden content: "what you see vs what the AI would have read"
    const f = c.cv_findings || {};
    if (f.hidden_count) {
      d.append(el("div", { class: "callout danger stack" },
        el("strong", {}, `${f.hidden_count} hidden element(s) found in the CV and removed before the AI read it`),
        f.hidden_content.map((h) => el("div", {}, chip(h.technique, "danger"), " ", el("span", { class: "small" }, h.text))),
        el("div", { class: "small" }, "This is a flag for your review, not an automatic rejection.")));
    }
    if (f.pii_masked && Object.keys(f.pii_masked).length) {
      d.append(el("div", { class: "small muted" }, "Masked before AI processing: " +
        Object.entries(f.pii_masked).map(([k, v]) => `${k.toLowerCase()} ×${v}`).join(", ")));
    }

    // CV evidence
    d.append(el("h3", {}, "CV evidence per requirement"));
    d.append(el("table", {}, el("tbody", {}, c.cv_evidence.map((r) => el("tr", {},
      el("td", { class: "w40" }, r.requirement, r.must_have ? el("div", {}, chip("must-have")) : ""),
      el("td", {}, r.quotes.length ? r.quotes.map((q) => el("blockquote", { dir: "auto" }, q))
                                   : el("span", { class: "muted small" }, "No evidence found in the CV")))))));

    // Actions
    const actions = el("div", { class: "row" });
    const pendingInvite = c.proposals.find((p) => p.kind === "interview_invite" && p.status === "pending");
    if (canWrite() && ["recruiter", "hr_admin"].includes(me.role) && !pendingInvite && (!c.interview || c.interview.state !== "completed")) {
      actions.append(el("button", { class: "primary", type: "button", onclick: () => proposeInvite(id) },
        c.interview ? "Propose a new interview link" : "Propose AI interview invitation"));
    }
    if (pendingInvite) actions.append(chip("invitation waiting for approval", "warn"));
    actions.append(el("button", { type: "button", onclick: () => showReport(id) }, "Open evidence report"));
    if (c.interview && c.interview.state !== "invited") actions.append(el("button", { type: "button", onclick: () => showTranscript(id) }, "Transcript"));
    if (me.role === "hr_admin") actions.append(el("button", { class: "danger", type: "button", onclick: () => erase(id) }, "Erase personal data"));
    d.append(actions);

    if (c.decisions.length) {
      d.append(el("h3", {}, "Human decisions"));
      c.decisions.forEach((x) => d.append(el("div", { class: "small" }, chip(x.decision), ` by ${x.by}, ${fmt(x.created_at)}: `, x.reason)));
    }
    d.append(el("div", { id: "report-area", class: "stack" }));
    d.append(el("details", {}, el("summary", { class: "small muted" }, "CV text as the AI sees it (hidden content removed, personal data masked)"),
      el("pre", { dir: "auto" }, c.cv_text || "")));
    loadShortlist();
  }

  async function proposeInvite(id) {
    try { await api(`candidates/${id}/invite`, { method: "POST" }); await openCandidate(id); refreshPending(); }
    catch (e) { setErr(e.message); }
  }

  async function erase(id) {
    if (!confirm("Erase this candidate's personal data? This cannot be undone.")) return;
    try { await api(`candidates/${id}/erase`, { method: "POST" }); $("detail").textContent = ""; loadShortlist(); }
    catch (e) { setErr(e.message); }
  }

  const LEVEL_CHIP = { supported_cv_and_interview: "ok", supported_one_source: "warn", no_evidence: "danger" };

  async function showReport(id) {
    const area = $("report-area"); area.textContent = "";
    let r;
    try { r = await api(`candidates/${id}/report`); } catch (e) { setErr(e.message); return; }
    area.append(el("h3", {}, "Evidence report"), el("div", { class: "callout" }, el("strong", {}, r.summary)),
      el("div", { class: "small muted" }, r.notice));
    if (!r.interview_completed) area.append(el("div", { class: "callout warn small" }, "Interview not completed yet: CV evidence only."));
    r.review_flags.forEach((fl) => area.append(el("div", { class: "callout warn small" }, el("strong", {}, fl.type.replace(/_/g, " ") + ": "), fl.detail)));
    area.append(el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Requirement"), el("th", {}, "Level"), el("th", {}, "CV"), el("th", {}, "Interview"))),
      el("tbody", {}, r.requirements.map((q) => el("tr", {},
        el("td", {}, q.requirement, q.must_have ? el("div", {}, chip("must-have")) : ""),
        el("td", { class: "req-level" }, chip(q.level_label, LEVEL_CHIP[q.level])),
        el("td", {}, q.cv_quotes.map((x) => el("blockquote", { dir: "auto" }, x))),
        el("td", {}, q.interview_quotes.map((x) => el("blockquote", { dir: "auto" }, x))))))));
    if (r.suggested_questions_for_human_interview.length) {
      area.append(el("h3", {}, "Ask in the human interview"), el("ul", {}, r.suggested_questions_for_human_interview.map((s) => el("li", {}, s))));
    }
    area.append(el("div", { class: "small muted" }, `Model ${r.provenance.model} · prompt ${r.provenance.prompt_version} · rubric ${r.provenance.rubric_version} · anonymised input`));

    if (canWrite()) {
      const reason = el("textarea", { placeholder: "Job-related reason (required, min 15 characters)" });
      const sel = el("select", {}, el("option", { value: "advance" }, "Advance to human interview"),
        el("option", { value: "hold" }, "Hold"), el("option", { value: "reject" }, "Do not continue"));
      const err = el("div", { class: "error" });
      area.append(el("div", { class: "panel stack" }, el("h3", {}, "Your decision"),
        el("div", { class: "small muted" }, "You decide. The AI does not. Your decision and reason are recorded in the audit log."),
        sel, reason, err,
        el("button", { class: "primary", type: "button", onclick: async () => {
          err.textContent = "";
          try {
            const res = await api(`candidates/${id}/decision`, { method: "POST", body: { decision: sel.value, reason: reason.value } });
            if (res.slots_proposal) alert("Decision recorded. Interview slots were prepared and are waiting for approval in the Approvals tab.");
            await openCandidate(id); refreshPending();
          } catch (e) { err.textContent = e.message; }
        } }, "Record decision")));
    }
  }

  async function showTranscript(id) {
    const area = $("report-area"); area.textContent = "";
    const t = await api(`candidates/${id}/transcript`);
    area.append(el("h3", {}, "Transcript"));
    t.forEach((m) => {
      const flagged = m.flags && m.flags.injection;
      area.append(el("div", { class: flagged ? "callout danger" : "callout" },
        el("div", { class: "small muted" }, (m.sender === "bot" ? "Assistant" : "Candidate") + (m.question_id ? ` · ${m.question_id}` : "")
          + (m.flags && Number.isInteger(m.flags.seconds) ? ` · answered in ${m.flags.seconds >= 60 ? Math.floor(m.flags.seconds / 60) + " min " : ""}${m.flags.seconds % 60} s` : ""),
          flagged ? el("span", {}, " ", chip("looks like instructions to the AI: " + m.flags.injection.join(", "), "danger")) : ""),
        el("div", { dir: "auto", class: "prewrap" }, m.text)));
    });
  }

  async function upload() {
    $("up-error").textContent = "";
    const file = $("up-file").files[0];
    if (!file) { $("up-error").textContent = "Choose a file"; return; }
    const fd = new FormData();
    fd.append("full_name", $("up-name").value); fd.append("email", $("up-email").value); fd.append("cv", file);
    $("up-btn").disabled = true;
    try {
      const r = await api(`jobs/${jobId}/candidates`, { method: "POST", body: fd });
      $("up-name").value = ""; $("up-email").value = ""; $("up-file").value = "";
      await openCandidate(r.id);
    } catch (e) { $("up-error").textContent = e.message; }
    finally { $("up-btn").disabled = false; }
  }

  // ------------------------------------------------------------ approvals
  async function refreshPending() {
    try { const p = await api("proposals?status=pending"); $("pending-count").textContent = p.length || ""; } catch (e) { /* ignore */ }
  }

  async function loadApprovals() {
    const box = $("approvals"); box.textContent = "";
    const list = await api("proposals?status=pending");
    $("pending-count").textContent = list.length || "";
    if (!list.length) { box.append(el("p", { class: "muted" }, "Nothing waiting for approval.")); return; }
    list.forEach((p) => {
      const err = el("div", { class: "error" });
      const card = el("div", { class: "panel stack" },
        el("div", { class: "row" }, el("strong", {}, p.kind === "interview_invite" ? "AI interview invitation" : "Interview slots"),
          chip(p.alias), el("span", { class: "spacer" }), el("span", { class: "small muted" }, `proposed by ${p.proposed_by_name}, ${fmt(p.proposed_at)}`)),
        el("div", { class: "small" }, el("strong", {}, "To: "), p.payload.to),
        el("div", { class: "small" }, el("strong", {}, "Subject: "), p.payload.subject),
        el("pre", { class: "callout" }, p.payload.body),
        el("div", { class: "small muted" }, "Payload fingerprint: " + p.payload_hash.slice(0, 16) + "… (approval is bound to exactly this content)"),
        err,
        canWrite() ? el("div", { class: "row" },
          el("button", { class: "primary", type: "button", onclick: async () => {
            err.textContent = "";
            try { await api(`proposals/${p.id}/approve`, { method: "POST", body: { payload_hash: p.payload_hash } }); loadApprovals(); }
            catch (e) { err.textContent = e.message; }
          } }, "Approve and send"),
          el("button", { type: "button", onclick: async () => {
            const note = prompt("Reason for rejecting (optional)") || "";
            try { await api(`proposals/${p.id}/reject`, { method: "POST", body: { note } }); loadApprovals(); }
            catch (e) { err.textContent = e.message; }
          } }, "Reject")) : null);
      box.append(card);
    });
  }

  async function loadOutbox() {
    const box = $("outbox"); box.textContent = "";
    const list = await api("outbox");
    if (!list.length) { box.append(el("p", { class: "muted" }, "No messages sent yet.")); return; }
    list.forEach((m) => {
      const body = el("pre", {}, m.body);
      const link = (m.body.match(/https?:\/\/\S+\/interview#t=[A-Za-z0-9_-]+/) || [])[0];
      box.append(el("div", { class: "panel stack" },
        el("div", { class: "row" }, el("strong", {}, m.subject), el("span", { class: "spacer" }), el("span", { class: "small muted" }, fmt(m.created_at))),
        el("div", { class: "small" }, "To: " + m.to_addr), body,
        link ? el("a", { href: link, target: "_blank", rel: "noopener noreferrer" }, "Open the candidate's interview link (demo)") : null));
    });
  }

  async function loadAudit() {
    const box = $("audit"); box.textContent = "";
    const list = await api("ledger");
    box.append(el("table", {}, el("thead", {}, el("tr", {}, ["Time", "Actor", "Action", "Details", "Hash"].map((h) => el("th", {}, h)))),
      el("tbody", {}, list.map((e) => el("tr", {}, el("td", { class: "small" }, fmt(e.ts)), el("td", { class: "small" }, e.actor),
        el("td", {}, chip(e.action, /blocked|failure|flagged/.test(e.action) ? "danger" : "")),
        el("td", {}, el("pre", { class: "small" }, JSON.stringify(e.data))), el("td", { class: "small muted" }, e.hash))))));
  }

  async function verify() {
    const r = await api("ledger/verify");
    $("verify-result").textContent = "";
    $("verify-result").append(r.valid ? chip(`chain valid · ${r.entries} entries`, "ok") : chip(`chain BROKEN at entry ${r.first_broken_id}`, "danger"));
  }

  // ------------------------------------------------------------ boot
  async function start() {
    $("login-view").classList.add("hidden"); $("app-view").classList.remove("hidden");
    $("who").textContent = `${me.display_name} · ${me.role}`;
    $("upload-panel").classList.toggle("hidden", !["recruiter", "hr_admin"].includes(me.role));
    try { await loadJobs(); refreshPending(); } catch (e) { setErr(e.message); }
  }

  $("login-btn").addEventListener("click", login);
  $("password").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
  $("logout").addEventListener("click", logout);
  $("job-select").addEventListener("change", (e) => { jobId = Number(e.target.value); $("detail").textContent = ""; loadShortlist(); });
  $("up-btn").addEventListener("click", upload);
  $("verify").addEventListener("click", verify);
  document.querySelectorAll("nav.tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  window.addEventListener("unhandledrejection", (e) => setErr(e.reason && e.reason.message));

  try {
    const saved = JSON.parse(sessionStorage.getItem("ib_staff") || "null");
    if (saved && saved.token) { token = saved.token; me = saved.me; start(); }
  } catch (e) { /* ignore */ }
})();
