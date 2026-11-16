// The web panel of paperScraper. Every address is relative to the page (/p/<session>/), which carries
// the session, so it works also on phones that don't keep the cookie.
"use strict";

const view = document.getElementById("view");
const session = (location.pathname.match(/^\/p\/([^/]+)\//) || [])[1] || "";
document.getElementById("terminal-link").href = `/s/${session}/`;

let state = { daily: {}, job: {} };
let jobWasRunning = false;

// --- helpers ---

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  if (response.status === 401) { location.href = "/login"; throw new Error("sesión caducada"); }
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

function backLink() { return `<a class="back" href="#/">← Volver</a>`; }

function loading(title) { view.innerHTML = `${backLink()}<h1>${esc(title)}</h1><p class="muted">Cargando…</p>`; }

async function startJob(task, body, question) {
  if (question && !confirm(question)) return;
  try {
    await post(`api/job/${task}`, body);
    toast("Tarea en marcha.");
    await refreshStatus();
    location.hash = "#/job";
  } catch (error) { toast(error.message, true); }
}

// --- the bar on top: always visible ---

function dailyText(daily) {
  if (daily.running) {
    const author = daily.current_author ? ` · ${daily.current_author} (${daily.authors_done})` : "";
    const since = daily.started ? ` desde las ${daily.started.slice(11)}` : "";
    return `Revisión diaria en marcha${since}${author}`;
  }
  let last = "";
  if (daily.ended) last = `Última: ${daily.ended.slice(8, 10)}/${daily.ended.slice(5, 7)} ${daily.ended.slice(11)} ${daily.ok ? "✓" : "con errores"} · `;
  return `${last}Próxima: ${daily.next || "?"}`;
}

async function refreshStatus() {
  try {
    state = await api("api/status");
  } catch (error) {
    document.getElementById("daily-text").textContent = "Sin conexión con la torre";
    document.getElementById("daily-dot").className = "dot bad";
    return;
  }
  const daily = state.daily || {};
  document.getElementById("daily-text").textContent = dailyText(daily);
  document.getElementById("daily-dot").className = "dot " + (daily.running ? "running" : daily.ended ? (daily.ok ? "ok" : "bad") : "");
  const job = state.job || {};
  const jobBar = document.getElementById("job-status");
  jobBar.classList.toggle("hidden", !job.running);
  document.getElementById("job-text").textContent = job.running ? `${job.label} · desde las ${job.started.slice(11)}` : "";
  // When a task ends, what it changed shows at once.
  if (jobWasRunning && !job.running) {
    toast(job.code === 0 ? `Terminada: ${job.label}` : `${job.label}: ha terminado con errores`, job.code !== 0);
    if (route() === "") render();
  }
  jobWasRunning = !!job.running;
  if (route() === "job") renderJobLog();
  if (route() === "daily") renderDailyLog();
}

// --- pages ---

const MENU = [
  { label: "Buscar por autor", hint: "En la terminal, de momento", terminal: true },
  { label: "Buscar por palabras del título", hint: "En la terminal, de momento", terminal: true },
  { label: "Desde una bibliografía", hint: "En la terminal, de momento", terminal: true },
  { label: "Reintentar las obras pendientes", count: "pending", task: "retry",
    question: "¿Buscar otra vez el archivo de todas las obras pendientes? Puede tardar." },
  { label: "Descargar a mano las pendientes", hint: "Ábrelas y sube aquí el archivo", count: "pending", page: "pending" },
  { label: "Subir a Calibre lo ya descargado", count: "not_uploaded", task: "upload", question: "¿Subir a Calibre lo descargado?" },
  { label: "Ver y borrar archivos de la biblioteca", page: "library" },
  { label: "Revisar obras dudosas", hint: "Internet Archive, Google Books", count: "reviews", page: "reviews" },
  { label: "Actualizar los catálogos locales", hint: "Dialnet, PhilArchive, DOAB, BNE", page: "indexes" },
  { label: "Poner metadatos a los archivos ya descargados", task: "tag",
    question: "¿Escribir los metadatos en todos los archivos descargados?" },
  { label: "Autores que seguir", hint: "Revisión diaria", count: "followed", page: "follow" },
  { label: "Idiomas", hintFrom: "languages", page: "languages" },
  { label: "Hacer la revisión diaria ahora", task: "daily",
    question: "¿Hacer ahora la revisión diaria? Mañana se hace otra vez a su hora." },
];

async function renderHome() {
  const job = state.job || {};
  view.innerHTML = `<p class="muted">Cargando…</p>`;
  let home;
  try { home = await api("api/home"); } catch (error) { view.innerHTML = `<p class="bad-text">${esc(error.message)}</p>`; return; }
  const counts = home.counts || {};

  let html = "";
  if (job.task) {
    const result = job.running ? "en marcha" : job.interrupted ? "interrumpida" : job.code === 0 ? "terminada" : "terminada con errores";
    html += `<h2>Última tarea</h2><a class="card" style="display:block;color:inherit" href="#/job">
      <div class="title">${esc(job.label)}</div>
      <div class="small ${job.running ? "" : job.code === 0 ? "ok-text" : "bad-text"}">${result} · ${esc(job.started)}</div>
      <pre class="log short">${esc((job.log || []).slice(-6).join("\n"))}</pre></a>`;
  }

  html += `<h2>Últimas descargas</h2><div class="card">`;
  if (home.downloads.length) {
    html += `<ul class="list">${home.downloads.map(item => `<li>
      <div class="title">${esc(item.title)}</div>
      <div class="muted small">${esc([(item.authors || []).join(", "), item.year, item.source || item.how, (item.folder || "").replace(/\s*\([^)]*\)$/, "")].filter(Boolean).join(" · "))}</div>
      <div class="muted small">${esc(item.time.replace("T", " ").slice(0, 16))}</div></li>`).join("")}</ul>`;
  } else {
    html += `<p class="empty">Todavía no hay descargas apuntadas. Desde ahora, cada descarga sale aquí.</p>`;
  }
  html += `</div><h2>Menú</h2><div class="menu">`;
  MENU.forEach((item, number) => {
    const count = item.count ? counts[item.count] : null;
    const hint = item.hintFrom ? home[item.hintFrom] : item.hint;
    const badge = count != null ? `<span class="badge ${count ? "" : "quiet"}">${count}</span>` : item.terminal ? `<span class="badge quiet">›_</span>` : "";
    html += `<button class="menu-item" data-item="${number}"><span>${esc(item.label)}${hint ? `<span class="hint">${esc(hint)}</span>` : ""}</span>${badge}</button>`;
  });
  html += `</div>`;
  view.innerHTML = html;
  view.querySelectorAll(".menu-item").forEach(button => button.addEventListener("click", () => {
    const item = MENU[Number(button.dataset.item)];
    if (item.terminal) location.href = `/s/${session}/`;
    else if (item.page) location.hash = `#/${item.page}`;
    else if (item.task) startJob(item.task, {}, item.question);
  }));
}

function renderJob() {
  view.innerHTML = `${backLink()}<h1 id="job-title"></h1><p class="small" id="job-state"></p>
    <pre class="log" id="job-log"></pre>
    <div class="actions"><button class="danger hidden" id="job-stop">Parar la tarea</button></div>`;
  document.getElementById("job-stop").addEventListener("click", async () => {
    if (!confirm("¿Parar la tarea? Lo ya descargado se queda.")) return;
    try { await post("api/job/stop"); toast("Parando…"); } catch (error) { toast(error.message, true); }
  });
  renderJobLog();
}

function renderJobLog() {
  const job = state.job || {};
  const title = document.getElementById("job-title");
  if (!title) return;
  title.textContent = job.label || "Ninguna tarea todavía";
  const result = !job.task ? "" : job.running ? `En marcha desde ${job.started}` : job.interrupted ? "Interrumpida (se reinició el panel)"
    : `${job.code === 0 ? "Terminada" : "Terminada con errores"} · ${job.started} → ${job.finished}`;
  document.getElementById("job-state").textContent = result;
  document.getElementById("job-stop").classList.toggle("hidden", !job.running);
  showLog(document.getElementById("job-log"), job.log || []);
}

function renderDaily() {
  view.innerHTML = `${backLink()}<h1>Revisión diaria</h1><p class="small" id="daily-state"></p>
    <pre class="log" id="daily-log"></pre>
    <div class="actions"><button id="daily-now">Hacer la revisión ahora</button></div>`;
  document.getElementById("daily-now").addEventListener("click", () =>
    startJob("daily", {}, "¿Hacer ahora la revisión diaria? Mañana se hace otra vez a su hora."));
  renderDailyLog();
}

function renderDailyLog() {
  const daily = state.daily || {};
  const element = document.getElementById("daily-state");
  if (!element) return;
  element.textContent = dailyText(daily);
  document.getElementById("daily-now").disabled = !!daily.running;
  showLog(document.getElementById("daily-log"), daily.log_tail || ["Todavía no hay ningún log de la revisión diaria."]);
}

function showLog(element, lines) {
  // Keep following the end, unless the user scrolled up to read.
  const atEnd = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
  const text = lines.join("\n");
  if (element.textContent !== text) {
    element.textContent = text;
    if (atEnd) element.scrollTop = element.scrollHeight;
  }
}

async function renderReviews() {
  loading("Obras dudosas");
  let data;
  try { data = await api("api/reviews"); } catch (error) { return toast(error.message, true); }
  let html = `${backLink()}<h1>Obras dudosas</h1>
    <p class="muted small">Internet Archive y Google Books ponen a veces el autor equivocado. Marca qué hacer con cada una;
    las que dejes sin marcar se quedan para más tarde.</p>`;
  if (!data.groups.length) html += `<p class="empty">No hay obras dudosas por revisar.</p>`;
  data.groups.forEach((group, groupNumber) => {
    html += `<h2>${esc(group.name)} (${group.works.length})</h2><div class="card"><ul class="list">`;
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
  if (data.groups.length) html += `<div class="actions sticky"><button class="primary" id="save-reviews">Guardar y descargar las aceptadas</button></div>`;
  view.innerHTML = html;
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
    startJob("reviews", { decisions }, `¿Guardar ${count} decisiones y descargar las aceptadas?`);
  });
}

async function renderPending() {
  loading("Pendientes");
  let data;
  try { data = await api("api/pending"); } catch (error) { return toast(error.message, true); }
  const total = data.groups.reduce((sum, group) => sum + group.works.length, 0);
  let html = `${backLink()}<h1>Pendientes (${total})</h1>
    <p class="muted small">Abre la página de la obra, descarga el PDF o EPUB y súbelo aquí: se guarda con su nombre y
    sus metadatos. Luego, «Subir a Calibre».</p>`;
  if (!total) html += `<p class="empty">No hay obras pendientes.</p>`;
  data.groups.forEach(group => {
    html += `<details><summary><span>${esc(group.name)}</span><span class="badge quiet">${group.works.length}</span></summary><div class="inner"><ul class="list">`;
    group.works.forEach(work => {
      html += `<li>${workLine(work)}
        <div class="upload" data-list="${esc(group.list)}" data-key="${esc(work.key)}">
          <a class="button" href="${esc(work.page)}" target="_blank" rel="noopener noreferrer">Abrir ↗</a>
          <input type="file" accept=".pdf,.epub,application/pdf,application/epub+zip" aria-label="Archivo de la obra">
        </div></li>`;
    });
    html += `</ul></div></details>`;
  });
  view.innerHTML = html;
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
    } catch (error) {
      toast(error.message, true);
      input.disabled = false;
      input.value = "";
    }
  }));
}

