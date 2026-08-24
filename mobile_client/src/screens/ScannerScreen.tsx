/**
 * Pantalla de prueba de ESCANEO de códigos de barras (preparada para integrar la cámara).
 *
 * - Intenta montar la cámara (CameraScanner / vision-camera). Si el módulo nativo no está enlazado
 *   o falla, un ErrorBoundary degrada a la ENTRADA MANUAL, de modo que el flujo offline-first se
 *   puede probar de extremo a extremo sin hardware.
 * - Cada lectura se ENCOLA en el Outbox local (SQLite) como operación offline-first; se sincroniza
 *   luego desde el Dashboard contra la REST API (/api/v1/stock).
 */
import React, {useCallback, useState} from 'react';
import {
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import CameraScanner from '@/components/CameraScanner';
import {outbox} from '@/db/sync';
import {colors} from '@/theme/colors';
import type {ScannerProps} from '@/navigation/types';

/** Límite mínimo para no romper la pantalla si la cámara nativa no está disponible. */
class CameraBoundary extends React.Component<
  {children: React.ReactNode; onFail: () => void},
  {failed: boolean}
> {
  state = {failed: false};
  static getDerivedStateFromError() {
    return {failed: true};
  }
  componentDidCatch() {
    this.props.onFail();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function ScannerScreen({navigation}: ScannerProps) {
  const [camaraDisponible, setCamaraDisponible] = useState(true);
  const [manual, setManual] = useState('');
  const [ultimo, setUltimo] = useState<string | null>(null);
  const [encolados, setEncolados] = useState(0);

  const registrar = useCallback(async (codigo: string, tipo = 'manual') => {
    const limpio = codigo.trim();
    if (!limpio) {
      return;
    }
    await outbox.encolar('stock', 'scan', {
      codigo: limpio,
      tipo,
      ts: Date.now() / 1000,
    });
    setUltimo(limpio);
    setEncolados(n => n + 1);
    setManual('');
  }, []);

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>‹ Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Escaneo</Text>
        <View style={{width: 60}} />
      </View>

      <View style={styles.cameraBox}>
        {camaraDisponible ? (
          <CameraBoundary onFail={() => setCamaraDisponible(false)}>
            <CameraScanner
              active
              onScanned={(value, type) => registrar(value, type)}
            />
          </CameraBoundary>
        ) : (
          <View style={styles.noCam}>
            <Text style={styles.noCamText}>
              Cámara no disponible en este entorno.{'\n'}Usa la entrada manual para probar el flujo.
            </Text>
          </View>
        )}
      </View>

      <View style={styles.manualBox}>
        <Text style={styles.label}>Entrada manual (o simular lectura)</Text>
        <View style={styles.manualRow}>
          <TextInput
            style={styles.input}
            placeholder="Código de barras / EAN"
            placeholderTextColor={colors.textDim}
            value={manual}
            onChangeText={setManual}
            autoCapitalize="characters"
          />
          <TouchableOpacity style={styles.addBtn} onPress={() => registrar(manual)}>
            <Text style={styles.addBtnText}>Registrar</Text>
          </TouchableOpacity>
        </View>

        {ultimo ? (
          <Text style={styles.ok}>
            ✓ Encolado «{ultimo}» ({encolados} en esta sesión). Sincroniza desde el Dashboard.
          </Text>
        ) : (
          <Text style={styles.hint}>
            Cada lectura se guarda en el Outbox local y se enviará a /api/v1/stock al sincronizar.
          </Text>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.bg},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  back: {color: colors.cyan, fontSize: 16, fontWeight: '700', width: 60},
  title: {color: colors.text, fontSize: 18, fontWeight: '800'},
  cameraBox: {flex: 1, margin: 16, borderRadius: 14, overflow: 'hidden'},
  noCam: {
    flex: 1,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  noCamText: {color: colors.textDim, textAlign: 'center', lineHeight: 22},
  manualBox: {
    backgroundColor: colors.panel,
    borderTopWidth: 1,
    borderColor: colors.border,
    padding: 16,
  },
  label: {color: colors.textDim, marginBottom: 8, fontWeight: '700'},
  manualRow: {flexDirection: 'row', alignItems: 'center'},
  input: {
    flex: 1,
    backgroundColor: colors.bg,
    color: colors.text,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginRight: 8,
    fontSize: 16,
  },
  addBtn: {backgroundColor: colors.cyan, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 12},
  addBtnText: {color: colors.bg, fontWeight: '800'},
  ok: {color: colors.ok, marginTop: 12},
  hint: {color: colors.textDim, marginTop: 12, fontSize: 12},
});
