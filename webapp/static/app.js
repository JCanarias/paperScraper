// The web panel of paperScraper. Every address is relative to the page (/p/<session>/), which carries
// the session, so it works also on phones that don't keep the cookie.
"use strict";

const view = document.getElementById("view");
const session = (location.pathname.match(/^\/p\/([^/]+)\//) || [])[1] || "";
const terminalUrl = `/s/${session}/`;
document.getElementById("terminal-link").href = terminalUrl;

let state = { daily: {}, job: {} };
let counts = null;
let jobWasRunning = null;
// The search page remembers what was being done when the user goes to another tab and comes back.
const search = { mode: "author", name: "", authors: null, chosen: new Set(), previews: {}, languagesTouched: false,
                 languages: null, title: "", bibliographyText: "" };

// --- helpers ---

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  if (response.status === 401) { location.href = "/login"; throw new Error("La sesión ha caducado."); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || `Error ${response.status}`);
  return data;
}

function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
}

let toastTimer;
function toast(message, bad = false) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.className = "toast" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.add("hidden"), bad ? 7000 : 4000);
}

function workLine(work) {
  const details = [work.year || "s. f.", (work.authors || []).join(", "), work.source, work.publisher, work.language]
    .filter(Boolean).map(esc).join(" · ");
  return `<div class="title">${esc(work.title)}</div><div class="muted small">${details}</div>`;
}

function backLink(to = "#/", text = "Inicio") { return `<a class="back" href="${to}">← ${esc(text)}</a>`; }

function loading(title, back) { view.innerHTML = `${back || ""}<h1>${esc(title)}</h1><p class="muted">Cargando…</p>`; }

function failed(title, error, back) {
  view.innerHTML = `${back || ""}<h1>${esc(title)}</h1><p class="bad-text">${esc(error.message)}</p>
    <div class="actions"><button id="again">Reintentar</button></div>`;
  document.getElementById("again").addEventListener("click", render);
}

function plural(count, one, many) { return `${count} ${count === 1 ? one : many}`; }

function shortDate(text) { return text ? `${text.slice(8, 10)}/${text.slice(5, 7)} ${text.slice(11, 16)}` : ""; }

function capitalized(text) { return text ? text[0].toUpperCase() + text.slice(1) : ""; }

function busyReason() {
  if (state.job && state.job.running) return `Ya hay una tarea en marcha: ${state.job.label}.`;
  if (state.daily && state.daily.running) return "La revisión diaria está en marcha.";
  return null;
}

async function startJob(task, body, question) {
  if (question && !confirm(question)) return false;
  try {
    await post(`api/job/${task}`, body);
    location.hash = "#/job";
    await refreshStatus();
    return true;
  } catch (error) { toast(error.message, true); return false; }
}

// The checkboxes of the page that match `selector` and are ticked, as a list of their values.
function checkedValues(selector) { return [...view.querySelectorAll(selector)].filter(input => input.checked).map(input => input.value); }

function matchesFilter(item, words) { return words.every(word => item.dataset.text.includes(word)); }

function filterWords(input) { return input.value.toLowerCase().split(/\s+/).filter(Boolean); }

// --- the bar on top and the tabs: always visible ---

function dailyText(daily) {
  if (daily.running) {
    const author = daily.current_author ? ` · ${daily.current_author} (${daily.authors_done})` : "";
    const since = daily.started ? ` desde las ${daily.started.slice(11)}` : "";
    return `Revisión diaria en marcha${since}${author}`;
  }
  const last = daily.ended ? `Última: ${shortDate(daily.ended)} ${daily.ok ? "✓" : "con errores"} · ` : "";
  return `${last}Próxima: ${daily.next || "?"}`;
}

function jobResult(job) {
  if (job.running) return job.stopping ? "parando…" : "en marcha";
  if (job.interrupted) return "interrumpida (se reinició el panel)";
  if (job.stopped || job.code === 130 || job.code === -2) return "parada";
  if (job.code === 0) return "terminada";
  return "terminada con errores";
}

async function refreshStatus() {
  const page = route();
  const log = page === "job" ? "?log=job" : page === "daily" ? "?log=daily" : "";
  try {
    state = await api(`api/status${log}`);
  } catch (error) {
    document.getElementById("daily-text").textContent = "Sin conexión con la torre";
    document.getElementById("daily-dot").className = "dot bad";
    schedulePoll();
    return;
  }
  const daily = state.daily || {};
  document.getElementById("daily-text").textContent = dailyText(daily);
  document.getElementById("daily-dot").className = "dot " + (daily.running ? "running" : daily.ended ? (daily.ok ? "ok" : "bad") : "");
  const job = state.job || {};
  document.getElementById("job-status").classList.toggle("hidden", !job.running);
  document.getElementById("job-text").textContent = job.running
    ? `${job.label} · ${job.stopping ? "parando…" : job.last_line || `desde las ${job.started.slice(11)}`}` : "";
  document.title = job.running || daily.running ? "● paperScraper" : "paperScraper";
  if (jobWasRunning && !job.running) jobEnded(job);
  jobWasRunning = !!job.running;
  if (route() === "job") renderJobLog();
  if (route() === "daily") renderDailyLog();
  schedulePoll();
}

function jobEnded(job) {
  const result = jobResult(job);
  toast(`${job.label}: ${result}`, result !== "terminada");
  if (navigator.vibrate) navigator.vibrate(150);
  counts = null;
  loadCounts();
  // A search by title goes on choosing what to download.
  if (job.task === "title_search" && job.code === 0 && route() === "job") location.hash = "#/results";
  else if (route() === "" || route() === "todo") render();
}

// Every 2 s while something runs or its log is open; every 15 s otherwise; nothing while the phone hides the page.
let pollTimer;
function schedulePoll() {
  clearTimeout(pollTimer);
  if (document.hidden) return;
  const busy = (state.job || {}).running || (state.daily || {}).running || ["job", "daily"].includes(route());
  pollTimer = setTimeout(refreshStatus, busy ? 2000 : 15000);
}

async function loadCounts() {
  try {
    counts = await api("api/home");
  } catch (error) { return null; }
  // Only what waits for a decision: the works without a file are many and stay for long.
  const waiting = counts.counts.reviews || 0;
  const badge = document.getElementById("todo-badge");
  badge.textContent = waiting > 99 ? "99+" : waiting;
  badge.classList.toggle("hidden", !waiting);
  return counts;
}

// --- Inicio ---