async function renderLibrary() {
  loading("Biblioteca");
  let data;
  try { data = await api("api/library"); } catch (error) { return toast(error.message, true); }
  let html = `${backLink()}<h1>Biblioteca</h1><p class="muted small">Los archivos que siguen en la torre (lo subido a Calibre ya no está aquí).</p>`;
  if (!data.folders.length) html += `<p class="empty">No hay ningún archivo.</p>`;
  else html += `<div class="menu">${data.folders.map(folder => `<a class="menu-item" href="#/folder/${encodeURIComponent(folder.path)}">
      <span>${esc(folder.name)}<span class="hint">${folder.files} archivos · ${esc(folder.size)}</span></span><span>›</span></a>`).join("")}</div>`;
  view.innerHTML = html;
}

async function renderFolder(path) {
  loading("Carpeta");
  let data;
  try { data = await api(`api/folder?path=${encodeURIComponent(path)}`); } catch (error) { return toast(error.message, true); }
  let html = `<a class="back" href="#/library">← Carpetas</a><h1>${esc(path || "library")}</h1>`;
  if (!data.files.length) html += `<p class="empty">La carpeta no tiene archivos.</p>`;
  else {
    html += `<div class="card">${data.files.map(file => `<label class="check">
        <input type="checkbox" value="${esc(file.name)}">
        <span><span class="title">${file.work ? esc(file.work.title) : esc(file.name)}</span>
        <span class="muted small" style="display:block">${esc(file.size)}${file.in_calibre ? " · también en Calibre" : ""}${file.work ? "" : " · sin ficha"}</span>
        <a class="small" href="file/${file.path.split("/").map(encodeURIComponent).join("/")}">Descargar</a></span></label>`).join("")}</div>
      <label class="check"><input type="checkbox" id="forget" checked><span class="small">Que no se vuelvan a descargar
        (ni al reintentar las pendientes ni en la revisión diaria)</span></label>
      <div class="actions sticky"><button class="danger" id="delete">Borrar los marcados</button></div>`;
  }
  view.innerHTML = html;
  const remove = document.getElementById("delete");
  if (remove) remove.addEventListener("click", async () => {
    const files = [...view.querySelectorAll(".card input:checked")].map(input => input.value);
    if (!files.length) return toast("No has marcado ninguno.", true);
    if (!confirm(`¿Borrar ${files.length} archivos? No se pueden recuperar.`)) return;
    try {
      const answer = await post("api/delete", { folder: path, files, forget: document.getElementById("forget").checked });
      toast(answer.message, !answer.ok);
      renderFolder(path);
    } catch (error) { toast(error.message, true); }
  });
}

