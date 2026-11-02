/**
 * Aviso GLOBAL de escaneo remoto — montado una vez en la raíz de la app (`App.tsx`). Sondea cada
 * `POLL_MS` las solicitudes pendientes de la tienda/almacén del usuario (el backend ya filtra por
 * `centro_codigo` de su propio token — este componente no necesita saber cuál es) y, si hay una sin
 * reclamar, muestra un aviso centrado en pantalla. Al aceptar, reclama la solicitud (atómico: si otro
 * dispositivo se adelantó, se informa y se retira sin más) y abre la cámara reutilizando
 * `ScannerScreen` vía la ruta oculta `EscaneoRemotoFulfill`.
 *
 * SOLO avisa si el dispositivo está inactivo en el MENÚ PRINCIPAL (`Dashboard`) — nunca interrumpe un
 * proceso en curso (otro módulo abierto, o ya atendiendo un escaneo remoto distinto): se comprueba
 * `navigationRef.getCurrentRoute()` antes de sondear/mostrar, y de nuevo en cada cambio de pantalla
 * (para retirar el aviso al instante si el usuario navega fuera, y para ofrecerlo sin esperar al
 * siguiente ciclo en cuanto vuelve al menú).
 */
import React, {useCallback, useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Modal, StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {useTranslation} from 'react-i18next';
import {useAuth} from '@/store/AuthContext';
import {colors} from '@/theme/colors';
import {listarPendientes, reclamarSolicitud, type SolicitudEscaneo} from '@/api/escaneoRemoto';
import {navigationRef} from '@/navigation/navigationRef';

const POLL_MS = 4000;

function enMenuPrincipal(): boolean {
  return navigationRef.isReady() && navigationRef.getCurrentRoute()?.name === 'Dashboard';
}

export default function EscaneoRemotoOverlay() {
  const {t} = useTranslation();
  const {status} = useAuth();
  const [solicitud, setSolicitud] = useState<SolicitudEscaneo | null>(null);
  const [reclamando, setReclamando] = useState(false);
  // Solicitudes que el usuario ya descartó a propósito en ESTE dispositivo — no se le vuelven a
  // ofrecer aunque sigan pendientes en sondeos posteriores (una nueva solicitud sí se mostrará).
  const ignoradasRef = useRef<Set<string>>(new Set());

  const sondear = useCallback(async () => {
    if (status !== 'signedIn' || !enMenuPrincipal()) {
      // Fuera del menú principal (cualquier módulo/proceso abierto, incluida la propia atención de
      // OTRO escaneo remoto): no se molesta ni se sondea. La solicitud sigue viva en el servidor —
      // se ofrecerá en cuanto el dispositivo vuelva a quedar inactivo en el menú.
      return;
    }
    let pendientes: SolicitudEscaneo[] = [];
    try {
      pendientes = await listarPendientes();
    } catch {
      return; // sin red / backend caído: reintenta en el siguiente ciclo, sin ruido
    }
    setSolicitud(prev => {
      if (prev && pendientes.some(p => p.id === prev.id)) {
        return prev; // la que ya se muestra sigue viva — no reemplazar (evita parpadeo)
      }
      return pendientes.find(p => !ignoradasRef.current.has(p.id)) || null;
    });
  }, [status]);

  useEffect(() => {
    if (status !== 'signedIn') {
      setSolicitud(null);
      return;
    }
    sondear();
    const intervalo = setInterval(sondear, POLL_MS);
    return () => clearInterval(intervalo);
  }, [status, sondear]);

  // Reacciona a cada cambio de pantalla: si el usuario acaba de salir del menú principal, retira
  // cualquier aviso visible al instante (no esperar a que el usuario lo ignore ni al próximo sondeo);
  // si acaba de volver al menú, sondea ya mismo en vez de esperar hasta `POLL_MS`.
  useEffect(() => {
    if (status !== 'signedIn' || !navigationRef.isReady()) {
      return;
    }
    const unsub = navigationRef.addListener('state', () => {
      if (enMenuPrincipal()) {
        sondear();
      } else {
        setSolicitud(null);
      }
    });
    return unsub;
  }, [status, sondear]);

  const aceptar = async () => {
    if (!solicitud || reclamando) {
      return;
    }
    setReclamando(true);
    const r = await reclamarSolicitud(solicitud.id);
    setReclamando(false);
    if (!r.ok) {
      // Otro dispositivo de la tienda se adelantó (o expiró justo ahora) — se retira sin insistir,
      // el siguiente sondeo ya no la traerá.
      setSolicitud(null);
      return;
    }
    const idSolicitud = solicitud.id;
    setSolicitud(null);
    if (navigationRef.isReady()) {
      navigationRef.navigate('EscaneoRemotoFulfill', {idSolicitud});
    }
  };

  const ignorar = () => {
    if (solicitud) {
      ignoradasRef.current.add(solicitud.id);
    }
    setSolicitud(null);
  };

  if (!solicitud) {
    return null;
  }

  return (
    <Modal transparent animationType="fade" visible statusBarTranslucent onRequestClose={ignorar}>
      <View style={styles.fondo}>
        <View style={styles.tarjeta}>
          <Text style={styles.icono}>📡</Text>
          <Text style={styles.titulo}>{t('escremoto.titulo', 'Escaneo remoto solicitado')}</Text>
          <Text style={styles.texto}>
            {t('escremoto.cuerpo', 'Alguien en el ordenador de la tienda necesita escanear un código. ¿Lo atiendes desde este dispositivo?')}
          </Text>
          <TouchableOpacity style={styles.btnAceptar} onPress={aceptar} disabled={reclamando}>
            {reclamando ? (
              <ActivityIndicator color={colors.bg} />
            ) : (
              <Text style={styles.btnAceptarTexto}>{t('escremoto.aceptar_escanear_btn', 'Aceptar y escanear')}</Text>
            )}
          </TouchableOpacity>
          <TouchableOpacity style={styles.btnIgnorar} onPress={ignorar} disabled={reclamando}>
            <Text style={styles.btnIgnorarTexto}>{t('escremoto.ignorar_btn', 'Ignorar')}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fondo: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.65)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  tarjeta: {
    backgroundColor: colors.panel,
    borderRadius: 18,
    borderWidth: 2,
    borderColor: colors.cyan,
    padding: 24,
    width: '100%',
    maxWidth: 340,
    alignItems: 'center',
  },
  icono: {fontSize: 40, marginBottom: 8},
  titulo: {color: colors.text, fontSize: 18, fontWeight: '800', marginBottom: 8, textAlign: 'center'},
  texto: {color: colors.textDim, textAlign: 'center', marginBottom: 20, lineHeight: 20},
  btnAceptar: {
    backgroundColor: colors.cyan,
    borderRadius: 12,
    paddingVertical: 14,
    width: '100%',
    alignItems: 'center',
    marginBottom: 10,
  },
  btnAceptarTexto: {color: colors.bg, fontWeight: '800', fontSize: 15},
  btnIgnorar: {paddingVertical: 8},
  btnIgnorarTexto: {color: colors.textDim, fontWeight: '700'},
});
