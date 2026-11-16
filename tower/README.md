# paperScraper en la torre: panel web, terminal web y revisión diaria

Dos contenedores (`docker-compose.yml`, en la raíz del proyecto):

- **`paperscraper_web`**: el panel web (`https://papers.philtext.org`, con usuario y contraseña), pensado
  para el móvil, y el menú de `main.py`, el mismo de siempre, en una terminal web. ttyd la muestra en el navegador; delante tiene
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

## El panel web

Tras iniciar sesión se abre el panel (`webapp/`, servido por `tower/web_login.py` en `/p/<sesión>/`). Tiene
todas las opciones del menú; la terminal sigue a un toque (enlace "Terminal", arriba a la derecha). En el
móvil se puede añadir a la pantalla de inicio ("Añadir a pantalla de inicio") y se abre como una app.

- **Siempre arriba:** si la revisión diaria está en marcha (desde cuándo y qué autor va revisando) o cómo
  acabó la última y cuándo es la próxima; y si hay una tarea del panel en marcha, con su última línea.
  Tocándolas, su log en vivo.
- **Abajo, cuatro pestañas:**
  - **Inicio:** contadores (dudosas, pendientes, sin subir), la última tarea, las últimas descargas y el resto
    de opciones (biblioteca, autores que seguir, idiomas, catálogos, metadatos, revisión diaria ahora).
    Todo lo que se descarga queda apuntado en `library/.history/downloads.jsonl`.
  - **Buscar:**
    - *Autor:* busca los perfiles en OpenAlex, dice cuáles ya están en tu biblioteca y deja ver sus obras más
      citadas. Se marcan los perfiles de la persona (se juntan en una lista, como en el menú) y sus idiomas, que
      empiezan por los de su última búsqueda. Las obras dudosas no se preguntan en la búsqueda: esperan en
      "Obras dudosas".
    - *Título:* la búsqueda es una tarea; al acabar se eligen las obras (filtro, "marcar las que no están en
      Calibre") y se descargan. La última búsqueda se guarda en `library/.web/title_results.json`.
    - *Bibliografía:* un archivo .bib, .ris o .txt, o las referencias pegadas, una por línea. Se guarda en
      `library/.web/bibliographies/` con la fecha y la hora, y su lista en `library/Bibliografías/`.
  - **Pendiente:** obras dudosas (descargar o descartar cada una, o todas las de un autor), descargar a mano
    (abrir su página y subir el PDF o EPUB desde el móvil: se guarda con su nombre y metadatos), reintentar
    las pendientes y subir a Calibre. El número rojo son las dudosas por decidir.
  - **Tarea:** el log en vivo de la tarea del panel, el botón para pararla y, al acabar, el paso siguiente.
- Las opciones largas son tareas: una a la vez, en su propio proceso (`python -m webapp.jobs`), con su salida
  en `library/.web/job.log`. "Parar la tarea" hace lo mismo que Ctrl+C en el menú: lo descargado se queda y
  la lista se guarda.
- Nada que cambie las listas se hace mientras la revisión diaria está en marcha. Y si a las 6:00 hay una tarea
  del panel en marcha, la revisión diaria espera a que termine (`library/.web/task.lock`). No lances lo mismo
  a la vez desde el panel y desde la terminal: escribirían las mismas listas.

## Uso de la terminal web

- Es la terminal de siempre: flechas y Enter; en las listas de casillas, espacio para marcar.
- En el móvil, sin flechas: `j` y `k` para bajar y subir.
- Ctrl+C interrumpe, como siempre. Al terminar cada opción, Enter vuelve al menú.
- Rueda del ratón para ver lo de antes; para copiar texto, selecciona con Shift pulsado.
- "Descargar a mano las pendientes" no sirve aquí: abriría un navegador dentro del contenedor. Usa la del panel.

## Revisión diaria

Para cada autor seguido:

1. busca obras nuevas (OpenAlex y las demás bibliotecas) y marca para descargar las que no están en Calibre;
2. busca otra vez archivo para las obras elegidas que aún no lo tienen (también obras viejas). Una obra que
   sigue sin archivo espera cada vez más antes del siguiente intento (1, 2, 4, 8, 16 y como mucho 30 días),
   salvo que aparezca un enlace nuevo para ella. "Reintentar las obras pendientes", en el menú, las prueba todas;
3. sube a Calibre cada obra que descarga y te manda un mensaje por Telegram por cada una.

### Obras dudosas (Internet Archive y Google Books)

En esas dos el autor lo pone quien sube o publica el libro, y a veces está mal (una "History of Magic"
de Einstein). Una obra que solo está ahí no se descarga sin preguntarte; si también está en OpenAlex o en
una biblioteca fiable, sí.

- **Al buscar un autor en el menú**, te sale la lista de las dudosas para marcar las suyas.
- **La revisión diaria** te pregunta por Telegram ("¿Es de este autor?", con botones Descargar / Descartar),
  hasta 20 al día; las demás, los días siguientes. Al pulsar Descargar la busca en ese momento y te avisa.
- **En el menú**, "Revisar obras dudosas" enseña todas las que esperan respuesta.

Lo descartado no se vuelve a descargar, tampoco al buscar otra vez al autor. Lo mismo vale para lo que borres
en "Ver y borrar archivos" diciendo que no vuelva.

### Lo que borras de Calibre

Lo que subió el programa y borras después en Calibre no se vuelve a descargar ni a subir, desde ninguna lista
(`calibre_memory.py`). Lo que añadiste a Calibre a mano sí puede volver si lo borras. Para deshacer un borrado,
ver [TRUCOS.md](TRUCOS.md).

Los botones los atiende el bot de `telegram_bot/` (el servicio `telegram-bot`, fuera de Docker): pasa tu
respuesta al contenedor `paperscraper_daily` con `docker exec`. Por eso el usuario del bot tiene que poder usar
docker (estar en el grupo `docker`), y tras actualizar hay que reiniciarlo: `sudo systemctl restart telegram-bot`.

### Presupuesto de OpenAlex

Cada clave de OpenAlex tiene un presupuesto diario (1 $ la gratuita; se renueva a medianoche UTC). Una búsqueda
por texto cuesta 0,001 $, una página de una lista 0,0001 $. La revisión diaria deja sin gastar 0,30 $ para que
puedas usar el menú; si se acaba, el menú lo dice y a qué hora se renueva. Las obras de PhilArchive se buscan en
OpenAlex una vez cada 90 días, no cada día.

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