async function renderIndexes() {
  loading("Catálogos locales");
  let data;
  try { data = await api("api/indexes"); } catch (error) { return toast(error.message, true); }
  view.innerHTML = `${backLink()}<h1>Catálogos locales</h1>
    <p class="muted small">Copias en la torre de catálogos que se buscan sin preguntar a su web. La primera cosecha de Dialnet tarda horas.</p>
    <div class="card">${data.catalogues.map(catalogue => `<label class="check">
      <input type="checkbox" value="${esc(catalogue.key)}" checked>
      <span><span class="title">${esc(catalogue.name)}</span>
      <span class="muted small" style="display:block">${catalogue.records.toLocaleString("es-ES")} registros${catalogue.updated ? ` · completo el ${esc(catalogue.updated)}` : ""}</span></span></label>`).join("")}</div>
    <div class="actions"><button class="primary" id="update">Actualizar los marcados</button></div>`;
  document.getElementById("update").addEventListener("click", () => {
    const names = [...view.querySelectorAll("input:checked")].map(input => input.value);
    if (!names.length) return toast("No has marcado ninguno.", true);
    startJob("indexes", { names });
  });
}

async function renderFollow() {
  loading("Autores que seguir");
  let data;
  try { data = await api("api/follow"); } catch (error) { return toast(error.message, true); }
  let html = `${backLink()}<h1>Autores que seguir</h1>
    <p class="muted small">Cada día a las 6:00 se buscan sus obras nuevas y el archivo de las pendientes.</p>`;
  if (!data.authors.length) html += `<p class="empty">Todavía no se ha buscado ningún autor.</p>`;
  else html += `<div class="card">${data.authors.map(author => `<label class="check">
      <input type="checkbox" value="${esc(author.list)}" ${author.follow ? "checked" : ""}>
      <span><span class="title">${esc(author.name)}</span><span class="muted small" style="display:block">${author.works} obras en su lista</span></span></label>`).join("")}</div>
    <div class="actions sticky"><button class="primary" id="save">Guardar</button></div>`;
  view.innerHTML = html;
  const save = document.getElementById("save");
  if (save) save.addEventListener("click", async () => {
    const followed = [...view.querySelectorAll("input:checked")].map(input => input.value);
    try { toast((await post("api/follow", { followed })).message); } catch (error) { toast(error.message, true); }
  });
}