const MORE = [
  { label: "Ver y borrar archivos de la biblioteca", page: "library" },
  { label: "Autores que seguir", hint: "Revisión diaria", count: "followed", page: "follow" },
  { label: "Idiomas", hintFrom: "languages", page: "languages" },
  { label: "Actualizar los catálogos locales", hint: "Dialnet, PhilArchive, DOAB, BNE", page: "indexes" },
  { label: "Poner metadatos a los archivos ya descargados", task: "tag",
    question: "¿Escribir los metadatos en todos los archivos descargados?" },
  { label: "Revisión diaria", hint: "Sus informes y su log, y hacerla ahora", page: "daily" },
  { label: "Terminal", hint: "El menú de siempre", href: terminalUrl },
];

function menu(items, data) {
  const html = items.map((item, number) => {
    const count = item.count && data ? data.counts[item.count] : null;
    const hint = item.hintFrom ? data && data[item.hintFrom] : item.hint;
    const badge = count != null ? `<span class="badge ${count ? "" : "quiet"}">${count}</span>` : `<span class="chevron">›</span>`;
    return `<button class="menu-item" data-item="${number}"><span>${esc(item.label)}${hint ? `<span class="hint">${esc(hint)}</span>` : ""}</span>${badge}</button>`;
  }).join("");
  return `<div class="menu" data-menu>${html}</div>`;
}

function bindMenu(items) {
  view.querySelectorAll("[data-menu] .menu-item").forEach(button => button.addEventListener("click", () => {
    const item = items[Number(button.dataset.item)];
    if (item.href) location.href = item.href;
    else if (item.page) location.hash = `#/${item.page}`;
    else if (item.task) startJob(item.task, {}, item.question);
  }));
}

function downloadItem(item) {
  return `<li><div class="title">${esc(item.title)}</div>
    <div class="muted small">${esc([(item.authors || []).join(", "), item.year, item.source || item.how, (item.folder || "").replace(/\s*\([^)]*\)$/, "")].filter(Boolean).join(" · "))}</div>
    <div class="muted small">${esc(shortDate(item.time.replace("T", " ")))}</div></li>`;
}

async function renderHome() {
  if (!counts) view.innerHTML = `<p class="muted">Cargando…</p>`;
  const data = await loadCounts();
  if (route() !== "") return;
  if (!data) return failed("Inicio", new Error("No se puede hablar con la torre."));
  const job = state.job || {};
  const c = data.counts;
  let html = `<div class="quick">
    <a class="quick-item" href="#/search"><span class="quick-icon" aria-hidden="true">🔎</span>Buscar</a>
    <a class="quick-item" href="#/reviews"><span class="quick-number ${c.reviews ? "" : "quiet"}">${c.reviews}</span>Dudosas</a>
    <a class="quick-item" href="#/pending"><span class="quick-number ${c.pending ? "" : "quiet"}">${c.pending}</span>Pendientes</a>
    <a class="quick-item" href="#/todo"><span class="quick-number ${c.not_uploaded ? "" : "quiet"}">${c.not_uploaded}</span>Sin subir</a>
  </div>`;

  if (job.task) {
    const result = jobResult(job);
    html += `<h2>${job.running ? "Tarea en marcha" : "Última tarea"}</h2><a class="card link-card" href="#/job">
      <div class="title">${esc(job.label)}</div>
      <div class="small ${job.running ? "" : result === "terminada" ? "ok-text" : "bad-text"}">${esc(capitalized(result))} · ${esc(shortDate(job.started))}</div>
      ${job.progress && job.progress.total ? `<div class="small">${esc(progressNumbers(job.progress))}</div>` : ""}
      ${job.last_line ? `<div class="muted small ellipsis">${esc(job.last_line)}</div>` : ""}</a>`;
  }

  html += `<h2>Última revisión diaria</h2>`;
  html += data.daily_report ? `<a class="card link-card" href="#/daily">${reportHead(data.daily_report)}</a>`
    : `<a class="card link-card" href="#/daily"><p class="empty">Todavía no hay informes. Cada revisión deja aquí el suyo al terminar.</p></a>`;

  const downloads = data.downloads || [];
  html += `<h2>Últimas descargas</h2><div class="card">`;
  if (downloads.length) {
    html += `<ul class="list">${downloads.slice(0, 5).map(downloadItem).join("")}</ul>`;
    if (downloads.length > 5) html += `<details class="plain"><summary>Ver ${downloads.length - 5} más</summary>
      <ul class="list">${downloads.slice(5).map(downloadItem).join("")}</ul></details>`;
  } else {
    html += `<p class="empty">Todavía no hay descargas apuntadas. Desde ahora, cada descarga sale aquí.</p>`;
  }
  html += `</div><h2>Más</h2>${menu(MORE, data)}`;
  view.innerHTML = html;
  bindMenu(MORE);
}

// --- Pendiente: what waits for the user ---

async function renderTodo() {
  if (!counts) loading("Pendiente");
  const data = await loadCounts();
  if (route() !== "todo") return;
  if (!data) return failed("Pendiente", new Error("No se puede hablar con la torre."));
  const items = [
    { label: "Revisar obras dudosas", hint: "Internet Archive y Google Books: ¿son del autor?", count: "reviews", page: "reviews" },
    { label: "Descargar a mano", hint: "Ábrelas y sube aquí el PDF o EPUB", count: "pending", page: "pending" },
    { label: "Reintentar las pendientes", hint: "Busca otra vez su archivo en todas las fuentes", count: "pending", task: "retry",
      question: "¿Buscar otra vez el archivo de todas las obras pendientes? Puede tardar." },
    { label: "Subir a Calibre", hint: "Lo descargado que aún no está en la biblioteca", count: "not_uploaded", task: "upload",
      question: "¿Subir a Calibre lo descargado?" },
  ];
  view.innerHTML = `<h1>Pendiente</h1>${menu(items, data)}`;
  bindMenu(items);
}

// --- Tarea ---

function jobNextSteps(job) {
  if (job.running || !job.task) return "";
  const steps = [];
  if (job.task === "title_search" && job.code === 0) steps.push(`<a class="button primary" href="#/results">Elegir qué descargar</a>`);
  if (["author", "title_download", "bibliography", "retry", "reviews", "daily"].includes(job.task)) {
    steps.push(`<a class="button" href="#/todo">Ver lo pendiente</a>`);
  }
  steps.push(`<a class="button" href="#/search">Otra búsqueda</a>`);
  return steps.join("");
}

function renderJob() {
  view.innerHTML = `<h1 id="job-title"></h1><p class="small" id="job-state"></p>
    <div id="job-progress"></div>
    <details id="job-log-box"><summary>Ver el log<span class="chevron">›</span></summary>
      <div class="inner"><pre class="log" id="job-log"></pre></div></details>
    <div class="actions" id="job-actions"></div>`;
  // The tasks from before the numbers existed only have their log: open.
  document.getElementById("job-log-box").open = !(state.job || {}).progress;
  view.addEventListener("click", stopClicked);
  renderJobLog();
}

