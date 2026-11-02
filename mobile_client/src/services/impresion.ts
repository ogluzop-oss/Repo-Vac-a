/**
 * Puente AISLADO con `react-native-blob-util` — mismo criterio que `services/fcm.ts` aísla Firebase:
 * descarga un PDF ya generado por el backend (con el token de auth) y lo abre con el selector nativo de
 * Android (compartir/imprimir), sin necesidad de un FileProvider propio (la librería ya trae el suyo).
 * Cualquier fallo (módulo no enlazado, sin visor de PDF instalado) degrada a un error legible — nunca
 * tumba la app.
 */

export async function abrirPdf(
  url: string,
  headers: Record<string, string>,
  nombreFichero: string,
): Promise<{ok: boolean; error?: string}> {
  try {
    const ReactNativeBlobUtil = require('react-native-blob-util').default;
    const {dirs} = ReactNativeBlobUtil.fs;
    const destino = `${dirs.CacheDir}/${nombreFichero}`;
    const res = await ReactNativeBlobUtil.config({path: destino}).fetch('GET', url, headers);
    const path = res.path();
    await ReactNativeBlobUtil.android.actionViewIntent(path, 'application/pdf');
    return {ok: true};
  } catch {
    return {ok: false, error: 'No se pudo abrir el PDF (¿tienes un lector de PDF instalado?).'};
  }
}
