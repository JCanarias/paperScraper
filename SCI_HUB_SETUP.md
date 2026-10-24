# Setup de Sci-Hub

Sci-Hub requiere resolver un CAPTCHA para verificar que no eres un bot. Sigue estos pasos:

## Paso 1: Ejecutar el script de setup

```bash
python setup_sci_hub_cookies.py
```

El script:
1. Abrirá sci-hub.su en tu navegador
2. Te pedirá que resuelvas el CAPTCHA "Are you a robot?"
3. Guardará las cookies de la sesión en `sci_hub_cookies.json`

## Paso 2: Listo

Una vez guardadas las cookies, el programa usará automáticamente esa sesión para descargar papers. No necesitas repetir el CAPTCHA.

## Notas

- Las cookies pueden expirar después de algunos días/semanas
- Si dejan de funcionar, ejecuta el script nuevamente
- El archivo `sci_hub_cookies.json` contiene las cookies de sesión (no incluir en git)