// --- What a task is doing, as numbers (task_progress.py) ---

function secondsBetween(from, to) { return Math.max(0, Math.round((new Date(to) - new Date(from)) / 1000)); }

function duration(seconds) {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

function tile(number, label, style = "") {
  return `<div class="tile"><span class="tile-number ${style}">${number.toLocaleString("es-ES")}</span><span>${esc(label)}</span></div>`;
}

function bar(done, total, text) {
  const share = total ? Math.min(100, Math.round(100 * done / total)) : 0;
  return `<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done}">
      <span style="width:${share}%"></span></div><div class="muted small bar-text">${esc(text)}</div>`;
}

const EVENT_MARKS = { ok: ["✓", "ok-text"], bad: ["✗", "bad-text"], up: ["⬆", "accent-text"] };

function progressHtml(progress, running) {
  if (!progress) return "";
  // The tower writes its local time without zone, which the browser reads as local time too.
  const now = running ? new Date() : progress.updated;
  let html = `<div class="card progress">`;
  if (progress.group) {
    const of = progress.groups_total ? `${Math.min(progress.groups_done + 1, progress.groups_total)} de ${progress.groups_total}` : "";
    html += `<div class="progress-head"><span class="title">${esc(progress.group)}</span><span class="muted small">${esc(of)}</span></div>`;
    if (progress.groups_total > 1) html += bar(progress.groups_done + (running ? 0 : 1), progress.groups_total, "");
  }
  if (running && progress.step) html += `<div class="small step"><span class="dot running"></span>${esc(progress.step)}</div>`;
  if (running && progress.current) {
    html += `<div class="small current"><span class="muted">Ahora:</span> ${esc(progress.current.title)}
      <span class="muted">· ${esc(duration(secondsBetween(progress.current.since, now)))}</span>
      ${progress.detail ? `<span class="muted block">${esc(progress.detail)}</span>` : ""}</div>`;
  }
  const resolved = progress.downloaded + progress.not_found;
  if (progress.total) {
    html += bar(resolved, progress.total, `${resolved} de ${plural(progress.total, "obra", "obras")} resueltas · ${duration(secondsBetween(progress.started, now))}`);
  }
  html += `<div class="tiles">${tile(progress.total, "obras")}${tile(progress.downloaded, "descargadas", "ok-text")}${
    tile(progress.not_found, "sin archivo", progress.not_found ? "bad-text" : "")}${
    progress.uploaded || progress.upload_failed ? tile(progress.uploaded, "subidas a Calibre", "accent-text") : ""}</div>`;
  const sources = Object.entries(progress.by_source || {}).sort((a, b) => b[1] - a[1]);
  if (sources.length) {
    const most = sources[0][1];
    html += `<h3>De dónde vienen</h3><ul class="sources">${sources.slice(0, 8).map(([name, count]) => `<li>
      <span class="source-name">${esc(name)}</span><span class="source-bar"><span style="width:${Math.max(4, Math.round(100 * count / most))}%"></span></span>
      <span class="source-count">${count}</span></li>`).join("")}${sources.length > 8
      ? `<li class="muted small">y ${sources.length - 8} webs más (${sources.slice(8).reduce((sum, [, count]) => sum + count, 0)})</li>` : ""}</ul>`;
  }
  const events = (progress.events || []).slice(-12).reverse();
  if (events.length) {
    html += `<h3>Últimas</h3><ul class="list compact events">${events.map(event => {
      const [mark, style] = EVENT_MARKS[event.kind] || ["·", "muted"];
      return `<li><span class="${style} mark">${mark}</span><span class="grow"><span class="ellipsis block">${esc(event.title)}</span>
        <span class="muted small">${esc(event.time)} · ${esc(event.note)}</span></span></li>`;
    }).join("")}</ul>`;
  }
  return html + `</div>`;
}

function progressNumbers(progress) {
  return `${plural(progress.downloaded, "descargada", "descargadas")} · ${progress.not_found} sin archivo · de ${progress.total}`;
}

function showProgress(element, progress, running) {
  if (!element) return;
  const html = progressHtml(progress, running);
  if (element.dataset.html !== html) { element.innerHTML = html; element.dataset.html = html; }
}

async function stopClicked(event) {
  if (event.target.id !== "job-stop") return;
  if (!confirm("¿Parar la tarea? Lo ya descargado se queda y la lista se guarda.")) return;
  try { await post("api/job/stop"); toast("Parando…"); refreshStatus(); } catch (error) { toast(error.message, true); }
}

function renderJobLog() {
  const job = state.job || {};
  const title = document.getElementById("job-title");
  if (!title) return;
  title.textContent = job.label || "Ninguna tarea todavía";
  const result = jobResult(job);
  document.getElementById("job-state").innerHTML = !job.task ? "Lo que lances desde el panel se ve aquí mientras se hace."
    : job.running ? `${esc(capitalized(result))} desde las ${esc(job.started.slice(11))}`
    : `<span class="${result === "terminada" ? "ok-text" : "bad-text"}">${esc(capitalized(result))}</span> · ${esc(shortDate(job.started))} → ${esc(shortDate(job.finished))}`;
  const actions = job.running ? `<button class="danger" id="job-stop" ${job.stopping ? "disabled" : ""}>Parar la tarea</button>` : jobNextSteps(job);
  const box = document.getElementById("job-actions");
  if (box.dataset.html !== actions) { box.innerHTML = actions; box.dataset.html = actions; }
  showProgress(document.getElementById("job-progress"), job.progress, job.running);
  showLog(document.getElementById("job-log"), job.log || []);
}

function showLog(element, lines) {
  // Keep following the end, unless the user scrolled up to read.
  const atEnd = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
  const text = lines.join("\n");
  if (element.textContent !== text) {
    element.textContent = text;
    if (atEnd) element.scrollTop = element.scrollHeight;
  }
  element.classList.toggle("hidden", !text);
}

// --- Revisión diaria ---

const OUTCOMES = { ok: ["Terminada", "ok-text"], failed: ["Ha fallado", "bad-text"], stopped: ["Parada", "bad-text"] };

// The numbers of a report, in one line: only the ones that say something.
function reportNumbers(report) {
  const parts = [plural(report.downloaded, "descargada", "descargadas"), plural(report.new, "nueva", "nuevas"),
                 `${report.pending} sin archivo`];
  if (report.asked) parts.push(plural(report.asked, "dudosa preguntada", "dudosas preguntadas"));
  return parts.join(" · ");
}

function reportHead(report) {
  const [outcome, style] = OUTCOMES[report.outcome] || [report.outcome, ""];
  const problems = (report.problems || []).length;
  const note = report.error ? `<div class="small bad-text ellipsis">${esc(report.error)}</div>`
    : problems ? `<div class="small warn-text">⚠️ ${plural(problems, "problema", "problemas")}</div>`
    : report.outcome === "ok" ? `<div class="small muted">Ninguna fuente ha dado problemas · ${plural(report.authors_checked, "autor", "autores")}</div>` : "";
  return `<div class="report-head"><span class="title">${esc(shortDate(report.started.replace("T", " ")))}</span>
      <span class="small ${style}">${esc(outcome)} · ${esc(report.minutes)} min</span></div>
    <div class="small">${esc(reportNumbers(report))}</div>${note}`;
}

function reportBody(report) {
  let html = "";
  if (report.error) html += `<p class="bad-text small">${esc(report.error)}</p>`;
  html += `<p class="small muted">${esc(plural(report.authors_checked, "autor revisado", "autores revisados"))}${
    report.in_calibre != null ? ` · ${esc(report.in_calibre)} subidas a Calibre` : ""}</p>`;
  const downloads = report.downloads || [];
  if (downloads.length) {
    html += `<h3>Descargadas</h3><ul class="list compact">${downloads.map(work => `<li>
      <div class="title">${esc(work.title)}</div>
      <div class="muted small">${esc([work.year || "s. f.", (work.authors || []).join(", "), work.source].join(" · "))}</div>
      <div class="muted small">${esc(work.calibre)}</div></li>`).join("")}</ul>`;
  }
  const authors = report.authors || [];
  if (authors.length) {
    html += `<h3>Autores con novedades</h3><ul class="list compact">${authors.map(author => `<li>
      <span class="title">${esc(author.name)}</span><div class="small ${author.failed ? "bad-text" : "muted"}">${author.failed
        ? "Ha fallado (mira el log)" : esc(`${plural(author.new, "nueva", "nuevas")} · ${plural(author.downloaded, "descargada", "descargadas")} · ${author.pending} sin archivo`)}</div>
      </li>`).join("")}</ul>`;
  } else if (report.authors_checked) {
    html += `<p class="small muted">Ningún autor tiene obras nuevas ni descargas.</p>`;
  }
  const problems = report.problems || [];
  if (problems.length) {
    html += `<h3>Problemas</h3><ul class="list compact">${problems.map(problem =>
      `<li class="small">${esc(problem.text)}${problem.times > 1 ? ` <span class="muted">(×${problem.times})</span>` : ""}</li>`).join("")}</ul>`;
  }
  return html;
}

let dailyWasRunning = null;

function renderDaily() {
  view.innerHTML = `${backLink()}<h1>Revisión diaria</h1><p class="small" id="daily-state"></p>
    <div class="actions tight"><button id="daily-now">Hacer la revisión ahora</button></div>
    <div id="daily-progress"></div>
    <h2>Informes</h2><div id="daily-reports"><p class="muted">Cargando…</p></div>
    <details id="daily-log-box"><summary>Log de la última revisión<span class="chevron">›</span></summary>
      <div class="inner"><pre class="log" id="daily-log"></pre></div></details>`;
  document.getElementById("daily-now").addEventListener("click", () =>
    startJob("daily", {}, "¿Hacer ahora la revisión diaria? Mañana se hace otra vez a su hora."));
  dailyWasRunning = !!(state.daily || {}).running;
  // While it runs, the log is what tells what it does.
  document.getElementById("daily-log-box").open = dailyWasRunning && !(state.daily || {}).progress;
  loadDailyReports();
  renderDailyLog();
}

async function loadDailyReports() {
  let reports;
  try { reports = (await api("api/daily_reports")).reports; } catch (error) {
    const box = document.getElementById("daily-reports");
    if (box) box.innerHTML = `<p class="bad-text">${esc(error.message)}</p>`;
    return;
  }
  const box = document.getElementById("daily-reports");
  if (!box) return;
  if (!reports.length) {
    box.innerHTML = `<p class="empty">Todavía no hay informes. Cada revisión deja aquí el suyo al terminar.</p>`;
    return;
  }
  box.innerHTML = reports.map((report, number) => `<details class="report" ${number === 0 ? "open" : ""}>
    <summary><div class="grow">${reportHead(report)}</div><span class="chevron">›</span></summary>
    <div class="inner">${reportBody(report)}</div></details>`).join("");
}

function renderDailyLog() {
  const daily = state.daily || {};
  const element = document.getElementById("daily-state");
  if (!element) return;
  element.textContent = dailyText(daily);
  document.getElementById("daily-now").disabled = !!daily.running;
  // While it runs; afterwards its report says the same.
  showProgress(document.getElementById("daily-progress"), daily.running ? daily.progress : null, true);
  showLog(document.getElementById("daily-log"), daily.log_tail || ["Todavía no hay ningún log de la revisión diaria."]);
  // When a check ends, its report is the new first one.
  if (dailyWasRunning && !daily.running) loadDailyReports();
  dailyWasRunning = !!daily.running;
}

// --- Buscar ---

function renderSearch() {
  const tabs = [["author", "Autor"], ["title", "Título"], ["bibliography", "Bibliografía"]];
  view.innerHTML = `<h1>Buscar</h1>
    <div class="segmented" role="tablist">${tabs.map(([mode, name]) =>
      `<button role="tab" data-mode="${mode}" aria-selected="${search.mode === mode}">${name}</button>`).join("")}</div>
    <div id="search-body"></div>`;
  view.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => {
    search.mode = button.dataset.mode;
    renderSearch();
  }));
  ({ author: renderAuthorSearch, title: renderTitleSearch, bibliography: renderBibliographySearch })[search.mode]();
}

