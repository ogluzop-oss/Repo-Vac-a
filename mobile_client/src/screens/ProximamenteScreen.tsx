/**
 * Placeholder HONESTO para capacidades del catálogo (`api/capabilities.ts`) cuyo endpoint REST
 * todavía no existe en el backend (ver `src/services/mobile/core.py`, que las marca como
 * "funcionalidades previstas"). No se simulan datos: se explica el motivo real.
 */
import React from 'react';
import {StyleSheet, Text, TouchableOpacity, View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {useTranslation} from 'react-i18next';
import {colors} from '@/theme/colors';
import type {ProximamenteProps} from '@/navigation/types';

export default function ProximamenteScreen({navigation, route}: ProximamenteProps) {
  const {t} = useTranslation();
  const {label, endpoint, icon} = route.params;

  return (
    <SafeAreaView style={styles.root} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.back}>{t('proximamente.volver', '‹ Volver')}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>{label}</Text>
        <View style={{width: 90}} />
      </View>

      <View style={styles.centered}>
        <Text style={styles.icon}>{icon}</Text>
        <Text style={styles.heading}>{t('proximamente.titulo', 'Próximamente')}</Text>
        <Text style={styles.body}>
          {t('proximamente.cuerpo_pre', 'Esta capacidad está prevista en el catálogo móvil, pero el backend todavía no expone')}{' '}
          <Text style={styles.mono}>{endpoint}</Text>.{'\n\n'}
          {t('proximamente.cuerpo_post',
             'En cuanto ese endpoint esté disponible en la REST API, esta pantalla se conectará con datos reales — no se muestran datos simulados.')}
        </Text>
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
  back: {color: colors.cyan, fontSize: 16, fontWeight: '700', width: 90},
  title: {color: colors.text, fontSize: 18, fontWeight: '800'},
  centered: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32},
  icon: {fontSize: 40, marginBottom: 12},
  heading: {color: colors.text, fontWeight: '800', fontSize: 18, marginBottom: 10},
  body: {color: colors.textDim, textAlign: 'center', lineHeight: 21},
  mono: {color: colors.cyan, fontWeight: '700'},
});
