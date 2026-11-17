# Pendientes

Lo que falta para que este sea el buscador definitivo de textos digitales. Aquí está lo que **no** se ha podido automatizar del todo, y por qué.

Estado a 16 de noviembre de 2026.

## Ya automatizado (como referencia)

Las webs que ponen una verificación de Cloudflare a los programas se abren con un Chrome real
(`browser_session.py`), con una pausa de 5 segundos entre peticiones a una misma web.

| Fuente | Cómo se usa | Qué da |
|---|---|---|
| OpenAlex | API (con `OPEN_ALEX_API_KEY`) | Artículos y libros académicos; enlaces a PDF |
| Unpaywall, Semantic Scholar, CORE, Sci-Hub | Buscadores de PDF por DOI o título | PDFs de las obras elegidas |
| Internet Archive | API | Libros escaneados, incluidas muchas copias de Google Books |
| Gutenberg | API Gutendex | Clásicos en EPUB |
| Wikisource | API de MediaWiki y su exportador de EPUB | Clásicos en EPUB, primero en español |
| Wikimedia Commons | API de MediaWiki (búsqueda de archivos PDF); cada archivo debe decir en su campo de autor que es suyo | Libros escaneados de dominio público en PDF (los DjVu, que son muchos, todavía no) |
| DOAB / OAPEN | Catálogo diario descargable (CC0), copia local que se renueva cada semana | Unos 96.000 libros académicos en abierto; descarga desde la editorial o desde la copia de Internet Archive |
| Dialnet | Cosecha OAI-PMH del área de Humanidades a una copia local | Artículos en español con texto completo en Dialnet |
| PhilArchive | Cosecha OAI-PMH a una copia local, y para cada obra encontrada, la copia que conoce OpenAlex | Filosofía en abierto que también está publicada en otro sitio |
| Biblioteca Virtual Miguel de Cervantes | SPARQL de BVMC Labs (`data.cervantesvirtual.com/bvmc-lod/repositories/data`); los PDF, con el navegador | Obras con PDF, buscadas por autor o título |
| Páginas de las copias en abierto (OpenAlex) | Para cada copia en abierto sin enlace al PDF, su página, de la que se saca `citation_pdf_url`; "Reintentar las pendientes" pide a OpenAlex los enlaces de hoy de las pendientes | Revistas OJS (Complutenses, CSIC, RACO, revistas universitarias) y repositorios |
| Webs con la comprobación de Cloudflare | Si una web responde con ella (o con su 403), se abre con el navegador; si bloquea del todo, o el navegador no la pasa, no se le vuelve a preguntar en esa ejecución | TDX y RACO, entre otras, sin tener que apuntarlas |
| Otras comprobaciones | Anubis y Zenodo: se repite la petición con el nombre del programa, que dejan pasar. La de Amazon (De Gruyter), la de PubMed Central y la de la Universidad de Chile: con el navegador | Repositorios de Valencia, Salamanca, UPM, Humboldt; PUCP, IMPAN, PMC, De Gruyter |
| Biblioteca Digital de Múnich (MDZ) | Sus enlaces (de Europeana, sobre todo) llevan el número del libro; el navegador abre su página de descarga, marca que se ha leído el aviso de derechos (uso libre, no comercial), pulsa "WEITER" y descarga el PDF del libro entero. Un libro cada 30 s | Libros antiguos enteros (Kant, Fichte, Segner): de 1 MB a más de 150 MB |
| Revistas de la Universidad de Navarra | Los enlaces de OpenAlex, abiertos con el navegador, que hace clic en su casilla de Turnstile | Anuario Filosófico, Scripta Theologica... Pasa casi siempre en unos 30 s; si un día no, se reintenta otro |
| Europeana | API con `EUROPEANA_API_KEY` (la clave va en el parámetro `wskey`) | Solo obras de dominio público o con licencia CC; el archivo, o la página de la obra en su biblioteca |
| Calibre | API del servidor de contenido | Marca lo que ya tienes y sube lo nuevo |

## Fuentes que se buscan solas pero se descargan a mano

Sus obras aparecen en las búsquedas y quedan pendientes; "Descargar a mano las pendientes" abre su
página en tu navegador.

### Biblioteca Digital Hispánica / BNE Digital
- **Qué hay:** su lista de dominio público en datos abiertos (CC BY 4.0): un ZIP de 1.930 CSV con unos 100.000 libros. Se guarda en el índice local y se renueva cada semana (con el navegador: bne.es pasa por Cloudflare).
- **Por qué a mano:** el 16 de noviembre de 2026, tras unas pocas pruebas de descarga de PDF desde `bnedigital.bne.es`, su sistema de seguridad bloqueó el acceso ("Página de bloqueo"). No se vuelve a intentar.
- **Qué se puede hacer:** escribir a bnelab@bne.es y preguntar si hay una forma permitida de descargar los documentos de dominio público con un programa.