function busyNote() {
  const reason = busyReason();
  return reason ? `<p class="note">${esc(reason)} Puedes ir eligiendo, pero no empezará hasta que termine.</p>` : "";
}

// Por autor: choose the OpenAlex profiles (one person often has several), their languages, and download.

function renderAuthorSearch() {
  const body = document.getElementById("search-body");
  body.innerHTML = `<form class="search-form" id="author-form">
      <input type="search" id="author-name" placeholder="Nombre del autor" value="${esc(search.name)}"
        autocomplete="off" autocapitalize="words" enterkeyhint="search" required>
      <button class="primary" type="submit">Buscar</button>
    </form><div id="author-results"></div>`;
  document.getElementById("author-form").addEventListener("submit", async event => {
    event.preventDefault();
    const input = document.getElementById("author-name");
    const name = input.value.trim();
    if (!name) return;
    input.blur();
    Object.assign(search, { name, authors: null, chosen: new Set(), previews: {}, languagesTouched: false });
    document.getElementById("author-results").innerHTML = `<p class="muted">Buscando en OpenAlex…</p>`;
    try {
      const [found, languages] = await Promise.all([
        api(`api/authors?name=${encodeURIComponent(name)}`),
        search.languages ? Promise.resolve(search.languages) : api("api/languages"),
      ]);
      search.authors = found.authors;
      search.languages = languages;
      if (found.authors.length === 1) search.chosen.add(found.authors[0].id);
    } catch (error) {
      document.getElementById("author-results").innerHTML = `<p class="bad-text">${esc(error.message)}</p>`;
      return;
    }
    renderAuthorResults();
  });
  if (search.authors) renderAuthorResults();
  else if (!search.name) document.getElementById("author-name").focus();
}

