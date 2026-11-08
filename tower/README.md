# paperScraper en la torre: terminal web y revisión diaria

Dos contenedores (`docker-compose.yml`, en la raíz del proyecto):

- **`paperscraper_web`**: el menú de `main.py`, el mismo de siempre, en una terminal web
  (`https://papers.philtext.org`), con usuario y contraseña. ttyd la muestra en el navegador; delante tiene
  una página de inicio de sesión (`tower/web_login.py`), que solo escucha en la torre (`localhost:7681`).
  tmux guarda la sesión: si cierras la pestaña o se corta la conexión, la búsqueda sigue, y al volver
  la encuentras donde estaba.
- **`paperscraper_daily`**: la revisión diaria a las 6:00 de los autores marcados en
  "Autores que seguir". Si la torre estaba apagada a esa hora, la hace al arrancar.

Los dos usan la red de la torre, así que Calibre está en `localhost:8080`. Chrome (Sci-Hub) se abre dentro de
cada contenedor, en una pantalla invisible (Xvfb). Cada contenedor puede usar 2 GB de memoria como mucho:
la torre tiene 8 GB y Phil-text los necesita.

`library/` y `data/` (los catálogos) quedan fuera de los contenedores, en la carpeta del proyecto.
Para tenerlos en el disco grande, pon en `.env`:

```
PAPERSCRAPER_LIBRARY=/mnt/hdd/paperscraper/library
PAPERSCRAPER_DATA=/mnt/hdd/paperscraper/data
```

## Puesta en marcha

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

En la torre, en `.env`:

```
CALIBRE_URL=http://localhost:8080
PAPERSCRAPER_WEB_USER=jorge
PAPERSCRAPER_WEB_PASSWORD=<una contraseña larga>
```

La página pide ese usuario y contraseña al abrir la terminal y se acuerda 30 días (una cookie; también en el
móvil). Tras entrar, la dirección es `https://papers.philtext.org/s/<sesión>/`: lleva la sesión dentro (para los móviles que no guardan la cookie), así que no la compartas. Para cerrar la sesión: `https://papers.philtext.org/logout`. Cambiar la contraseña cierra todas las sesiones. Sin ellos,
la terminal web no arranca. Es la única puerta al menú desde internet: usa una contraseña larga y que no uses en otro sitio.

Comprueba también que `telegram_bot/.env` tiene `TELEGRAM_BOT_TOKEN` y `TELEGRAM_ALLOWED_USER_IDS`:
la revisión diaria avisa con ese bot.

### 2. Los contenedores

```bash
./update.sh
```

Pruébalo en el navegador de la torre: `http://localhost:7681` (pide el usuario y la contraseña).
Tras cambiar `requirements.txt` o el `Dockerfile` hace falta `./update.sh` (reconstruye la imagen); para lo demás basta `git pull`.

### 3. La dirección

El túnel se gestiona en la torre. En `/etc/cloudflared/config.yml`, añade esto en `ingress:`
**antes** de la última regla (`- service: http_status:404`):

```yaml
  - hostname: papers.philtext.org
    service: http://localhost:7681
```

Y luego, sin sudo (hace falta el `cert.pem` de `~/.cloudflared/`; el nombre del túnel es el de `tunnel:`):

```bash
cloudflared tunnel route dns <nombre-del-túnel> papers.philtext.org
sudo systemctl restart cloudflared
```

Si `route dns` no encuentra el certificado, crea el registro a mano en el DNS de `philtext.org`:
CNAME `papers` → `<id-del-túnel>.cfargotunnel.com`, con proxy (nube naranja).

Abre `https://papers.philtext.org`: tiene que pedir usuario y contraseña antes de enseñar nada.

## Uso de la terminal web

- Es la terminal de siempre: flechas y Enter; en las listas de casillas, espacio para marcar.
- En el móvil, sin flechas: `j` y `k` para bajar y subir.
- Ctrl+C interrumpe, como siempre. Al terminar cada opción, Enter vuelve al menú.
- Rueda del ratón para ver lo de antes; para copiar texto, selecciona con Shift pulsado.
- "Descargar a mano las pendientes" no sirve aquí: abriría un navegador dentro del contenedor.

## Revisión diaria

Para cada autor seguido:

1. busca obras nuevas (OpenAlex y las demás bibliotecas) y marca para descargar las que no están en Calibre;
2. busca otra vez archivo para las obras elegidas que aún no lo tienen (también obras viejas);
3. sube a Calibre cada obra que descarga y te manda un mensaje por Telegram por cada una.

En las listas buscadas antes de esto solo está guardado el perfil principal de OpenAlex. Si un autor
tenía varios perfiles ("L. Flamarique-Zaratiegui"...), búscalo otra vez por autor y elígelos todos: la marca de
seguirlo se conserva.

Mientras corre, el menú avisa al arrancar de que la revisión está en marcha.

## Mantenimiento

```bash
./update.sh                                         # git pull, reconstruir y reiniciar
docker compose exec daily python daily_check.py     # hacer la revisión ahora
docker logs -f paperscraper_daily                   # qué hace (o hizo) la revisión
docker logs -f paperscraper_web
docker compose restart web                          # reinicia la terminal (cierra la sesión)
```

`./update.sh` no reinicia nada mientras la revisión diaria está en marcha (con `--force`, sí).
Reiniciar `web` cierra la sesión de la terminal y lo que esté corriendo en ella.
Los cambios de código solo necesitan volver al menú (cada opción arranca `main.py` de nuevo);
los de `requirements.txt` o `Dockerfile`, `./update.sh`.

## Trucos

Ver los logs, traer archivos al PC y otros comandos útiles: [TRUCOS.md](TRUCOS.md).
