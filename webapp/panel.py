"""The web panel: the state of the daily check, the latest downloads and the menu options, for the phone.

tower/web_login.py serves it at /p/<session>/ after the login, next to the terminal (/s/<session>/).
The page (static/) asks this for data (api/...) and sends the user's choices. The long options run as
tasks (webapp/jobs.py), one at a time, in their own process; the quick ones (languages, authors to
follow, deleting a file) are done here at once.

Nothing that changes the lists runs while the daily check does: both would write the same files.
"""
import asyncio
import datetime as dt
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

from aiohttp import web

import download_history
from downloader import EXTENSIONS, file_extension, is_downloaded, save_file
from languages import (LANGUAGE_NAMES, current_choice, languages_label, load_settings, paper_language_allowed,
                       save_settings, using_languages)
from library_browser import folder_files, folders_with_files, human_size, papers_by_file, remove_files
from manual_download import work_page
from reviews import needs_review
import daily_reports
import task_progress
from run_lock import daily_check_running
from storage import find_saved_lists, load_content, load_papers, set_follow, update_papers, work_key
from update_indexes import INDEXED_SOURCES
from webapp import jobs
from webapp.jobs import BIBLIOGRAPHY_FOLDER, TASKS, TITLE_RESULTS

REPO = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
LIBRARY = Path("library")
WEB_FOLDER = LIBRARY / ".web"
JOB_LOG = WEB_FOLDER / "job.log"
JOB_STATE = WEB_FOLDER / "job.json"
JOB_ARGUMENTS = WEB_FOLDER / "job_arguments.json"
# What the task and the daily check are doing, as numbers (task_progress.py; the second, tower/scheduler.py).
JOB_PROGRESS = WEB_FOLDER / "job_progress.json"
DAILY_PROGRESS = WEB_FOLDER / "daily_progress.json"
DAILY_LOGS = LIBRARY / ".logs"
DAILY_LAST_RUN = LIBRARY / ".daily_check.last"
DAILY_RUN_AT = dt.time(6, 0)
LATEST_DOWNLOADS = 15
# The reports of the daily check shown in its page: about a month.
DAILY_REPORTS_SHOWN = 30
LOG_LINES_SHOWN = 400
# The lock is asked for at most this often, however many pages are open.
DAILY_STATE_SECONDS = 5
# A file uploaded from the phone can be a whole scanned book.
MAX_UPLOAD_BYTES = 300 * 1024 * 1024
MAX_BIBLIOGRAPHY_BYTES = 5 * 1024 * 1024
# "Parar la tarea" first asks as Ctrl+C does (the task saves what it did); if it doesn't end, it is ended.
STOP_GRACE_SECONDS = 45
# The works of an author shown before choosing it, as in the menu.
PREVIEW_WORKS = 15