function mainAuthor() {
  const chosen = (search.authors || []).filter(author => search.chosen.has(author.id));
  return chosen.length ? chosen.reduce((best, author) => author.works_count > best.works_count ? author : best) : null;
}

// The languages it starts from: those of the last search of this person, or the general ones.
function defaultLanguages() {
  const author = mainAuthor();
  const earlier = author && author.known && author.known.language_choice;
  if (earlier) {
    const chosen = earlier.languages || [];
    return { chosen, unknown: !!earlier.unknown_language && chosen.length > 0, earlier: true };
  }
  return { chosen: search.languages.chosen, unknown: search.languages.unknown_language, earlier: false };
}

function renderAuthorResults() {
  const box = document.getElementById("author-results");
  const authors = search.authors;
  if (!authors.length) { box.innerHTML = `<p class="empty">No se ha encontrado ningún autor con ese nombre.</p>`; return; }
  let html = `<p class="muted small">${authors.length > 1
    ? "Varios perfiles coinciden. Una misma persona suele tener varios (con el nombre escrito de otra forma): márcalos todos y se juntan en una sola lista."
    : "Solo un perfil coincide. Mira sus obras si dudas de que sea quien buscas."}</p><div class="card">`;
  authors.forEach(author => {
    const known = author.known;
    html += `<div class="author">
      <label class="check"><input type="checkbox" value="${esc(author.id)}" ${search.chosen.has(author.id) ? "checked" : ""}>
        <span><span class="title">${esc(author.name)}</span>
        <span class="muted small block">${plural(author.works_count, "obra", "obras")} · ${esc(author.institutions.join(", ") || "institución desconocida")}</span>
        ${known ? `<span class="small block ok-text">Ya en tu biblioteca: ${plural(known.works, "obra", "obras")}${known.follow ? " · se sigue cada día" : ""}</span>` : ""}
        </span></label>
      <button class="link" data-preview="${esc(author.id)}">${search.previews[author.id] ? "Ocultar sus obras" : "Ver sus obras más citadas"}</button>
      <div class="preview">${search.previews[author.id] ? previewHtml(search.previews[author.id]) : ""}</div>
    </div>`;
  });
  html += `</div><div id="author-languages"></div>${busyNote()}
    <div class="actions sticky"><button class="primary grow" id="author-download">Buscar y descargar sus obras</button></div>`;
  box.innerHTML = html;

  box.querySelectorAll(".author input[type=checkbox]").forEach(input => input.addEventListener("change", () => {
    if (input.checked) search.chosen.add(input.value); else search.chosen.delete(input.value);
    renderAuthorLanguages();
  }));
  box.querySelectorAll("[data-preview]").forEach(button => button.addEventListener("click", async () => {
    const id = button.dataset.preview;
    const preview = button.nextElementSibling;
    if (search.previews[id]) {
      delete search.previews[id];
      preview.innerHTML = "";
      button.textContent = "Ver sus obras más citadas";
      return;
    }
    preview.innerHTML = `<p class="muted small">Cargando…</p>`;
    try {
      search.previews[id] = (await api(`api/author_works?id=${encodeURIComponent(id)}`)).works;
      preview.innerHTML = previewHtml(search.previews[id]);
      button.textContent = "Ocultar sus obras";
    } catch (error) { preview.innerHTML = `<p class="bad-text small">${esc(error.message)}</p>`; }
  }));
  document.getElementById("author-download").addEventListener("click", downloadAuthor);
  renderAuthorLanguages();
}

function previewHtml(works) {
  if (!works.length) return `<p class="muted small">OpenAlex no le conoce obras.</p>`;
  return `<ul class="list compact">${works.map(work => `<li>${workLine(work)}</li>`).join("")}</ul>`;
}

function renderAuthorLanguages() {
  const box = document.getElementById("author-languages");
  if (!box) return;
  const names = search.languages.names;
  let chosen, unknown, earlier = false;
  if (search.languagesTouched) {
    chosen = checkedValues("#author-languages .lang");
    unknown = document.getElementById("lang-unknown").checked;
  } else {
    ({ chosen, unknown, earlier } = defaultLanguages());
  }
  const label = chosen.length ? chosen.map(code => names[code] || code).join(", ") + (unknown ? ", sin idioma conocido" : "") : "todos";
  const open = box.querySelector("details") && box.querySelector("details").open;
  box.innerHTML = `<details ${open ? "open" : ""}><summary><span>Idiomas: ${esc(label)}</span><span class="muted small">cambiar</span></summary><div class="inner">
    <p class="muted small">${search.languagesTouched ? "Elegidos ahora." : earlier ? "Los de la última búsqueda de este autor." : "Los generales (menú Idiomas)."}
      Sin ninguno marcado: todos. La revisión diaria de este autor usará los mismos.</p>
    <div class="lang-grid">${Object.entries(names).map(([code, name]) => `<label class="check"><input type="checkbox" class="lang" value="${esc(code)}"
      ${chosen.includes(code) ? "checked" : ""}><span>${esc(name)}</span></label>`).join("")}</div>
    <label class="check"><input type="checkbox" id="lang-unknown" ${unknown ? "checked" : ""}><span>Obras sin idioma conocido</span></label>
  </div></details>`;
  box.querySelectorAll("input").forEach(input => input.addEventListener("change", () => {
    search.languagesTouched = true;
    renderAuthorLanguages();
  }));
}

