/**
 * Aviso GLOBAL de alarma antihurto — montado una vez en la raíz de la app (`App.tsx`), mismo patrón que
 * `EscaneoRemotoOverlay.tsx` pero disparado por FCM (`services/fcm.escucharAlertasAntihurto`) en vez de
 * sondeo: cuando un artículo sale sin pagar y dispara la alarma EAS/RFID
 * (`services/rfid/antihurto.py::alarma_salida_no_pagada`), este componente muestra de inmediato nombre,
 * EAN, precio y foto del artículo — tanto si el mensaje llega con la app en primer plano como si el
 * guardia toca la notificación del sistema con la app en 2º plano o cerrada.
 */
import React, {useEffect, useState} from 'react';
import {Image, Modal, StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {useTranslation} from 'react-i18next';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';
import {imagenArticuloSource} from '@/api/articles';
import {escucharAlertasAntihurto, type AlertaAntihurto} from '@/services/fcm';

export default function AntihurtoOverlay() {
  const {t} = useTranslation();
  const {status} = useAuth();
  const [alerta, setAlerta] = useState<AlertaAntihurto | null>(null);
  const [fotoError, setFotoError] = useState(false);

  useEffect(() => {
    if (status !== 'signedIn') {
      return;
    }
    const dejarDeEscuchar = escucharAlertasAntihurto(datos => {
      setFotoError(false);
      setAlerta(datos);
    });
    return dejarDeEscuchar;
  }, [status]);

  if (!alerta) {
    return null;
  }

  return (
    <Modal transparent animationType="fade" visible statusBarTranslucent onRequestClose={() => setAlerta(null)}>
      <View style={styles.fondo}>
        <View style={styles.tarjeta}>
          <Text style={styles.icono}>🚨</Text>
          <Text style={styles.titulo}>{t('antihurto.titulo', 'Artículo sin pagar en la salida')}</Text>

          {alerta.foto && !fotoError ? (
            <Image
              source={imagenArticuloSource(alerta.ean)}
              style={styles.foto}
              onError={() => setFotoError(true)}
            />
          ) : (
            <View style={[styles.foto, styles.fotoPlaceholder]}>
              <Text style={styles.fotoPlaceholderTexto}>📦</Text>
            </View>
          )}

          <Text style={styles.nombre}>{alerta.nombre}</Text>
          <Text style={styles.detalle}>{t('antihurto.ean_lbl', 'EAN {{e}}', {e: alerta.ean})}</Text>
          {alerta.precio > 0 && <Text style={styles.detalle}>{alerta.precio.toFixed(2)} €</Text>}
          {!!alerta.hora && <Text style={styles.hora}>{alerta.hora}</Text>}

          <TouchableOpacity style={styles.btnEntendido} onPress={() => setAlerta(null)}>
            <Text style={styles.btnEntendidoTexto}>{t('antihurto.entendido_btn', 'Entendido')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fondo: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.75)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  tarjeta: {
    backgroundColor: colors.panel,
    borderRadius: 18,
    borderWidth: 2,
    borderColor: colors.danger,
    padding: 24,
    width: '100%',
    maxWidth: 340,
    alignItems: 'center',
  },
  icono: {fontSize: 40, marginBottom: 8},
  titulo: {
    color: colors.danger,
    fontSize: 18,
    fontWeight: '800',
    marginBottom: 16,
    textAlign: 'center',
  },
  foto: {width: 140, height: 140, borderRadius: 12, marginBottom: 16},
  fotoPlaceholder: {
    backgroundColor: colors.panelAlt,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  fotoPlaceholderTexto: {fontSize: 48},
  nombre: {color: colors.text, fontSize: 16, fontWeight: '700', textAlign: 'center'},
  detalle: {color: colors.textDim, fontSize: 14, marginTop: 4},
  hora: {color: colors.textDim, fontSize: 12, marginTop: 8, opacity: 0.7},
  btnEntendido: {
    backgroundColor: colors.danger,
    borderRadius: 12,
    paddingVertical: 14,
    width: '100%',
    alignItems: 'center',
    marginTop: 20,
  },
  btnEntendidoTexto: {color: colors.bg, fontWeight: '800', fontSize: 15},
});