class Panel:
    def __init__(self):
        self.process: asyncio.subprocess.Process | None = None
        self.job = self.load_job()
        self.daily_checked_at = 0.0
        self.daily_running = False

    # --- the page ---

    async def page(self, request: web.Request) -> web.Response:
        return web.FileResponse(STATIC / "index.html", headers=NO_STORE)

    async def static(self, request: web.Request) -> web.Response:
        path = (STATIC / request.match_info["name"]).resolve()
        if not path.is_relative_to(STATIC) or not path.is_file():
            raise web.HTTPNotFound()
        # Kept by the phone, but asked again each time (a short "not modified" answer after an update).
        return web.FileResponse(path, headers={"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"})

    # --- what is happening now ---

    def is_daily_running(self) -> bool:
        if time.monotonic() - self.daily_checked_at > DAILY_STATE_SECONDS:
            self.daily_running = daily_check_running()
            self.daily_checked_at = time.monotonic()
        return self.daily_running

    async def status(self, request: web.Request) -> web.Response:
        # The logs only for the page that shows them: the bar on top polls this every few seconds.
        wanted = request.query.get("log")
        daily = self.daily_state()
        if wanted != "daily":
            daily.pop("log_tail", None)
        return json_response({"daily": daily, "job": self.job_state(with_log=wanted == "job")})

    def daily_state(self) -> dict:
        running = self.is_daily_running()
        log_files = sorted(DAILY_LOGS.glob("daily-*.log")) if DAILY_LOGS.exists() else []
        state = {"running": running, "next": next_daily_run(), "progress": task_progress.read(DAILY_PROGRESS)}
        if not log_files:
            return state
        lines = log_files[-1].read_text(encoding="utf-8", errors="replace").splitlines()
        # The file of a day can have several checks; the last one counts.
        starts = [number for number, line in enumerate(lines) if line.endswith(" Revisión diaria")]
        lines = lines[starts[-1]:] if starts else lines
        authors = [lines[number + 1] for number in range(len(lines) - 2)
                   if lines[number].startswith("=====") and lines[number + 2].startswith("=====")]
        state["started"] = lines[0][:16] if starts else None
        state["authors_done"] = len(authors)
        state["current_author"] = re.sub(r"\s*\([^)]*\)$", "", authors[-1]) if authors else None
        state["last_line"] = next((line.strip() for line in reversed(lines) if line.strip()), "")
        end = next((line for line in reversed(lines) if " Fin (código " in line), None)
        if end:
            state["ended"] = end[:16]
            state["ok"] = end.rstrip(")").endswith("código 0")
        state["log_tail"] = lines[-LOG_LINES_SHOWN:]
        return state

    # --- the tasks ---

    def job_state(self, with_log: bool = True) -> dict:
        state = dict(self.job or {})
        if state:
            log = tail(JOB_LOG, LOG_LINES_SHOWN if with_log else 8)
            state["last_line"] = next((line.strip() for line in reversed(log) if line.strip()), "")
            if with_log:
                state["log"] = log
            # The daily check started from the panel writes its numbers where the one at 6:00 does.
            state["progress"] = task_progress.read(DAILY_PROGRESS if state.get("task") == "daily" else JOB_PROGRESS)
        return state

    def load_job(self) -> dict | None:
        try:
            job = json.loads(JOB_STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        # A task still "running" in the file was stopped when the panel restarted.
        if job.get("running"):
            job.update(running=False, finished=job.get("started"), code=None, interrupted=True)
        return job

    def save_job(self) -> None:
        WEB_FOLDER.mkdir(parents=True, exist_ok=True)
        JOB_STATE.write_text(json.dumps(self.job, ensure_ascii=False), encoding="utf-8")

    async def start_job(self, request: web.Request) -> web.Response:
        task = request.match_info["task"]
        if task not in TASKS:
            raise web.HTTPNotFound()
        arguments = await request.json() if request.can_read_body else {}
        return await self.launch(task, arguments if isinstance(arguments, dict) else {})

    def busy(self) -> str | None:
        """Why no task can start now, or None."""
        if self.process and self.process.returncode is None:
            return f"Ya hay una tarea en marcha: {self.job['label']}."
        if self.is_daily_running():
            return "La revisión diaria está en marcha; espera a que termine."
        return None

    async def launch(self, task: str, arguments: dict) -> web.Response:
        reason = self.busy()
        if reason:
            return refuse(reason)
        WEB_FOLDER.mkdir(parents=True, exist_ok=True)
        # In a file: a long list of choices doesn't fit in the command line.
        JOB_ARGUMENTS.write_text(json.dumps(arguments, ensure_ascii=False), encoding="utf-8")
        log = JOB_LOG.open("w", encoding="utf-8")
        JOB_PROGRESS.unlink(missing_ok=True)
        environment = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
                       task_progress.ENVIRONMENT_VARIABLE: str(JOB_PROGRESS.resolve())}
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "webapp.jobs", task, f"@{JOB_ARGUMENTS}",
            stdout=log, stderr=asyncio.subprocess.STDOUT, stdin=asyncio.subprocess.DEVNULL, env=environment)
        log.close()
        self.job = {"task": task, "label": jobs.label(task, arguments), "running": True, "started": now_text()}
        self.save_job()
        asyncio.get_running_loop().create_task(self.wait_job(self.process))
        return json_response({"ok": True})

    async def wait_job(self, process: asyncio.subprocess.Process) -> None:
        code = await process.wait()
        if process is self.process:
            # Stopped by the user, even if it ended well (it saved what it had, as after Ctrl+C).
            stopped = self.job.pop("stopping", False)
            self.job.update(running=False, finished=now_text(), code=code, stopped=stopped)
            self.save_job()

    async def stop_job(self, request: web.Request) -> web.Response:
        process = self.process
        if process and process.returncode is None:
            if os.name == "nt":
                process.terminate()
            else:
                process.send_signal(signal.SIGINT)
                asyncio.get_running_loop().create_task(self.end_if_still_running(process))
            self.job["stopping"] = True
        return json_response({"ok": True})

    async def end_if_still_running(self, process: asyncio.subprocess.Process) -> None:
        try:
            await asyncio.wait_for(process.wait(), STOP_GRACE_SECONDS)
        except asyncio.TimeoutError:
            process.terminate()

    # --- searches ---

    async def find_authors(self, request: web.Request) -> web.Response:
        """The OpenAlex profiles with that name, and what the library already has of each one."""
        name = request.query.get("name", "").strip()
        if not name:
            return refuse("Escribe un nombre.")
        try:
            from sources.openalex import OpenAlexSource

            authors = await asyncio.get_running_loop().run_in_executor(None, OpenAlexSource().find_authors, name)
        except Exception as error:
            return refuse(f"OpenAlex no responde: {error}")
        known = {}
        for papers_file, content, papers in load_lists():
            for profile in content.get("profiles") or ([content["author"]] if "author" in content else []):
                known[profile.get("id")] = {"list": relative(papers_file), "name": list_name(papers_file, content),
                                            "works": len(papers), "follow": bool(content.get("follow")),
                                            "language_choice": content.get("language_choice")}
        return json_response({"authors": [{
            "id": author.id, "name": author.name, "works_count": author.works_count,
            "institutions": author.institutions, "known": known.get(author.id)} for author in authors]})

    async def author_works(self, request: web.Request) -> web.Response:
        """The most cited works of an OpenAlex profile, to tell who it is."""
        author_id = request.query.get("id", "")
        if not re.fullmatch(r"https://openalex\.org/A\d+", author_id):
            return refuse("No es un autor de OpenAlex.")
        try:
            from models import Author
            from sources.openalex import OpenAlexSource

            author = Author(id=author_id, name="", works_count=0, institutions=[])
            papers = await asyncio.get_running_loop().run_in_executor(
                None, OpenAlexSource().get_top_papers, author, PREVIEW_WORKS)
        except Exception as error:
            return refuse(f"OpenAlex no responde: {error}")
        return json_response({"works": [work_data(paper) for paper in papers]})

    async def title_results(self, request: web.Request) -> web.Response:
        """The works found by the last search by title, to choose which to download."""
        from models import Paper

        try:
            results = json.loads(TITLE_RESULTS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return json_response({"words": None, "works": []})
        works = []
        for number, fields in enumerate(results.get("papers") or []):
            paper = Paper(**fields)
            works.append({**work_data(paper), "number": number, "in_calibre": paper.in_calibre,
                          "has_link": bool(paper.pdf_urls)})
        return json_response({"words": results.get("words"), "works": works})

    async def send_bibliography(self, request: web.Request) -> web.Response:
        """A bibliography sent as a file or pasted as text: it is saved and its works are downloaded."""
        reason = self.busy()
        if reason:
            return refuse(reason)
        try:
            form = await request.post()
        except UnicodeDecodeError:
            return refuse("El texto no está en UTF-8: guárdalo en un archivo y envía el archivo.")
        upload = form.get("file")
        if hasattr(upload, "file"):
            content = upload.file.read(MAX_BIBLIOGRAPHY_BYTES + 1)
            name = Path(upload.filename or "bibliografia.txt").name
        else:
            content = str(form.get("text") or "").encode("utf-8")
            name = "bibliografia.txt"
        if not content.strip():
            return refuse("La bibliografía está vacía.")
        if len(content) > MAX_BIBLIOGRAPHY_BYTES:
            return refuse("El archivo es demasiado grande para ser una bibliografía.")
        stem, suffix = os.path.splitext(name)
        suffix = suffix.lower() if suffix.lower() in (".bib", ".ris", ".txt") else ".txt"
        stem = re.sub(r"[^\w .,()-]", "", stem).strip() or "bibliografia"
        # The day and time in the name: each bibliography sent gets its own list (two pasted ones too).
        name = f"{stem[:80]} {dt.datetime.now():%Y-%m-%d %H.%M}{suffix}"
        BIBLIOGRAPHY_FOLDER.mkdir(parents=True, exist_ok=True)
        (BIBLIOGRAPHY_FOLDER / name).write_bytes(content)
        return await self.launch("bibliography", {"file": name})

    # --- the home page: latest downloads and what is waiting ---

    async def home(self, request: web.Request) -> web.Response:
        lists = load_lists()
        counts = {"pending": 0, "reviews": 0, "followed": 0, "not_uploaded": 0}
        for papers_file, content, papers in lists:
            folder = papers_file.parent
            counts["followed"] += bool(content.get("follow"))
            with using_languages(content.get("language_choice")):
                for paper in papers:
                    if paper.in_calibre:
                        continue
                    downloaded = is_downloaded(paper, folder)
                    counts["not_uploaded"] += downloaded
                    if needs_review(paper, folder):
                        counts["reviews"] += 1
                    elif paper.wanted and not downloaded and paper_language_allowed(paper):
                        counts["pending"] += 1
        return json_response({
            "downloads": download_history.latest(LATEST_DOWNLOADS),
            "daily_report": next(iter(daily_reports.latest(1)), None),
            "counts": counts,
            "languages": languages_label(),
        })

    async def daily_report_list(self, request: web.Request) -> web.Response:
        return json_response({"reports": daily_reports.latest(DAILY_REPORTS_SHOWN)})

    # --- doubtful works ---

    async def reviews(self, request: web.Request) -> web.Response:
        groups = []
        for papers_file, content, papers in load_lists():
            folder = papers_file.parent
            works = [work_data(paper) for paper in papers if needs_review(paper, folder)]
            if works:
                groups.append({"list": relative(papers_file), "name": list_name(papers_file, content),
                               "works": works})
        return json_response({"groups": groups})

    # --- pending works, to download by hand ---

    async def pending(self, request: web.Request) -> web.Response:
        groups = []
        for papers_file, content, papers in load_lists():
            folder = papers_file.parent
            with using_languages(content.get("language_choice")):
                works = [{**work_data(paper), "page": work_page(paper)} for paper in papers
                         if paper.wanted and not paper.in_calibre and not is_downloaded(paper, folder)
                         and paper_language_allowed(paper) and not needs_review(paper, folder)]
            if works:
                groups.append({"list": relative(papers_file), "name": list_name(papers_file, content),
                               "works": works})
        return json_response({"groups": groups})

    async def upload_file(self, request: web.Request) -> web.Response:
        """A file of a pending work, downloaded by the user on their phone or computer."""
        if self.is_daily_running():
            return refuse("La revisión diaria está en marcha; espera a que termine.")
        form = await request.post()
        papers_file = library_path(str(form.get("list", "")))
        upload = form.get("file")
        if papers_file is None or not papers_file.is_file() or not hasattr(upload, "file"):
            return refuse("Falta la obra o el archivo.")
        content = upload.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            return refuse("El archivo es demasiado grande.")
        extension = file_extension(content)
        if extension not in EXTENSIONS:
            return refuse("No es un PDF ni un EPUB.")
        folder = papers_file.parent
        papers = load_papers(papers_file)
        paper = next((paper for paper in papers if work_key(paper) == form.get("key")), None)
        if paper is None:
            return refuse("No encuentro esa obra en su lista.")
        save_file(content, extension, paper, folder)
        paper.downloaded = True
        update_papers(papers_file, papers)
        download_history.record(paper, folder, "subida desde la web")
        return json_response({"ok": True, "message": "Guardado. Con «Subir a Calibre» pasa a la biblioteca."})

    # --- authors followed by the daily check ---

    async def follow(self, request: web.Request) -> web.Response:
        authors = [{"list": relative(papers_file), "name": list_name(papers_file, content),
                    "follow": bool(content.get("follow")), "works": len(papers)}
                   for papers_file, content, papers in load_lists() if "author" in content]
        return json_response({"authors": authors})

    async def save_follow(self, request: web.Request) -> web.Response:
        if self.is_daily_running():
            return refuse("La revisión diaria está en marcha; espera a que termine.")
        followed = set((await request.json()).get("followed") or [])
        count = 0
        for papers_file in find_saved_lists(LIBRARY):
            content = load_content(papers_file)
            if "author" not in content:
                continue
            follow = relative(papers_file) in followed
            count += follow
            if content.get("follow", False) != follow:
                set_follow(papers_file, follow)
        return json_response({"ok": True, "message": f"Se revisan cada día {count} autores."})

    # --- languages ---

    async def languages(self, request: web.Request) -> web.Response:
        choice = current_choice()
        return json_response({"names": LANGUAGE_NAMES, "chosen": choice["languages"],
                              "unknown_language": bool(choice["languages"]) and choice["unknown_language"],
                              "label": languages_label()})

    async def save_languages(self, request: web.Request) -> web.Response:
        answer = await request.json()
        chosen = set(current_choice()["languages"])
        # Codes chosen before that the panel doesn't offer (edited by hand) are kept, as in the menu.
        languages = sorted({code for code in answer.get("languages") or [] if code in LANGUAGE_NAMES}
                           | (chosen - set(LANGUAGE_NAMES)))
        settings = load_settings()
        settings.update({"languages": languages, "unknown_language": bool(answer.get("unknown_language")) or not languages})
        save_settings(settings)
        return json_response({"ok": True, "message": f"Idiomas: {languages_label()}."})

    # --- the files of the library ---

    async def library(self, request: web.Request) -> web.Response:
        folders = []
        if LIBRARY.exists():
            for folder in folders_with_files(LIBRARY):
                files = folder_files(folder)
                folders.append({"path": relative(folder), "name": "library" if folder == LIBRARY else relative(folder),
                                "files": len(files), "size": human_size(sum(path.stat().st_size for path in files))})
        return json_response({"folders": folders})

    async def folder(self, request: web.Request) -> web.Response:
        folder = library_path(request.query.get("path", ""))
        if folder is None or not folder.is_dir():
            raise web.HTTPNotFound()
        _, _, paper_of = papers_by_file(folder)
        files = []
        for path in folder_files(folder):
            paper = paper_of.get(path)
            files.append({"name": path.name, "path": relative(path), "size": human_size(path.stat().st_size),
                          "work": work_data(paper) if paper else None,
                          "in_calibre": bool(paper and paper.in_calibre)})
        return json_response({"path": relative(folder), "files": files})

    async def delete_files(self, request: web.Request) -> web.Response:
        if self.is_daily_running():
            return refuse("La revisión diaria está en marcha; espera a que termine.")
        answer = await request.json()
        folder = library_path(answer.get("folder", ""))
        if folder is None or not folder.is_dir():
            return refuse("No encuentro esa carpeta.")
        papers_file, papers, paper_of = papers_by_file(folder)
        names = set(answer.get("files") or [])
        chosen = [path for path in folder_files(folder) if path.name in names]
        deleted, errors = remove_files(chosen, LIBRARY, papers_file, papers, paper_of, bool(answer.get("forget")))
        return json_response({"ok": not errors, "message": f"Borrados {deleted} archivos." + "".join(
            f"\n✗ {error}" for error in errors)})

    async def file(self, request: web.Request) -> web.Response:
        path = library_path(request.match_info["path"])
        # Only the files the panel lists: not the program's own (hidden folders, papers.json).
        if path is None or not path.is_file() or path not in folder_files(path.parent) \
                or any(part.startswith(".") for part in Path(relative(path)).parts):
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={**NO_STORE, "Content-Disposition": "attachment"})

    # --- local catalogues ---

    async def indexes(self, request: web.Request) -> web.Response:
        from local_index import LocalIndex

        catalogues = []
        for key, source_type in INDEXED_SOURCES.items():
            index = LocalIndex(source_type.name)
            catalogues.append({"key": key, "name": source_type.name, "records": index.count(),
                               "updated": (index.get_state("last_complete") or "")[:10] or None})
            index.database.close()
        return json_response({"catalogues": catalogues})


