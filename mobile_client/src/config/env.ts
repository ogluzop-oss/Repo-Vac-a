/**
 * Configuración de entorno del cliente móvil.
 *
 * Para el MVP mantenemos la config en un solo sitio (sin dependencia nativa de `.env`).
 * En producción se recomienda `react-native-config` para inyectar `API_HOST` por build;
 * mientras tanto, edita `API_HOST` aquí o desde una pantalla de ajustes.
 *
 * Recuerda (ver .env.example):
 *   - Emulador Android → http://10.0.2.2:5000
 *   - Emulador iOS     → http://127.0.0.1:5000
 *   - Dispositivo real → http://<IP-LAN-de-tu-PC>:5000
 */

/** Host del backend Flask que sirve la REST API. */
export const API_HOST = 'http://10.0.2.2:5000';

/** Prefijo de la API versionada (coincide con `src/api/__init__.py` → url_prefix=/api/v1). */
export const API_BASE_PATH = '/api/v1';

/** URL base completa de la API. */
export const API_BASE_URL = `${API_HOST}${API_BASE_PATH}`;

/** Timeout de red por defecto (ms). */
export const REQUEST_TIMEOUT_MS = 15000;
