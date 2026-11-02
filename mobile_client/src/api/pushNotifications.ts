/**
 * Registro del token de dispositivo para push (FCM). Espejo de
 * `POST /notifications/device-token` (`src/api/routers/notifications.py`).
 */
import {api} from './client';

export async function registrarTokenDispositivo(
  token: string,
  plataforma: string = 'android',
): Promise<boolean> {
  const r = await api.post<{ok?: boolean}>('/notifications/device-token', {
    body: {token, plataforma},
  });
  return r.ok;
}
