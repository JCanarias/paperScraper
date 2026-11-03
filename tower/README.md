# paperScraper en la torre: terminal web y revisión diaria

El menú de `main.py`, el mismo de siempre, en una terminal web que corre en la torre.
Se usa desde cualquier sitio en `https://papers.philtext.org`.

- **ttyd** muestra la terminal en el navegador. Solo escucha en la propia torre (`localhost:7681`).
- **tmux** guarda la sesión: si cierras la pestaña o se corta la conexión, la búsqueda sigue,
  y al volver la encuentras donde estaba.
- **cloudflared** la saca a internet, como `calibre.philtext.org`.
- **Cloudflare Access** pide tu correo antes de dejar pasar. Sin él, cualquiera tendría una terminal en la torre.

## Puesta en marcha (en la torre)

### 1. El proyecto

```bash
cd ~/paperScraper
git fetch && git checkout feature/additional-sources && git pull
```

Desde el PC (PowerShell, en la carpeta del proyecto), copia lo que no está en git:

```powershell
scp .env jorge@100.71.69.117:~/paperScraper/
scp -r data library jorge@100.71.69.117:~/paperScraper/
```

En la torre, cambia en `.env` la dirección de Calibre por la local: `CALIBRE_URL=http://localhost:8080`.

### 2. El servicio

```bash
bash tower/install.sh
```

Instala ttyd, tmux, el entorno de Python y el servicio `paperscraper-web`. Pruébalo en el navegador
de la torre: `http://localhost:7681`.

Sci-Hub necesita Chrome. Si no está: descarga el `.deb` de google.com/chrome e instálalo con
`sudo apt install ./google-chrome-stable_current_amd64.deb`.

### 3. Cloudflare Access (ANTES de publicar la dirección)

En https://one.dash.cloudflare.com → **Access → Applications → Add an application → Self-hosted**:

- Application domain: `papers.philtext.org`
- Policy: **Allow**, regla **Emails** = tu correo.
- Login method: **One-time PIN** (te llega un código por correo).

### 4. La dirección

En `/etc/cloudflared/config.yml`, añade esto en `ingress:` **antes** de la última regla (`- service: http_status:404`):

```yaml
  - hostname: papers.philtext.org
    service: http://localhost:7681
```

Y luego (el nombre del túnel es el de `tunnel:` en ese mismo archivo):

```bash
cloudflared tunnel route dns <nombre-del-túnel> papers.philtext.org
sudo systemctl restart cloudflared
```

Abre `https://papers.philtext.org`: primero debe pedirte el correo. Si entra directo, Access no está bien puesto.

## Uso

- Es la terminal de siempre: flechas y Enter; en las listas de casillas, espacio para marcar.
- En el móvil, sin flechas: `j` y `k` para bajar y subir.
- Ctrl+C interrumpe, como siempre. Al terminar cada opción, Enter vuelve al menú.
- Rueda del ratón para ver lo de antes; para copiar texto, selecciona con Shift pulsado.
- "Descargar a mano las pendientes" abre el navegador **de la torre**, no el tuyo; en remoto no sirve.
- Chrome (Sci-Hub) se abre en la pantalla de la torre.

## Revisión diaria (6:00)

Cada día a las 6:00 (hora de la torre), `daily_check.py` revisa los autores marcados en
el menú → **"Autores que seguir (revisión diaria)"**. De cada uno:

1. busca obras nuevas (OpenAlex y las demás bibliotecas) y marca para descargar las que no están en Calibre;
2. busca otra vez archivo para las obras elegidas que aún no lo tienen (también obras viejas);
3. sube a Calibre cada obra que descarga y te manda un mensaje por Telegram por cada una.

Usa el bot de `telegram_bot/.env`: su token, y manda los mensajes a los usuarios de `TELEGRAM_ALLOWED_USER_IDS`.
Si la torre estaba apagada a las 6:00, la revisión se hace al encenderla.

En las listas buscadas antes de esto solo está guardado el perfil principal de OpenAlex. Si un autor
tenía varios perfiles ("L. Flamarique-Zaratiegui"...), búscalo otra vez por autor y elígelos todos: la marca de
seguirlo se conserva.

```bash
sudo systemctl start paperscraper-daily      # hacerla ahora
journalctl -u paperscraper-daily -e           # qué hizo la última vez
systemctl list-timers paperscraper-daily.timer   # cuándo toca la próxima
```

Mientras corre, el menú avisa al arrancar de que la revisión está en marcha.

## Mantenimiento

```bash
sudo systemctl restart paperscraper-web   # reinicia la web; la sesión de tmux sigue
tmux kill-session -t paperscraper         # cierra la sesión (para lo que esté corriendo)
journalctl -u paperscraper-web -f         # registros
```

Después de un `git pull` con cambios en `main.py`, basta con volver al menú: cada opción arranca `main.py` de nuevo.
