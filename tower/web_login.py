"""The door of the web terminal: a login page with a cookie, in front of ttyd.

ttyd's own user and password (HTTP Basic) don't work on many phones: the browser sends them for the page
but not for the terminal's live connection (WebSocket), so ttyd refuses it and the page stays at
"Press ⏎ to Reconnect". Here the session goes in a cookie and in the terminal's address
(/s/<session>/), so it works even on the phones that don't keep the cookie.

ttyd listens only on a UNIX socket inside the container (TTYD_SOCKET), so nothing reaches it without
passing through here. This listens on localhost:PAPERSCRAPER_WEB_PORT (7681), where cloudflared sends
https://papers.philtext.org.
"""
import asyncio
import hashlib
import hmac
import html
import logging
import os
import sys
import time

from aiohttp import ClientSession, UnixConnector, WSMsgType, web

log = logging.getLogger("web_login")
COOKIE_NAME = "paperscraper_session"
SESSION_SECONDS = 30 * 24 * 3600
# Each wrong password waits this long, and only one login is checked at a time: guessing is slow.
FAILED_LOGIN_DELAY_SECONDS = 2
# Headers that belong to one connection and must not be passed on.
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
              "transfer-encoding", "upgrade", "host", "content-length", "cookie"}

LOGIN_PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>paperScraper</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1e1e1e; color: #eee; display: flex;
         justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 16px;
         box-sizing: border-box; }}
  form {{ width: 100%; max-width: 320px; display: flex; flex-direction: column; gap: 12px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 8px; }}
  input, button {{ font-size: 1rem; padding: 12px; border-radius: 6px; border: 1px solid #555; }}
  input {{ background: #2b2b2b; color: #eee; }}
  button {{ background: #3b82f6; color: white; border: none; }}
  .error {{ color: #f87171; margin: 0; }}
</style></head>
<body><form method="post" action="/login">
  <h1>paperScraper</h1>
  {error}
  <input name="user" placeholder="Usuario" autocomplete="username" autocapitalize="none" required autofocus>
  <input name="password" type="password" placeholder="Contraseña" autocomplete="current-password" required>
  <button type="submit">Entrar</button>
</form></body></html>
"""


class Door:
    def __init__(self, user: str, password: str, ttyd_socket: str):
        self.user = user
        self.password = password
        self.ttyd_socket = ttyd_socket
        # Changing the password in .env closes every open session.
        self.secret = hashlib.sha256(f"paperscraper-web\0{user}\0{password}".encode()).digest()
        self.login_lock = asyncio.Lock()
        self.client: ClientSession | None = None

    # --- sessions ---
    # A session is "<expiry>.<signature>". It goes in a cookie and also in the address of the terminal
    # (/s/<session>/): some phone browsers don't keep the cookie, and ttyd builds the addresses of its
    # connections from the page's, so the terminal works with the address alone.

    def signature(self, expiry: int) -> str:
        return hmac.new(self.secret, str(expiry).encode(), hashlib.sha256).hexdigest()

    def new_session(self) -> str:
        expiry = int(time.time()) + SESSION_SECONDS
        return f"{expiry}.{self.signature(expiry)}"

    def valid(self, session: str) -> bool:
        expiry_text, _, signature = session.partition(".")
        if not expiry_text.isdigit() or int(expiry_text) < time.time():
            return False
        return hmac.compare_digest(signature, self.signature(int(expiry_text)))

    def cookie_session(self, request: web.Request) -> str | None:
        session = request.cookies.get(COOKIE_NAME, "")
        return session if self.valid(session) else None

    # --- pages ---

    async def home(self, request: web.Request) -> web.Response:
        session = self.cookie_session(request)
        raise web.HTTPFound(f"/s/{session}/" if session else "/login")

    async def login_page(self, request: web.Request, error: str = "") -> web.Response:
        session = self.cookie_session(request)
        if not error and session:
            raise web.HTTPFound(f"/s/{session}/")
        error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
        return web.Response(text=LOGIN_PAGE.format(error=error_html), content_type="text/html",
                            headers={"Cache-Control": "no-store"})

    async def login(self, request: web.Request) -> web.Response:
        form = await request.post()
        # Phone keyboards often capitalise the user or add a space after it.
        typed_user = str(form.get("user", "")).strip().lower()
        async with self.login_lock:
            right_user = hmac.compare_digest(typed_user.encode(), self.user.strip().lower().encode())
            right_password = hmac.compare_digest(str(form.get("password", "")).encode(), self.password.encode())
            if not (right_user and right_password):
                log.warning("Inicio de sesión fallido desde %s: %s", client_address(request),
                            "contraseña incorrecta" if right_user else "usuario incorrecto")
                await asyncio.sleep(FAILED_LOGIN_DELAY_SECONDS)
                return await self.login_page(request, "Usuario o contraseña incorrectos. En el móvil, mira que el "
                                             "teclado no haya puesto mayúscula o cambiado algún carácter.")
        log.info("Sesión iniciada desde %s (%s)", client_address(request), request.headers.get("User-Agent", "?"))
        session = self.new_session()
        response = web.HTTPFound(f"/s/{session}/")
        response.set_cookie(COOKIE_NAME, session, max_age=SESSION_SECONDS, httponly=True,
                            samesite="Lax", secure=not is_local(request), path="/")
        response.headers["Cache-Control"] = "no-store"
        raise response

    async def logout(self, request: web.Request) -> web.Response:
        response = web.HTTPFound("/login")
        response.del_cookie(COOKIE_NAME, path="/")
        raise response

    # --- the terminal: /s/<session>/... goes to ttyd's /... ---

    async def without_slash(self, request: web.Request) -> web.Response:
        raise web.HTTPFound(f"/s/{request.match_info['session']}/")

    async def forward(self, request: web.Request) -> web.StreamResponse:
        websocket = request.headers.get("Upgrade", "").lower() == "websocket"
        if not self.valid(request.match_info["session"]):
            log.info("%s %s con una sesión no válida o caducada", request.method, request.match_info["rest"])
            if websocket:
                raise web.HTTPUnauthorized()
            raise web.HTTPFound("/login")
        path = "/" + request.match_info["rest"]
        if request.query_string:
            path += "?" + request.query_string
        if websocket:
            return await self.forward_websocket(request, path)
        return await self.forward_http(request, path)

    def ttyd_client(self) -> ClientSession:
        if self.client is None:
            self.client = ClientSession(connector=UnixConnector(path=self.ttyd_socket), auto_decompress=False)
        return self.client

    async def forward_http(self, request: web.Request, path: str) -> web.Response:
        headers = {name: value for name, value in request.headers.items() if name.lower() not in HOP_BY_HOP}
        async with self.ttyd_client().request(request.method, f"http://ttyd{path}", headers=headers,
                                              data=await request.read(), allow_redirects=False) as answer:
            body = await answer.read()
            answer_headers = {name: value for name, value in answer.headers.items()
                              if name.lower() not in HOP_BY_HOP}
            # The address carries the session: it must not leave in a Referer, nor stay in a cache.
            answer_headers["Referrer-Policy"] = "no-referrer"
            answer_headers["Cache-Control"] = "no-store"
            return web.Response(status=answer.status, body=body, headers=answer_headers)

    async def forward_websocket(self, request: web.Request, path: str) -> web.WebSocketResponse:
        # Only the page itself may open the terminal (what ttyd's --check-origin did).
        origin = request.headers.get("Origin", "")
        if origin.split("://")[-1] != request.host:
            raise web.HTTPForbidden()
        browser = web.WebSocketResponse(protocols=("tty",), heartbeat=30)
        await browser.prepare(request)
        async with self.ttyd_client().ws_connect(f"http://ttyd{path}", protocols=("tty",)) as terminal:
            await asyncio.gather(pump(browser, terminal), pump(terminal, browser))
        return browser


async def pump(source, destination) -> None:
    """Pass the messages of one side to the other until either closes."""
    try:
        async for message in source:
            if message.type == WSMsgType.BINARY:
                await destination.send_bytes(message.data)
            elif message.type == WSMsgType.TEXT:
                await destination.send_str(message.data)
            else:
                break
    finally:
        await destination.close()


def client_address(request: web.Request) -> str:
    # Behind cloudflared every request comes from localhost; Cloudflare says who it really is.
    return request.headers.get("CF-Connecting-IP") or request.remote or "?"


@web.middleware
async def https_only(request: web.Request, handler):
    """A page opened with http:// goes to https:// (Cloudflare says how the browser came)."""
    came_by_http = (request.headers.get("X-Forwarded-Proto") == "http"
                    or '"scheme":"http"' in request.headers.get("Cf-Visitor", "").replace(" ", ""))
    if came_by_http and not is_local(request):
        raise web.HTTPMovedPermanently(f"https://{request.host}{request.rel_url}")
    return await handler(request)


def is_local(request: web.Request) -> bool:
    return request.host.split(":")[0] in ("localhost", "127.0.0.1")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    user = os.environ.get("PAPERSCRAPER_WEB_USER", "")
    password = os.environ.get("PAPERSCRAPER_WEB_PASSWORD", "")
    if not user or not password:
        sys.exit("Faltan PAPERSCRAPER_WEB_USER y PAPERSCRAPER_WEB_PASSWORD en .env; la terminal web no arranca.")
    door = Door(user, password, os.environ.get("TTYD_SOCKET", "/tmp/ttyd.sock"))
    app = web.Application(middlewares=[https_only])
    app.router.add_get("/", door.home)
    app.router.add_get("/login", door.login_page)
    app.router.add_post("/login", door.login)
    app.router.add_get("/logout", door.logout)
    app.router.add_get("/s/{session}", door.without_slash)
    app.router.add_route("*", "/s/{session}/{rest:.*}", door.forward)
    port = int(os.environ.get("PAPERSCRAPER_WEB_PORT", "7681"))
    # Only this machine (cloudflared); PAPERSCRAPER_WEB_HOST=0.0.0.0 only for trying it in a container.
    host = os.environ.get("PAPERSCRAPER_WEB_HOST", "127.0.0.1")
    web.run_app(app, host=host, port=port, print=lambda *_: print(f"Terminal web en {host}:{port}"))


if __name__ == "__main__":
    main()