function downloadAuthor() {
  const profiles = search.authors.filter(author => search.chosen.has(author.id))
    .map(({ id, name, works_count, institutions }) => ({ id, name, works_count, institutions }));
  if (!profiles.length) return toast("Marca al menos un perfil.", true);
  const languages = checkedValues("#author-languages .lang");
  const unknown = document.getElementById("lang-unknown").checked;
  const total = profiles.reduce((sum, profile) => sum + profile.works_count, 0);
  startJob("author", { profiles, languages: { languages, unknown_language: unknown || !languages.length } },
    `¿Buscar y descargar las obras de ${mainAuthor().name} (${total} en OpenAlex, más las de otras bibliotecas)? ` +
    "Las dudosas te esperarán en «Obras dudosas».");
}

// Por título: the search is a task (it asks many libraries); then the results are chosen in #/results.

function renderTitleSearch() {
  const body = document.getElementById("search-body");
  body.innerHTML = `<form class="search-form" id="title-form">
      <input type="search" id="title-words" placeholder="Palabras del título" value="${esc(search.title)}"
        autocomplete="off" enterkeyhint="search" required>
      <button class="primary" type="submit">Buscar</button>
    </form>
    <p class="muted small">Busca en OpenAlex y en las demás bibliotecas; tarda un poco. Luego eliges qué descargar.</p>
    ${busyNote()}<div id="last-results"></div>`;
  document.getElementById("title-form").addEventListener("submit", event => {
    event.preventDefault();
    const words = document.getElementById("title-words").value.trim();
    if (!words) return;
    search.title = words;
    startJob("title_search", { words });
  });
  api("api/title_results").then(results => {
    const box = document.getElementById("last-results");
    if (box && results.words) box.innerHTML = `<a class="card link-card" href="#/results"><div class="title">Última búsqueda: «${esc(results.words)}»</div>
      <div class="muted small">${plural(results.works.length, "obra", "obras")} · elegir qué descargar ›</div></a>`;
  }).catch(() => {});
  if (!search.title) document.getElementById("title-words").focus();
}

async function renderResults() {
  const back = backLink("#/search", "Buscar");
  loading("Resultados", back);
  let data;
  try { data = await api("api/title_results"); } catch (error) { return failed("Resultados", error, back); }
  if (!data.words) { view.innerHTML = `${back}<h1>Resultados</h1><p class="empty">Todavía no has buscado por título.</p>`; return; }
  const works = data.works;
  const inCalibre = works.filter(work => work.in_calibre).length;
  view.innerHTML = `${back}<h1>«${esc(data.words)}»</h1>
    <p class="muted small">${plural(works.length, "obra", "obras")}${inCalibre ? `; ${inCalibre} ya en Calibre` : ""}.
      Las que llevan 🔗 ya traen enlace a su archivo.</p>
    ${works.length ? `<input type="search" class="filter" id="filter" placeholder="Filtrar por título, autor, año…" autocomplete="off">
    <div class="actions tight">
      <button data-mark="missing">Marcar las que no están en Calibre</button>
      <button data-mark="visible">Marcar las que se ven</button>
      <button data-mark="none">Desmarcar</button>
    </div>` : `<p class="empty">No se ha encontrado nada.</p>`}
    <div class="card ${works.length ? "" : "hidden"}"><div id="results">${works.map(work => `<label class="check" data-text="${esc([work.title, (work.authors || []).join(" "), work.year, work.source, work.publisher].join(" ").toLowerCase())}">
      <input type="checkbox" value="${work.number}" ${work.in_calibre ? "data-in-calibre" : ""}>
      <span>${workLine(work)}${work.in_calibre ? `<span class="small block ok-text">Ya en Calibre</span>` : ""}${work.has_link ? `<span class="small" title="Con enlace">🔗</span>` : ""}</span></label>`).join("")}
    </div></div>
    ${busyNote()}
    <div class="actions sticky ${works.length ? "" : "hidden"}"><button class="primary grow" id="download-chosen">Descargar las marcadas</button></div>`;

  const items = [...view.querySelectorAll("#results .check")];
  const button = document.getElementById("download-chosen");
  const update = () => {
    const count = items.filter(item => item.querySelector("input").checked).length;
    button.textContent = count ? `Descargar ${plural(count, "obra marcada", "obras marcadas")}` : "Marca las obras que quieres";
    button.disabled = !count;
  };
  view.querySelector("#results").addEventListener("change", update);
  const filter = document.getElementById("filter");
  if (filter) filter.addEventListener("input", () => {
    const words = filterWords(filter);
    items.forEach(item => item.classList.toggle("hidden", !matchesFilter(item, words)));
  });
  view.querySelectorAll("[data-mark]").forEach(mark => mark.addEventListener("click", () => {
    items.forEach(item => {
      const input = item.querySelector("input");
      if (mark.dataset.mark === "none") input.checked = false;
      else if (mark.dataset.mark === "missing") input.checked = input.checked || !input.hasAttribute("data-in-calibre");
      else if (!item.classList.contains("hidden")) input.checked = true;
    });
    update();
  }));
  button.addEventListener("click", () => {
    const chosen = items.map(item => item.querySelector("input")).filter(input => input.checked).map(input => Number(input.value));
    startJob("title_download", { words: data.words, chosen }, `¿Descargar ${plural(chosen.length, "obra", "obras")}?`);
  });
  update();
}

// Desde una bibliografía: a file (.bib, .ris, .txt) or references pasted, one per line.

function renderBibliographySearch() {
  const body = document.getElementById("search-body");
  body.innerHTML = `<p class="muted small">Se buscan todas sus obras, en cualquier idioma, y se descargan las que no están en Calibre.</p>
    <div class="card">
      <label class="field-label" for="bib-file">Un archivo BibTeX, RIS o de texto</label>
      <input type="file" id="bib-file" accept=".bib,.ris,.txt,text/plain">
      <label class="field-label" for="bib-text">… o pega las referencias, una por línea</label>
      <textarea id="bib-text" rows="7" placeholder="Arendt, H. (1958). The Human Condition. University of Chicago Press.">${esc(search.bibliographyText)}</textarea>
    </div>${busyNote()}
    <div class="actions"><button class="primary grow" id="bib-send">Buscar y descargar</button></div>`;
  const text = document.getElementById("bib-text");
  text.addEventListener("input", () => { search.bibliographyText = text.value; });
  document.getElementById("bib-send").addEventListener("click", async () => {
    const file = document.getElementById("bib-file").files[0];
    if (!file && !text.value.trim()) return toast("Elige un archivo o pega las referencias.", true);
    if (!confirm("¿Buscar y descargar las obras de esta bibliografía?")) return;
    const form = new FormData();
    if (file) form.append("file", file); else form.append("text", text.value);
    try {
      await api("api/bibliography", { method: "POST", body: form });
      search.bibliographyText = "";
      location.hash = "#/job";
      await refreshStatus();
    } catch (error) { toast(error.message, true); }
  });
}

