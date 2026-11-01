"use strict";
// Candidate interview chat with a countdown timer. Every answer is saved on the server.
// The link token arrives in the URL fragment (#t=...), which browsers never send to servers;
// it is moved to sessionStorage and removed from the address bar.
(function () {
  const $ = (id) => document.getElementById(id);
  const UI = {
    en: { consent: "I have read this and I agree to continue.", start: "Start the interview", placeholder: "Type your answer…",
          send: "Send", finish: "End interview", confirmEnd: "End the interview now? You cannot come back to it.",
          done: "The interview is finished. Thank you! A recruiter will review your answers.", sending: "Sending…",
          left: "Time left", warn: "Less than 2 minutes left: send your current answer soon.",
          timeUp: "Time is up. Your answers so far have been saved." },
    fr: { consent: "J'ai lu ce texte et j'accepte de continuer.", start: "Commencer l'entretien", placeholder: "Écrivez votre réponse…",
          send: "Envoyer", finish: "Terminer l'entretien", confirmEnd: "Terminer l'entretien maintenant ? Vous ne pourrez pas y revenir.",
          done: "L'entretien est terminé. Merci ! Un recruteur examinera vos réponses.", sending: "Envoi…",
          left: "Temps restant", warn: "Moins de 2 minutes restantes : envoyez bientôt votre réponse.",
          timeUp: "Le temps est écoulé. Vos réponses ont été enregistrées." },
    ar: { consent: "قرأت هذا النص وأوافق على المتابعة.", start: "ابدأ المقابلة", placeholder: "اكتب إجابتك…",
          send: "إرسال", finish: "إنهاء المقابلة", confirmEnd: "هل تريد إنهاء المقابلة الآن؟ لا يمكنك العودة إليها.",
          done: "انتهت المقابلة. شكرا لك! سيراجع أحد المسؤولين إجاباتك.", sending: "جار الإرسال…",
          left: "الوقت المتبقي", warn: "بقي أقل من دقيقتين: أرسل إجابتك قريبا.",
          timeUp: "انتهى الوقت. تم حفظ إجاباتك." },
  };

  let token = null;
  const m = location.hash.match(/t=([A-Za-z0-9_-]{20,100})/);
  if (m) {
    token = m[1];
    try { sessionStorage.setItem("ib_token", token); } catch (e) { /* storage blocked: keep in memory */ }
    history.replaceState(null, "", location.pathname);
  } else {
    try { token = sessionStorage.getItem("ib_token"); } catch (e) { token = null; }
  }

  let info = null, lang = "en", busy = false, finished = false;
  let deadline = null, timerHandle = null;            // local clock time when the interview time ends

  const ui = (k) => (UI[lang] || UI.en)[k];
  const showError = (msg) => { $("error").textContent = msg || ""; };

  async function api(path, method, payload) {
    const res = await fetch("api/interview/" + path, {
      method: method || "GET",
      headers: { "Content-Type": "application/json", "X-Interview-Token": token || "" },
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Something went wrong");
    return data;
  }

  function bubble(sender, text) {
    const div = document.createElement("div");
    div.className = "bubble " + (sender === "bot" ? "bot" : "candidate");
    div.dir = "auto";
    div.textContent = text;            // never innerHTML: messages are untrusted text
    $("chat").appendChild(div);
    div.scrollIntoView({ block: "end", behavior: "smooth" });
  }

  function setLang(l) {
    lang = UI[l] ? l : "en";
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-lang]").forEach((b) => b.classList.toggle("active", b.dataset.lang === lang));
    if (info) $("notice").textContent = info.notice[lang] || info.notice.en;
    $("consent-label").textContent = ui("consent");
    $("start").textContent = ui("start");
    $("answer").placeholder = ui("placeholder");
    $("send").textContent = ui("send");
    $("finish").textContent = ui("finish");
    $("time-warning").textContent = ui("warn");
  }

  // ------------------------------------------------------------ timer (the server enforces the limit too)
  function startTimer(remainingS) {
    if (!remainingS && remainingS !== 0) return;
    deadline = Date.now() + remainingS * 1000;
    $("timer").classList.remove("hidden");
    clearInterval(timerHandle);
    const tick = async () => {
      const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      $("timer").textContent = `${ui("left")} ${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
      $("timer").classList.toggle("timer-low", left <= 120);
      $("time-warning").classList.toggle("hidden", !(left > 0 && left <= 120) || finished);
      if (left === 0 && !finished) {
        clearInterval(timerHandle);
        // Send what is typed, then close. The server keeps everything already sent.
        const typed = $("answer").value.trim();
        try {
          if (typed) { await send(); }
          if (!finished) { const r = await api("finish", "POST"); showHistory(r.history); }
        } catch (e) { /* already closed by the server */ }
        finishUi(true);
      }
    };
    tick();
    timerHandle = setInterval(tick, 1000);
  }

  function showHistory(history) {
    $("chat").textContent = "";
    history.forEach((h) => bubble(h.sender, h.text));
  }

  function showChat(history, completed) {
    $("consent").classList.add("hidden");
    $("chat-section").classList.remove("hidden");
    showHistory(history);
    if (completed) finishUi(false);
  }

  function finishUi(timeUp) {
    finished = true;
    clearInterval(timerHandle);
    $("composer").classList.add("hidden");
    $("timer").classList.add("hidden");
    $("done").classList.remove("hidden");
    $("done-text").textContent = timeUp ? ui("timeUp") + " " + ui("done") : ui("done");
    try { sessionStorage.removeItem("ib_token"); } catch (e) { /* ignore */ }
  }

  async function send() {
    const text = $("answer").value.trim();
    if (!text || busy || finished) return;
    busy = true; $("send").disabled = true; $("send").textContent = ui("sending"); showError("");
    bubble("candidate", text);
    $("answer").value = ""; $("count").textContent = "0 / 2000";
    try {
      const r = await api("message", "POST", { text });
      r.bot.forEach((t) => bubble("bot", t));
      if (r.completed) finishUi(false);
    } catch (e) {
      showError(e.message);
    } finally {
      busy = false; $("send").disabled = false; $("send").textContent = ui("send");
      if (!finished) $("answer").focus();
    }
  }

  async function init() {
    if (!token) { showError("This interview link is missing or invalid. Please use the link from your email."); return; }
    try { info = await api("info"); } catch (e) { showError(e.message); return; }
    $("job-title").textContent = info.job_title;
    setLang(info.language || (navigator.language || "en").slice(0, 2));
    if (info.state === "invited") {
      $("consent").classList.remove("hidden");
    } else {
      showChat(info.history, info.state === "completed");
      if (info.state === "in_progress" && info.timer && info.timer.limit_s) startTimer(info.timer.remaining_s);
    }
  }

  document.querySelectorAll("[data-lang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  $("consent-box").addEventListener("change", (e) => { $("start").disabled = !e.target.checked; });
  $("start").addEventListener("click", async () => {
    $("start").disabled = true; showError("");
    try {
      const r = await api("start", "POST", { language: lang, consent: $("consent-box").checked });
      showChat(r.history, false);
      if (info.timer && info.timer.limit_s) startTimer(info.timer.limit_s);
      $("answer").focus();
    } catch (e) { showError(e.message); $("start").disabled = false; }
  });
  $("send").addEventListener("click", send);
  $("answer").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); });
  $("answer").addEventListener("input", (e) => { $("count").textContent = e.target.value.length + " / 2000"; });
  $("finish").addEventListener("click", async () => {
    if (!confirm(ui("confirmEnd"))) return;
    try { const r = await api("finish", "POST"); showHistory(r.history); finishUi(false); } catch (e) { showError(e.message); }
  });
  init();
})();