def load_lists() -> list[tuple[Path, dict, list]]:
    lists = []
    for papers_file in find_saved_lists(LIBRARY) if LIBRARY.exists() else []:
        try:
            content = load_content(papers_file)
            lists.append((papers_file, content, load_papers(papers_file)))
        except (OSError, ValueError, TypeError):
            continue
    return lists


def list_name(papers_file: Path, content: dict) -> str:
    return re.sub(r"\s*\([^)]*\)$", "", papers_file.parent.name) if "author" in content else papers_file.parent.name


def work_data(paper) -> dict:
    return {"key": work_key(paper), "title": paper.title, "year": paper.year, "authors": paper.authors[:3],
            "source": paper.source or "OpenAlex", "language": paper.language,
            "publisher": paper.journal or paper.publisher, "link": paper.pdf_urls[0] if paper.pdf_urls else None}


def relative(path: Path) -> str:
    """The path as the page names it: from the library's folder, with "/"."""
    text = path.resolve().relative_to(LIBRARY.resolve()).as_posix()
    return "" if text == "." else text


def library_path(text: str) -> Path | None:
    """The path inside the library that the page names, or None if it points outside it."""
    path = (LIBRARY / text).resolve()
    return path if path.is_relative_to(LIBRARY.resolve()) else None


def next_daily_run() -> str:
    today = dt.date.today()
    try:
        done_today = DAILY_LAST_RUN.read_text().strip() == today.isoformat()
    except OSError:
        done_today = False
    day = today + dt.timedelta(days=1) if done_today or dt.datetime.now().time() >= DAILY_RUN_AT else today
    return f"{'mañana' if day != today else 'hoy'} a las {DAILY_RUN_AT:%H:%M}"