// --- Obras dudosas ---

async function renderReviews() {
  const back = backLink("#/todo", "Pendiente");
  loading("Obras dudosas", back);
  let data;
  try { data = await api("api/reviews"); } catch (error) { return failed("Obras dudosas", error, back); }
  let html = `${back}<h1>Obras dudosas</h1>
    <p class="muted small">Internet Archive y Google Books ponen a veces el autor equivocado. Marca qué hacer con cada una;
    las que dejes sin marcar se quedan para más tarde.</p>`;
  if (!data.groups.length) html += `<p class="empty">No hay obras dudosas por revisar.</p>`;
  data.groups.forEach((group, groupNumber) => {
    html += `<h2 class="group-head"><span>${esc(group.name)} (${group.works.length})</span>
      <span><button class="link" data-all="yes" data-group="${groupNumber}">Todas sí</button>
      <button class="link" data-all="no" data-group="${groupNumber}">Todas no</button></span></h2>
      <div class="card"><ul class="list" data-group="${groupNumber}">`;
    group.works.forEach((work, number) => {
      const name = `r-${groupNumber}-${number}`;
      html += `<li data-list="${esc(group.list)}" data-key="${esc(work.key)}">${workLine(work)}
        ${work.link ? `<a class="small" href="${esc(work.link)}" target="_blank" rel="noopener noreferrer">Ver la obra ↗</a>` : ""}
        <div class="choice">
          <label><input type="radio" name="${name}" value="yes"><span class="yes">📥 Descargar</span></label>
          <label><input type="radio" name="${name}" value="no"><span class="no">🗑 Descartar</span></label>
        </div></li>`;
    });
    html += `</ul></div>`;
  });
  if (data.groups.length) html += `<div class="actions sticky"><button class="primary grow" id="save-reviews">Guardar y descargar las aceptadas</button></div>`;
  view.innerHTML = html;
  view.querySelectorAll("[data-all]").forEach(button => button.addEventListener("click", () => {
    view.querySelectorAll(`ul[data-group="${button.dataset.group}"] input[value="${button.dataset.all}"]`).forEach(input => { input.checked = true; });
  }));
  const save = document.getElementById("save-reviews");
  if (save) save.addEventListener("click", () => {
    const decisions = {};
    let count = 0;
    view.querySelectorAll("li[data-key]").forEach(item => {
      const chosen = item.querySelector("input:checked");
      if (!chosen) return;
      (decisions[item.dataset.list] ||= {})[item.dataset.key] = chosen.value === "yes";
      count++;
    });
    if (!count) return toast("No has marcado ninguna.", true);
    startJob("reviews", { decisions }, `¿Guardar ${plural(count, "decisión", "decisiones")} y descargar las aceptadas?`);
  });
}

// --- Descargar a mano ---

async function renderPending() {
  const back = backLink("#/todo", "Pendiente");
  loading("Descargar a mano", back);
  let data;
  try { data = await api("api/pending"); } catch (error) { return failed("Descargar a mano", error, back); }
  const total = data.groups.reduce((sum, group) => sum + group.works.length, 0);
  let html = `${back}<h1>Descargar a mano (${total})</h1>
    <p class="muted small">Abre la página de la obra, descarga el PDF o EPUB y súbelo aquí: se guarda con su nombre y
    sus metadatos. Luego, «Subir a Calibre».</p>`;
  if (!total) html += `<p class="empty">No hay obras pendientes.</p>`;
  else if (total > 8) html += `<input type="search" class="filter" id="filter" placeholder="Filtrar por título o autor…" autocomplete="off">`;
  data.groups.forEach(group => {
    html += `<details ${data.groups.length === 1 ? "open" : ""}><summary><span>${esc(group.name)}</span><span class="badge quiet">${group.works.length}</span></summary><div class="inner"><ul class="list">`;
    group.works.forEach(work => {
      html += `<li data-text="${esc([work.title, (work.authors || []).join(" "), work.year].join(" ").toLowerCase())}">${workLine(work)}
        <div class="upload" data-list="${esc(group.list)}" data-key="${esc(work.key)}">
          <a class="button" href="${esc(work.page)}" target="_blank" rel="noopener noreferrer">Abrir ↗</a>
          <label class="button">Subir archivo<input type="file" class="visually-hidden" accept=".pdf,.epub,application/pdf,application/epub+zip"></label>
        </div></li>`;
    });
    html += `</ul></div></details>`;
  });
  view.innerHTML = html;
  const filter = document.getElementById("filter");
  if (filter) filter.addEventListener("input", () => {
    const words = filterWords(filter);
    view.querySelectorAll("li[data-text]").forEach(item => item.classList.toggle("hidden", !matchesFilter(item, words)));
    if (words.length) view.querySelectorAll("details").forEach(details => { details.open = true; });
  });
  view.querySelectorAll(".upload input[type=file]").forEach(input => input.addEventListener("change", async () => {
    const box = input.closest(".upload");
    if (!input.files.length) return;
    const form = new FormData();
    form.append("list", box.dataset.list);
    form.append("key", box.dataset.key);
    form.append("file", input.files[0]);
    input.disabled = true;
    toast("Subiendo…");
    try {
      const answer = await api("api/pending/upload", { method: "POST", body: form });
      toast(answer.message);
      box.closest("li").remove();
      loadCounts();
    } catch (error) {
      toast(error.message, true);
      input.disabled = false;
      input.value = "";
    }
  }));
}

// --- Biblioteca ---

async function renderLibrary() {
  loading("Biblioteca", backLink());
  let data;
  try { data = await api("api/library"); } catch (error) { return failed("Biblioteca", error, backLink()); }
  let html = `${backLink()}<h1>Biblioteca</h1><p class="muted small">Los archivos que siguen en la torre (lo subido a Calibre ya no está aquí).</p>`;
  if (!data.folders.length) html += `<p class="empty">No hay ningún archivo.</p>`;
  else html += `<div class="menu">${data.folders.map(folder => `<a class="menu-item" href="#/folder/${encodeURIComponent(folder.path)}">
      <span>${esc(folder.name)}<span class="hint">${plural(folder.files, "archivo", "archivos")} · ${esc(folder.size)}</span></span><span class="chevron">›</span></a>`).join("")}</div>`;
  view.innerHTML = html;
}

