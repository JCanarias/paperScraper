# Trucos para la torre

Cosas útiles para ver qué hace paperScraper en la torre y traerse sus archivos al PC.
La torre es `jorge@100.71.69.117` (Tailscale) y el proyecto está en `~/paperScraper`.

## Ver qué ha hecho la revisión diaria

### Los archivos de log (desde el 8 de noviembre de 2026)

Cada revisión se guarda también en un archivo por día, `library/.logs/daily-AAAA-MM-DD.log`.
Se conservan los últimos 90 días.

```bash
ls ~/paperScraper/library/.logs/
less ~/paperScraper/library/.logs/daily-2026-11-08.log
```

### El log de Docker

Todo lo que escriben los contenedores también queda en el log de Docker:

```bash
docker logs --timestamps paperscraper_daily 2>&1 | less
docker logs --timestamps paperscraper_daily 2>&1 | grep "Revisión diaria"   # una línea por revisión
```

En `less`: `/texto` busca, `n` salta al siguiente, `G` va al final, `q` sale.
Las horas de `--timestamps` están en UTC (una hora menos que en Madrid en invierno).

**Ojo: el log de Docker se pierde al recrear el contenedor.** `./update.sh` los recrea siempre, así que
`docker logs` solo tiene lo que ha pasado desde el último `./update.sh`. Para saber desde cuándo:

```bash
docker ps --format '{{.Names}}  creado: {{.CreatedAt}}'
```

Por eso existen los archivos de `library/.logs/`. Si quieres guardar el log de Docker antes de actualizar:

```bash
docker logs --timestamps paperscraper_daily > ~/daily.log 2>&1
```

### Los inicios de sesión de la terminal web

```bash
docker logs paperscraper_web 2>&1 | grep -v "\] N:" | tail -30
```

`grep -v "\] N:"` quita los avisos internos de ttyd y deja los de la página de inicio de sesión:
sesiones iniciadas, contraseñas fallidas…

## Traer archivos de la torre al PC

Desde el PC, en PowerShell. `scp` necesita **dos** cosas: qué copiar (en la torre) y **dónde dejarlo** (en el PC).
Si falta el destino, solo enseña la ayuda (`usage: scp ...`).

```powershell
# Un archivo, a la carpeta del proyecto
scp jorge@100.71.69.117:~/daily.log C:\Users\jorge\jcc.main\paperScraper\daily.log

# Una carpeta entera: -r
scp -r jorge@100.71.69.117:~/paperScraper/library/.logs C:\Users\jorge\jcc.main\paperScraper\logs
```

El destino puede ser `.` ("aquí"), pero entonces el archivo va a la carpeta donde esté PowerShell
(lo que sale antes de `>`, por ejemplo `PS C:\Users\jorge>`), que no siempre es la del proyecto.

Al revés, del PC a la torre, se cambia el orden: primero lo del PC y después la torre.

```powershell
scp C:\Users\jorge\jcc.main\paperScraper\.env jorge@100.71.69.117:~/paperScraper/
```

Los `.log` que traigas a la carpeta del proyecto no se suben a git (`.gitignore`).

## Otras cosas útiles

```bash
# Lanzar la revisión diaria ahora, a mano (se ve en pantalla; no la guarda en library/.logs)
docker compose exec daily python daily_check.py

# Reiniciar solo la terminal web (corta la búsqueda que esté en marcha en ella)
docker compose restart web

# Cuánta memoria usan los contenedores
docker stats --no-stream paperscraper_web paperscraper_daily
```
