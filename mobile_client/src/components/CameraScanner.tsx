/**
 * Escáner de códigos con la cámara (react-native-vision-camera v4).
 *
 * Componente AISLADO: los hooks nativos de la cámara viven solo aquí, de modo que el resto de la
 * app no depende de que el módulo nativo esté enlazado. Se monta bajo demanda desde ScannerScreen;
 * si no hay permiso o dispositivo, informa y deja que la pantalla ofrezca la entrada manual.
 *
 * Requiere configuración nativa (permisos de cámara en AndroidManifest / Info.plist) — ver README.
 */
import React, {useEffect, useRef, useState} from 'react';
import {StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCodeScanner,
  type PhotoFile,
} from 'react-native-vision-camera';
import {useTranslation} from 'react-i18next';
import {colors} from '@/theme/colors';

interface Props {
  /** Se invoca con el valor leído (una sola vez hasta re-armar). Solo aplica en modo 'scan'. */
  onScanned?: (value: string, type: string) => void;
  /** Se invoca con el `file://` local de la foto tomada. Solo aplica en modo 'foto'. */
  onCaptured?: (uri: string) => void;
  active: boolean;
  /** 'scan' (por defecto, comportamiento existente) decodifica códigos; 'foto' muestra un disparador
   * de captura de imagen — mismo módulo nativo ya enlazado (`react-native-vision-camera`), sin
   * dependencia nueva. */
  modo?: 'scan' | 'foto';
}

export default function CameraScanner({onScanned, onCaptured, active, modo = 'scan'}: Props) {
  const {t} = useTranslation();
  const device = useCameraDevice('back');
  const [permiso, setPermiso] = useState<boolean | null>(null);
  const [capturando, setCapturando] = useState(false);
  const camRef = useRef<Camera>(null);

  useEffect(() => {
    (async () => {
      const estado = await Camera.requestCameraPermission();
      setPermiso(estado === 'granted');
    })();
  }, []);

  const codeScanner = useCodeScanner({
    codeTypes: ['ean-13', 'ean-8', 'code-128', 'code-39', 'upc-a', 'qr'],
    onCodeScanned: codes => {
      if (modo !== 'scan') {
        return;
      }
      const first = codes[0];
      if (first?.value) {
        onScanned?.(first.value, first.type ?? 'unknown');
      }
    },
  });

  const disparar = async () => {
    if (!camRef.current || capturando) {
      return;
    }
    setCapturando(true);
    try {
      const foto: PhotoFile = await camRef.current.takePhoto();
      onCaptured?.(`file://${foto.path}`);
    } catch {
      // Silencioso: el usuario puede reintentar pulsando el disparador de nuevo.
    } finally {
      setCapturando(false);
    }
  };

  if (permiso === false) {
    return (
      <View style={styles.msg}>
        <Text style={styles.msgText}>
          {t('camara.permiso_denegado', 'Permiso de cámara denegado. Habilítalo en los ajustes del dispositivo.')}
        </Text>
      </View>
    );
  }
  if (!device || permiso === null) {
    return (
      <View style={styles.msg}>
        <Text style={styles.msgText}>{t('camara.inicializando', 'Inicializando cámara…')}</Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <Camera
        ref={camRef}
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={active}
        photo={modo === 'foto'}
        codeScanner={modo === 'scan' ? codeScanner : undefined}
      />
      {modo === 'scan' ? (
        <View style={styles.reticle} />
      ) : (
        <TouchableOpacity
          style={[styles.disparador, capturando && styles.disparadorActivo]}
          onPress={disparar}
          disabled={capturando}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {flex: 1, overflow: 'hidden', borderRadius: 14, backgroundColor: '#000'},
  reticle: {
    position: 'absolute',
    alignSelf: 'center',
    top: '30%',
    width: '70%',
    height: 140,
    borderWidth: 2,
    borderColor: colors.cyan,
    borderRadius: 12,
  },
  msg: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 20},
  msgText: {color: colors.textDim, textAlign: 'center'},
  disparador: {
    position: 'absolute',
    alignSelf: 'center',
    bottom: 24,
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: colors.bg,
    borderWidth: 4,
    borderColor: colors.cyan,
  },
  disparadorActivo: {opacity: 0.5},
});
