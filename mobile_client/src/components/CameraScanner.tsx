/**
 * Escáner de códigos con la cámara (react-native-vision-camera v4).
 *
 * Componente AISLADO: los hooks nativos de la cámara viven solo aquí, de modo que el resto de la
 * app no depende de que el módulo nativo esté enlazado. Se monta bajo demanda desde ScannerScreen;
 * si no hay permiso o dispositivo, informa y deja que la pantalla ofrezca la entrada manual.
 *
 * Requiere configuración nativa (permisos de cámara en AndroidManifest / Info.plist) — ver README.
 */
import React, {useEffect, useState} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {
  Camera,
  useCameraDevice,
  useCodeScanner,
} from 'react-native-vision-camera';
import {colors} from '@/theme/colors';

interface Props {
  /** Se invoca con el valor leído (una sola vez hasta re-armar). */
  onScanned: (value: string, type: string) => void;
  active: boolean;
}

export default function CameraScanner({onScanned, active}: Props) {
  const device = useCameraDevice('back');
  const [permiso, setPermiso] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      const estado = await Camera.requestCameraPermission();
      setPermiso(estado === 'granted');
    })();
  }, []);

  const codeScanner = useCodeScanner({
    codeTypes: ['ean-13', 'ean-8', 'code-128', 'code-39', 'upc-a', 'qr'],
    onCodeScanned: codes => {
      const first = codes[0];
      if (first?.value) {
        onScanned(first.value, first.type ?? 'unknown');
      }
    },
  });

  if (permiso === false) {
    return (
      <View style={styles.msg}>
        <Text style={styles.msgText}>
          Permiso de cámara denegado. Habilítalo en los ajustes del dispositivo.
        </Text>
      </View>
    );
  }
  if (!device || permiso === null) {
    return (
      <View style={styles.msg}>
        <Text style={styles.msgText}>Inicializando cámara…</Text>
      </View>
    );
  }

  return (
    <View style={styles.wrap}>
      <Camera
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={active}
        codeScanner={codeScanner}
      />
      <View style={styles.reticle} />
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
});