async function renderLanguages() {
  loading("Idiomas");
  let data;
  try { data = await api("api/languages"); } catch (error) { return toast(error.message, true); }
  const chosen = new Set(data.chosen);
  view.innerHTML = `${backLink()}<h1>Idiomas</h1>
    <p class="muted small">Ahora: ${esc(data.label)}. Sin ninguno marcado: todos. Un autor buscado con otros idiomas sigue con los suyos.</p>
    <div class="card">${Object.entries(data.names).map(([code, name]) => `<label class="check">
      <input type="checkbox" value="${esc(code)}" ${chosen.has(code) ? "checked" : ""}><span>${esc(name)} <span class="muted">(${esc(code)})</span></span></label>`).join("")}
      <label class="check"><input type="checkbox" id="unknown" ${data.unknown_language ? "checked" : ""}><span>Obras sin idioma conocido</span></label></div>
    <div class="actions sticky"><button class="primary" id="save">Guardar</button></div>`;
  document.getElementById("save").addEventListener("click", async () => {
    const languages = [...view.querySelectorAll(".card input:checked")].map(input => input.value).filter(code => code !== "on");
    const unknown = document.getElementById("unknown").checked;
    try { toast((await post("api/languages", { languages, unknown_language: unknown })).message); } catch (error) { toast(error.message, true); }
  });
}

// --- navigation ---

function route() { return location.hash.replace(/^#\/?/, "").split("/")[0]; }

function render() {
  const [page, ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  window.scrollTo(0, 0);
  const pages = {
    "": renderHome, job: renderJob, daily: renderDaily, reviews: renderReviews, pending: renderPending,
    library: renderLibrary, folder: () => renderFolder(decodeURIComponent(rest.join("/"))), indexes: renderIndexes,
    follow: renderFollow, languages: renderLanguages,
  };
  (pages[page] || renderHome)();
}

window.addEventListener("hashchange", render);
refreshStatus().then(render);
// Faster while something runs; slower when the phone shows another tab.
setInterval(() => { if (!document.hidden) refreshStatus(); }, 3000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshStatus(); });
