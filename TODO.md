# Pendiente

## Frontend propio para Calibre

Una web nuestra para la biblioteca de Calibre, en la torre, que use las mismas llamadas que la web
oficial del servidor de Calibre (las que ya usa `calibre_library.py`), nunca `metadata.db` directamente.

- Biblioteca: buscar, portadas, filtrar por autor, etiqueta o serie; ficha de cada libro.
- Lector de PDF (pdf.js) con subrayado y notas.
- **Las anotaciones y subrayados van en el propio archivo**: es la biblioteca personal y lo que
  interesa es que el PDF lleve lo marcado, para verlo en cualquier lector. Nada de guardarlas aparte.
  Al guardar, el PDF del libro en Calibre se sustituye por el subrayado (pensar si se conserva el
  original como ORIGINAL_PDF, como hace Calibre al modificar archivos).
- Con el mismo inicio de sesión que la terminal web (`tower/web_login.py`).
- Más adelante, quizá: las búsquedas de paperScraper desde esta web en vez de la terminal.
