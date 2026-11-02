/**
 * Pantalla OCULTA (no aparece en el Dashboard ni en ningún catálogo): solo se entra desde
 * `EscaneoRemotoOverlay` al aceptar un aviso de escaneo remoto, ya con la solicitud RECLAMADA. Abre
 * la cámara automáticamente (reutilizando `ScannerScreen` vía el mecanismo `volverA` existente) y, en
 * cuanto vuelve con un valor escaneado, lo envía y regresa al Dashboard.
 */
import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {colors} from '@/theme/colors';
import {cancelarSolicitud, completarSolicitud} from '@/api/escaneoRemoto';
import type {EscaneoRemotoFulfillProps} from '@/navigation/types';

export default function EscaneoRemotoFulfillScreen({navigation, route}: EscaneoRemotoFulfillProps) {
  const {t} = useTranslation();
  const {idSolicitud, escaneado} = route.params;
  const [estado, setEstado] = useState<'abriendo' | 'enviando' | 'hecho' | 'error' | 'vuelto'>(
    'abriendo',
  );
  const [mensaje, setMensaje] = useState<string | null>(null);
  const abiertoRef = useRef(false);

  useEffect(() => {
    if (escaneado) {
      let cancelado = false;
      setEstado('enviando');
      completarSolicitud(idSolicitud, escaneado).then(r => {
        if (cancelado) {
          return;
        }
        if (r.ok) {
          setEstado('hecho');
          setTimeout(() => {
            if (!cancelado) {
              navigation.reset({index: 0, routes: [{name: 'Dashboard'}]});
            }
          }, 1200);
        } else {
          setEstado('error');
          setMensaje(r.error);
        }
      });
      return () => {
        cancelado = true;
      };
    }
    if (!abiertoRef.current) {
      abiertoRef.current = true;
      navigation.navigate('Scanner', {volverA: 'EscaneoRemotoFulfill'});
    } else {
      // Vuelve de la cámara SIN escanear (pulsó "Volver") — no reabrir solo; se ofrece reintentar o
      // cancelar la solicitud reclamada.
      setEstado('vuelto');
    }
  }, [escaneado, idSolicitud, navigation]);

  const cancelar = async () => {
    await cancelarSolicitud(idSolicitud);
    navigation.reset({index: 0, routes: [{name: 'Dashboard'}]});
  };

  const reintentar = () => {
    navigation.navigate('Scanner', {volverA: 'EscaneoRemotoFulfill'});
  };

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.centro}>
        {estado === 'hecho' ? (
          <>
            <Text style={styles.icono}>✅</Text>
            <Text style={styles.texto}>{t('escremoto.enviado_ordenador', 'Escaneo enviado al ordenador.')}</Text>
          </>
        ) : estado === 'error' ? (
          <>
            <Text style={styles.icono}>⚠️</Text>
            <Text style={styles.texto}>{mensaje || t('escremoto.no_se_pudo_enviar', 'No se pudo enviar el escaneo.')}</Text>
            <TouchableOpacity style={styles.btn} onPress={cancelar}>
              <Text style={styles.btnTexto}>{t('escremoto.volver_panel', 'Volver al panel')}</Text>
            </TouchableOpacity>
          </>
        ) : estado === 'vuelto' ? (
          <>
            <Text style={styles.icono}>📡</Text>
            <Text style={styles.texto}>{t('escremoto.pendiente_completar', 'Solicitud de escaneo pendiente de completar.')}</Text>
            <TouchableOpacity style={styles.btn} onPress={reintentar}>
              <Text style={styles.btnTexto}>{t('escremoto.volver_camara', 'Volver a la cámara')}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.btnCancelar} onPress={cancelar}>
              <Text style={styles.btnCancelarTexto}>{t('escremoto.cancelar_solicitud', 'Cancelar solicitud')}</Text>
            </TouchableOpacity>
          </>
        ) : (
          <>
            <ActivityIndicator color={colors.cyan} size="large" />
            <Text style={styles.texto}>
              {estado === 'enviando'
                ? t('escremoto.enviando_codigo', 'Enviando el código escaneado…')
                : t('escremoto.abriendo_camara', 'Abriendo la cámara…')}
            </Text>
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg},
  centro: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24},
  icono: {fontSize: 48, marginBottom: 12},
  texto: {color: colors.text, fontSize: 15, textAlign: 'center', marginTop: 14, lineHeight: 22},
  btn: {
    marginTop: 20,
    backgroundColor: colors.cyan,
    borderRadius: 10,
    paddingVertical: 12,
    paddingHorizontal: 24,
  },
  btnTexto: {color: colors.bg, fontWeight: '800'},
  btnCancelar: {marginTop: 16, paddingVertical: 8},
  btnCancelarTexto: {color: colors.textDim, fontWeight: '700'},
});