def tail(path: Path, count: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
    except OSError:
        return []


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def json_response(data: dict) -> web.Response:
    return web.json_response(data, headers=NO_STORE, dumps=lambda value: json.dumps(value, ensure_ascii=False))


def refuse(message: str) -> web.Response:
    return web.json_response({"ok": False, "message": message}, status=409, headers=NO_STORE,
                             dumps=lambda value: json.dumps(value, ensure_ascii=False))


@web.middleware
async def same_origin_only(request: web.Request, handler):
    """Only the panel's own page may change things (no form on another website)."""
    if request.method == "POST":
        origin = request.headers.get("Origin", "")
        if origin and origin.split("://")[-1] != request.host:
            raise web.HTTPForbidden()
    return await handler(request)


def add_routes(app: web.Application, prefix: str, check) -> None:
    """Add the panel's addresses under `prefix` ("/p/{session}"); `check` refuses an invalid session."""
    panel = Panel()
    routes = [
        ("GET", "/", panel.page),
        ("GET", "/static/{name}", panel.static),
        ("GET", "/api/status", panel.status),
        ("GET", "/api/home", panel.home),
        ("GET", "/api/daily_reports", panel.daily_report_list),
        ("GET", "/api/authors", panel.find_authors),
        ("GET", "/api/author_works", panel.author_works),
        ("GET", "/api/title_results", panel.title_results),
        ("POST", "/api/bibliography", panel.send_bibliography),
        ("POST", "/api/job/stop", panel.stop_job),
        ("POST", "/api/job/{task}", panel.start_job),
        ("GET", "/api/reviews", panel.reviews),
        ("GET", "/api/pending", panel.pending),
        ("POST", "/api/pending/upload", panel.upload_file),
        ("GET", "/api/follow", panel.follow),
        ("POST", "/api/follow", panel.save_follow),
        ("GET", "/api/languages", panel.languages),
        ("POST", "/api/languages", panel.save_languages),
        ("GET", "/api/library", panel.library),
        ("GET", "/api/folder", panel.folder),
        ("POST", "/api/delete", panel.delete_files),
        ("GET", "/file/{path:.+}", panel.file),
        ("GET", "/api/indexes", panel.indexes),
    ]
    for method, path, handler in routes:
        app.router.add_route(method, prefix + path, check(handler))