async function renderFolder(path) {
  const back = backLink("#/library", "Carpetas");
  loading("Carpeta", back);
  let data;
  try { data = await api(`api/folder?path=${encodeURIComponent(path)}`); } catch (error) { return failed("Carpeta", error, back); }
  let html = `${back}<h1>${esc(path || "library")}</h1>`;
  if (!data.files.length) html += `<p class="empty">La carpeta no tiene archivos.</p>`;
  else {
    html += `<div class="card">${data.files.map(file => `<label class="check">
        <input type="checkbox" value="${esc(file.name)}">
        <span><span class="title">${file.work ? esc(file.work.title) : esc(file.name)}</span>
        <span class="muted small block">${esc(file.size)}${file.in_calibre ? " · también en Calibre" : ""}${file.work ? "" : " · sin ficha"}</span>
        <a class="small" href="file/${file.path.split("/").map(encodeURIComponent).join("/")}">Descargar</a></span></label>`).join("")}</div>
      <label class="check"><input type="checkbox" id="forget" checked><span class="small">Que no se vuelvan a descargar
        (ni al reintentar las pendientes ni en la revisión diaria)</span></label>
      <div class="actions sticky"><button class="danger grow" id="delete">Borrar los marcados</button></div>`;
  }
  view.innerHTML = html;
  const remove = document.getElementById("delete");
  if (remove) remove.addEventListener("click", async () => {
    const files = checkedValues(".card input[type=checkbox]");
    if (!files.length) return toast("No has marcado ninguno.", true);
    if (!confirm(`¿Borrar ${plural(files.length, "archivo", "archivos")}? No se pueden recuperar.`)) return;
    try {
      const answer = await post("api/delete", { folder: path, files, forget: document.getElementById("forget").checked });
      toast(answer.message, !answer.ok);
      renderFolder(path);
    } catch (error) { toast(error.message, true); }
  });
}

// --- Catálogos, autores que seguir, idiomas ---

async function renderIndexes() {
  loading("Catálogos locales", backLink());
  let data;
  try { data = await api("api/indexes"); } catch (error) { return failed("Catálogos locales", error, backLink()); }
  view.innerHTML = `${backLink()}<h1>Catálogos locales</h1>
    <p class="muted small">Copias en la torre de catálogos que se buscan sin preguntar a su web. La primera cosecha de Dialnet tarda horas.</p>
    <div class="card">${data.catalogues.map(catalogue => `<label class="check">
      <input type="checkbox" value="${esc(catalogue.key)}" checked>
      <span><span class="title">${esc(catalogue.name)}</span>
      <span class="muted small block">${catalogue.records.toLocaleString("es-ES")} registros${catalogue.updated ? ` · completo el ${esc(catalogue.updated)}` : ""}</span></span></label>`).join("")}</div>
    <div class="actions"><button class="primary grow" id="update">Actualizar los marcados</button></div>`;
  document.getElementById("update").addEventListener("click", () => {
    const names = checkedValues(".card input");
    if (!names.length) return toast("No has marcado ninguno.", true);
    startJob("indexes", { names });
  });
}

async function renderFollow() {
  loading("Autores que seguir", backLink());
  let data;
  try { data = await api("api/follow"); } catch (error) { return failed("Autores que seguir", error, backLink()); }
  let html = `${backLink()}<h1>Autores que seguir</h1>
    <p class="muted small">Cada día a las 6:00 se buscan sus obras nuevas y el archivo de las pendientes.</p>`;
  if (!data.authors.length) html += `<p class="empty">Todavía no se ha buscado ningún autor.</p>`;
  else html += `<div class="card">${data.authors.map(author => `<label class="check">
      <input type="checkbox" value="${esc(author.list)}" ${author.follow ? "checked" : ""}>
      <span><span class="title">${esc(author.name)}</span><span class="muted small block">${plural(author.works, "obra", "obras")} en su lista</span></span></label>`).join("")}</div>
    <div class="actions sticky"><button class="primary grow" id="save">Guardar</button></div>`;
  view.innerHTML = html;
  const save = document.getElementById("save");
  if (save) save.addEventListener("click", async () => {
    try { toast((await post("api/follow", { followed: checkedValues(".card input") })).message); counts = null; }
    catch (error) { toast(error.message, true); }
  });
}

async function renderLanguages() {
  loading("Idiomas", backLink());
  let data;
  try { data = await api("api/languages"); } catch (error) { return failed("Idiomas", error, backLink()); }
  const chosen = new Set(data.chosen);
  view.innerHTML = `${backLink()}<h1>Idiomas</h1>
    <p class="muted small">Ahora: ${esc(data.label)}. Sin ninguno marcado: todos. Un autor buscado con otros idiomas sigue con los suyos.</p>
    <div class="card"><div class="lang-grid">${Object.entries(data.names).map(([code, name]) => `<label class="check">
      <input type="checkbox" class="lang" value="${esc(code)}" ${chosen.has(code) ? "checked" : ""}><span>${esc(name)} <span class="muted">(${esc(code)})</span></span></label>`).join("")}</div>
      <label class="check"><input type="checkbox" id="unknown" ${data.unknown_language ? "checked" : ""}><span>Obras sin idioma conocido</span></label></div>
    <div class="actions sticky"><button class="primary grow" id="save">Guardar</button></div>`;
  document.getElementById("save").addEventListener("click", async () => {
    const languages = checkedValues(".lang");
    const unknown = document.getElementById("unknown").checked;
    try {
      toast((await post("api/languages", { languages, unknown_language: unknown })).message);
      search.languages = null;
      counts = null;
    } catch (error) { toast(error.message, true); }
  });
}

// --- navigation ---

function route() { return location.hash.replace(/^#\/?/, "").split("/")[0]; }

// The tab each page belongs to.
const TAB_OF = { "": "", search: "search", results: "search", todo: "todo", reviews: "todo", pending: "todo", job: "job" };

function render() {
  const [page, ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  view.removeEventListener("click", stopClicked);
  window.scrollTo(0, 0);
  const tab = page in TAB_OF ? TAB_OF[page] : "";
  document.querySelectorAll(".tabs a").forEach(link => link.setAttribute("aria-current", link.dataset.tab === tab ? "page" : "false"));
  const pages = {
    "": renderHome, job: renderJob, daily: renderDaily, search: renderSearch, results: renderResults, todo: renderTodo,
    reviews: renderReviews, pending: renderPending, library: renderLibrary,
    folder: () => renderFolder(decodeURIComponent(rest.join("/"))), indexes: renderIndexes,
    follow: renderFollow, languages: renderLanguages,
  };
  (pages[page] || renderHome)();
}

window.addEventListener("hashchange", () => { render(); refreshStatus(); });
document.addEventListener("visibilitychange", () => { if (document.hidden) clearTimeout(pollTimer); else refreshStatus(); });
refreshStatus().then(() => { jobWasRunning = !!(state.job || {}).running; render(); });
