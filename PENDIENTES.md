# Pendientes

Lo que falta para que este sea el buscador definitivo de textos digitales. Aquí está lo que **no** se ha podido automatizar del todo, y por qué.

Estado a 2 de noviembre de 2026.

## Ya automatizado (como referencia)

| Fuente | Cómo se usa | Qué da |
|---|---|---|
| OpenAlex | API (con `OPEN_ALEX_API_KEY`) | Artículos y libros académicos; enlaces a PDF |
| Unpaywall, Semantic Scholar, CORE, Sci-Hub | Buscadores de PDF por DOI o título | PDFs de las obras elegidas |
| Internet Archive | API | Libros escaneados, incluidas muchas copias de Google Books |
| Gutenberg | API Gutendex | Clásicos en EPUB |
| Wikisource | API de MediaWiki y su exportador de EPUB | Clásicos en EPUB, primero en español |
| DOAB / OAPEN | Catálogo diario descargable (CC0), copia local que se renueva cada semana | Unos 96.000 libros académicos en abierto; descarga desde la editorial o desde la copia de Internet Archive |
| Dialnet | Cosecha OAI-PMH del área de Humanidades a una copia local | Artículos en español con texto completo en Dialnet |
| PhilArchive | Cosecha OAI-PMH a una copia local, y para cada obra encontrada, la copia que conoce OpenAlex | Filosofía en abierto que también está publicada en otro sitio |
| Calibre | API del servidor de contenido | Marca lo que ya tienes y sube lo nuevo |

## Fuentes que no se pueden automatizar del todo

### Biblioteca Virtual Miguel de Cervantes
- **Qué hay:** un catálogo abierto (SPARQL, CC0) con enlaces a los PDFs. Su aviso legal permite guardar copias para uso personal.
- **Por qué no:** los PDFs (`/descargaPdf/`) están detrás de la verificación de Cloudflare para cualquier programa.
- **Qué se puede hacer:**
  1. Buscar en su catálogo desde el programa y abrir el PDF en tu navegador. La descarga a mano ya existe en el programa; solo faltaría añadir la búsqueda.
  2. Escribir a "El Bibliotecario" (cervantesvirtual.com/bibliotecario/, tel. 96 590 9481) o a BVMC.Labs para pedir que dejen pasar a esta herramienta de investigación.

### Biblioteca Digital Hispánica (BNE)
- **Qué hay:** una lista abierta (CC BY 4.0) de sus documentos de dominio público en datosabiertos.bne.es: 1.930 CSV, con autor, título, fecha y enlace.
- **Por qué no:** el enlace antiguo de descarga (`bdh-rd.bne.es/pdf.raw`) devuelve una página anti-bots. La plataforma nueva (`bnedigital.bne.es`) no expone ningún enlace de descarga que un programa pueda usar.
- **Qué se puede hacer:** escribir a bnelab@bne.es y preguntar si hay una forma de descargar los documentos de dominio público con un programa.

### PhilArchive (los PDFs propios)
- **Ahora:** solo se descargan las obras que tienen otra copia en otro sitio (en una muestra, el 26 % tenía PDF fuera de PhilPapers y el 59 %, DOI).
- **Por qué no el resto:** sus PDFs están detrás de Cloudflare. Sus condiciones prohíben descargarlos con programas "salvo permiso expreso por escrito".
- **Qué se puede hacer:** escribirles (philpapers.org/help/contact.html). Pide permiso para descargar en abierto con esta herramienta personal, de poco volumen, o que la dejen pasar. Si lo dan, se añade la descarga directa.

### Revistas de la Universidad de Navarra (Anuario Filosófico, Scripta Theologica…)
- **Qué hay:** OpenAlex las marca bien como de acceso libre y da el enlace al PDF.
- **Por qué no:** `revistas.unav.edu` pone la verificación de Cloudflare (Turnstile) delante de cada PDF, y su repositorio `dadun.unav.edu` rechaza a los programas (403). En la búsqueda de Lourdes Flamarique fueron 21 de los 31 enlaces que fallaron.
- **Qué se puede hacer:**
  1. "Descargar a mano las pendientes": abre cada obra en el navegador y recoge el archivo de Descargas.
  2. Cuando termine la cosecha de Dialnet, "Reintentar las obras pendientes" por si Dialnet tiene copia de alguna.
  3. Escribir al Servicio de Publicaciones de la Universidad de Navarra (rhereder@unav.es, el contacto que aparece en su página de verificación) y pedir que dejen pasar a esta herramienta.

### HathiTrust
- **Por qué no:** su política de uso prohíbe expresamente automatizar descargas. Su API de datos se retiró en 2024.
- **Qué se puede hacer:**
  - Con cuenta de la Universidad Complutense (miembro de HathiTrust), descargar a mano libros enteros de dominio público desde el navegador.
  - Desde España solo se ven completos los libros de antes de 1901 aproximadamente.
  - Muchos de sus escaneos están en Internet Archive, que el programa ya usa.

### Google Books
- **Por qué no:** se puede buscar con una clave gratuita, pero las descargas de PDF están prohibidas para programas (robots.txt y sus condiciones) y llevan a un captcha.
- **Qué se puede hacer:**
  1. Conseguir una clave gratuita (console.cloud.google.com → API "Books API") y usarla solo para encontrar ediciones. Después se busca la misma copia en Internet Archive (identificadores que acaban en `goog`) o en Wikimedia Commons, que sí permiten descargar.
  2. Abrir en tu navegador el enlace de Google para descargarlo tú.

### DOAB / OAPEN (lo que falta)
- **Los libros de OAPEN posteriores a finales de 2024:** no están en la copia de Internet Archive. OAPEN tiene bloqueada nuestra IP desde las pruebas.
  - **Qué se puede hacer:** escribir a OAPEN (DOAB: oacontact@operas.atlassian.net; OAPEN: s.sali@oapen.org) y pedir que levanten el bloqueo, explicando que es un uso personal y lento.
- **Solo el primer autor:** el catálogo que usamos (KBART) solo trae el primer autor o editor de cada libro.
  - **Qué se puede hacer:** usar su CSV completo (`DOAB.csv`, más grande), que trae todos los autores.
- **JSTOR y Project MUSE:** se excluyen porque sus condiciones prohíben descargar con programas.

### Europeana
- **Qué hay:** una API gratuita con clave, que lleva a bibliotecas españolas como la Biblioteca Virtual del Patrimonio Bibliográfico.
- **Falta:**
  1. Pedir la clave en europeana.eu.
  2. Comprobar si las bibliotecas a las que lleva permiten descargar con programas.

### Gallica
- **Qué hay:** se puede buscar (API SRU).
- **Por qué no:** las descargas están detrás de Cloudflare.

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