### Gallica
- **Qué hay:** su buscador SRU, abierto con el navegador. Se guardan los libros impresos en dominio público.
- **Por qué a mano:** Cloudflare bloquea los PDF a los programas ("Attention Required"): es un bloqueo, no una verificación que se pueda pasar.

### PhilArchive (los PDFs propios)
- **Ahora:** solo se descargan las obras que tienen otra copia en otro sitio (en una muestra, el 26 % tenía PDF fuera de PhilPapers y el 59 %, DOI).
- **Por qué no el resto:** sus PDFs están detrás de Cloudflare. Sus condiciones prohíben descargarlos con programas "salvo permiso expreso por escrito".
- **Qué se puede hacer:** escribirles (philpapers.org/help/contact.html). Pide permiso para descargar en abierto con esta herramienta personal, de poco volumen, o que la dejen pasar. Si lo dan, se añade la descarga directa.

### HathiTrust
- **Qué hay:** su catálogo, abierto con el navegador (también su API pasa por Cloudflare). Se guardan los libros con un solo volumen en "Full view" desde España (aproximadamente, anteriores a 1901).
- **Por qué a mano:** su política de uso prohíbe automatizar descargas.
- **Qué se puede hacer:** con cuenta de la Universidad Complutense (miembro de HathiTrust), descargar a mano libros enteros. Muchos de sus escaneos están en Internet Archive, que el programa ya usa.

### Google Books
- **Falta:** una clave gratuita, `GOOGLE_BOOKS_API_KEY` en `.env` (console.cloud.google.com → API "Books API"). Sin clave, todas las peticiones comparten una cuota diaria mundial que siempre está gastada ("429 Quota exceeded"), así que sin clave la fuente no se usa.
- **Por qué a mano:** sus condiciones y su robots.txt prohíben descargar con programas. Se guarda el enlace de Google, y sus obras pasan por la revisión de obras dudosas.

## Fuentes que no se pueden automatizar del todo

### Biodiversity Heritage Library
- **Qué pasa:** sus PDFs están detrás de una verificación de Cloudflare que no deja pasar ni al navegador real (91 obras de Darwin pendientes en noviembre de 2026). Su robots.txt sí permite descargar.
- **Qué se puede hacer:** su API, con clave gratuita (biodiversitylibrary.org/getapikey), da el identificador de la copia de Internet Archive, de donde se descarga el PDF.
- **CORE**, que tenía el mismo problema, ya se resuelve sin clave: su API dice de qué repositorio sacó cada archivo, y se descarga de allí (`pdf_finders/core.py`). Con `CORE_API_KEY` responde a más peticiones seguidas.

## Fuentes nuevas por revisar

La lista de fuentes propuestas, con su valoración: [SOURCES_TO_CHECK.md](SOURCES_TO_CHECK.md).

## Otras mejoras pendientes

- **Bot de Telegram:**
  - Mandarle "autor: X" desde el móvil para que la torre busque, descargue y suba a Calibre.
  - **Falta decidir:**
    1. Sci-Hub abre un Chrome visible, y la torre no tiene pantalla donde abrirlo, así que allí haría falta Chrome sin interfaz o prescindir de Sci-Hub.
    2. Unir esta rama con `main`, donde está el bot con cambios recientes.
- **Actualización automática de los catálogos:** programar `update_indexes.py` cada semana con el Programador de tareas de Windows o un cron en la torre. Ahora se actualizan desde el menú o a mano. DOAB se renueva solo al buscar si tiene más de 7 días.
- **Más áreas de Dialnet:**
  - Ahora solo se cosecha Humanidades (conjunto 21).
  - Se pueden añadir Filologías (23) o Psicología y educación (20) en `HARVESTED_SETS` de `sources/dialnet.py`.
- **Traductor y editor:**
  - Las fuentes no distinguen el papel de cada persona, así que todos aparecen como autores.
  - Calibre solo lo admitiría con columnas personalizadas.
- **Credenciales de Calibre:** crear el usuario `automations` (no de solo lectura) y ponerlo en `.env` (`CALIBRE_URL`, `CALIBRE_USERNAME`, `CALIBRE_PASSWORD`). Probarlo contra el servidor real.
- **Frontend propio para Calibre:** una web nuestra para la biblioteca, en la torre, que use las mismas
  llamadas que la web oficial del servidor de Calibre (las de `calibre_library.py`), nunca `metadata.db` directamente.
  - Biblioteca: buscar, portadas, filtrar por autor, etiqueta o serie; ficha de cada libro.
  - Lector de PDF (pdf.js) con subrayado y notas.
  - **Las anotaciones y subrayados van en el propio archivo:** es la biblioteca personal y lo que interesa es que
    el PDF lleve lo marcado, para verlo en cualquier lector. Nada de guardarlas aparte. Al guardar, el PDF del
    libro en Calibre se sustituye por el subrayado (pensar si se conserva el original como ORIGINAL_PDF).
  - Con el mismo inicio de sesión que la terminal web (`tower/web_login.py`).
  - Más adelante, quizá: las búsquedas de paperScraper desde esta web en vez de la terminal.
