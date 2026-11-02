/**
 * Selector de idioma — mismo criterio que `portal_i18n.selector_idioma_html` en los portales web:
 * preferencia NO sensible, independiente por visitante/dispositivo (ver `src/i18n/index.ts`).
 * Botón compacto (bandera + código) que abre un modal con los 21 idiomas soportados.
 */
import React, {useState} from 'react';
import {FlatList, Modal, Pressable, StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {useTranslation} from 'react-i18next';
import {cambiarIdioma, idiomaActual} from '@/i18n';
import {CODIGOS_IDIOMA, IDIOMAS} from '@/i18n/languages';
import {colors} from '@/theme/colors';

export default function LanguageSwitcher() {
  const {t} = useTranslation();
  const [abierto, setAbierto] = useState(false);
  const actual = idiomaActual();
  const info = IDIOMAS[actual] ?? IDIOMAS.es!;

  const seleccionar = async (codigo: string) => {
    setAbierto(false);
    await cambiarIdioma(codigo);
  };

  return (
    <>
      <TouchableOpacity
        style={styles.boton}
        onPress={() => setAbierto(true)}
        accessibilityLabel={t('idioma.seleccionar', 'Seleccionar idioma')}>
        <Text style={styles.bandera}>{info.flag}</Text>
        <Text style={styles.codigo}>{actual.toUpperCase()}</Text>
      </TouchableOpacity>

      <Modal visible={abierto} transparent animationType="fade" onRequestClose={() => setAbierto(false)}>
        <Pressable style={styles.fondo} onPress={() => setAbierto(false)}>
          <View style={styles.hoja}>
            <Text style={styles.titulo}>{t('idioma.titulo', 'Idioma')}</Text>
            <FlatList
              data={CODIGOS_IDIOMA}
              keyExtractor={c => c}
              style={styles.lista}
              renderItem={({item}) => {
                const li = IDIOMAS[item] ?? IDIOMAS.es!;
                const activo = item === actual;
                return (
                  <TouchableOpacity
                    style={[styles.fila, activo && styles.filaActiva]}
                    onPress={() => seleccionar(item)}>
                    <Text style={styles.filaBandera}>{li.flag}</Text>
                    <Text style={[styles.filaTexto, activo && styles.filaTextoActivo]}>
                      {li.native}
                    </Text>
                    {activo && <Text style={styles.check}>✓</Text>}
                  </TouchableOpacity>
                );
              }}
            />
          </View>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  boton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  bandera: {fontSize: 16, marginRight: 4},
  codigo: {color: colors.text, fontWeight: '700', fontSize: 12},
  fondo: {flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end'},
  hoja: {
    backgroundColor: colors.panel,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    paddingTop: 16,
    maxHeight: '70%',
    borderWidth: 1,
    borderColor: colors.border,
  },
  titulo: {color: colors.text, fontWeight: '800', fontSize: 16, paddingHorizontal: 20, marginBottom: 8},
  lista: {paddingHorizontal: 8, paddingBottom: 24},
  fila: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
  },
  filaActiva: {backgroundColor: colors.bg},
  filaBandera: {fontSize: 20, marginRight: 12},
  filaTexto: {color: colors.text, fontSize: 15, flex: 1},
  filaTextoActivo: {color: colors.cyan, fontWeight: '700'},
  check: {color: colors.cyan, fontWeight: '800'},
});
