/**
 * Variante compacta de `Badge.tsx` para pestañas pequeñas (pastillas `tab`/`tabActive` de
 * LogisticaScreen/DistribucionPickingScreen/EtiquetasScreen/UbicacionScreen, etc.): mismo color/
 * criterio "99+" que el badge de módulo del Dashboard, pero más pequeño y con el offset hacia FUERA
 * del pill (`top:-6,right:-6`) en vez de hacia dentro (`top:6,right:6`), porque una pastilla de
 * pestaña es mucho más baja que una tarjeta del Dashboard y el círculo de 22px del `Badge` original
 * la recortaría o desbordaría mal.
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';

const ROJO_BADGE = '#FF3B30';

export default function TabBadge({n}: {n: number}) {
  if (!n || n <= 0) {
    return null;
  }
  return (
    <View style={styles.badge}>
      <Text style={styles.texto} numberOfLines={1}>
        {n > 99 ? '99+' : String(n)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    position: 'absolute',
    top: -6,
    right: -6,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: ROJO_BADGE,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
    zIndex: 10,
  },
  texto: {color: '#FFFFFF', fontSize: 9, fontWeight: '800'},
});
