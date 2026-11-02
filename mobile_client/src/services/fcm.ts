/**
 * Puente AISLADO con Firebase Cloud Messaging (@react-native-firebase/messaging) — mismo criterio que
 * `components/CameraScanner.tsx` aísla `react-native-vision-camera`: el resto de la app no depende de
 * que el módulo nativo esté enlazado ni de que Google Play Services esté disponible. Cualquier fallo
 * (módulo no enlazado, sin Play Services, permiso denegado) degrada a `null`/no-op — nunca tumba la app.
 *
 * Requiere configuración nativa (ver `android/app/build.gradle` + `google-services.json`) — ver
 * checklist de Firebase Console en el plan de implementación.
 */
import type {FirebaseMessagingTypes} from '@react-native-firebase/messaging';

export interface AlertaAntihurto {
  ean: string;
  nombre: string;
  foto: string | null;
  precio: number;
  hora: string;
}

function _messaging() {
  // Import perezoso: si el módulo nativo no está enlazado, el require lanza y lo capturamos arriba.
  return require('@react-native-firebase/messaging').default();
}

/** Pide permiso de notificaciones y devuelve el token de dispositivo, o `null` si algo falla/deniega. */
export async function pedirPermisoYObtenerToken(): Promise<string | null> {
  try {
    const messagingModule = require('@react-native-firebase/messaging');
    const m = _messaging();
    const estado = await m.requestPermission();
    const concedido =
      estado === messagingModule.AuthorizationStatus.AUTHORIZED ||
      estado === messagingModule.AuthorizationStatus.PROVISIONAL;
    if (!concedido) {
      return null;
    }
    return await m.getToken();
  } catch {
    return null; // módulo no enlazado / sin Play Services / permiso denegado — degradable
  }
}

function _datosAlerta(
  remoteMessage: FirebaseMessagingTypes.RemoteMessage | null | undefined,
): AlertaAntihurto | null {
  const data = remoteMessage?.data;
  if (!data || data.evento !== 'salida_no_pagada') {
    return null;
  }
  return {
    ean: String(data.ean ?? ''),
    nombre: String(data.nombre ?? data.ean ?? ''),
    foto: data.foto ? String(data.foto) : null,
    precio: Number(data.precio ?? 0),
    hora: String(data.hora ?? ''),
  };
}

/**
 * Registra los 4 puntos de escucha de FCM (primer plano, 2º plano, killed-app, y tap sobre la
 * notificación del sistema) y llama a `onAlerta` cuando el mensaje es una alarma antihurto
 * (`data.evento === 'salida_no_pagada'`). Devuelve una función de limpieza (o no-op si el módulo no
 * está disponible).
 */
export function escucharAlertasAntihurto(onAlerta: (datos: AlertaAntihurto) => void): () => void {
  try {
    const m = _messaging();

    const bajasFn = m.onMessage(async (remoteMessage: FirebaseMessagingTypes.RemoteMessage) => {
      const alerta = _datosAlerta(remoteMessage);
      if (alerta) {
        onAlerta(alerta);
      }
    });

    m.setBackgroundMessageHandler(async () => {
      // La bandeja del sistema ya muestra la notificación (payload `notification`); no hace falta
      // acción aquí — la app la procesa al abrirse vía onNotificationOpenedApp/getInitialNotification.
    });

    const bajaAbierta = m.onNotificationOpenedApp(
      (remoteMessage: FirebaseMessagingTypes.RemoteMessage) => {
        const alerta = _datosAlerta(remoteMessage);
        if (alerta) {
          onAlerta(alerta);
        }
      },
    );

    m.getInitialNotification().then(
      (remoteMessage: FirebaseMessagingTypes.RemoteMessage | null) => {
        const alerta = _datosAlerta(remoteMessage);
        if (alerta) {
          onAlerta(alerta);
        }
      },
    );

    return () => {
      bajasFn();
      bajaAbierta();
    };
  } catch {
    return () => {}; // módulo no enlazado — degradable, sin alertas push (no rompe la app)
  }
}
