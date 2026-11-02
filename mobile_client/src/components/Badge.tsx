/**
 * Círculo rojo con número blanco superpuesto en la esquina de una tarjeta — mismo criterio visual
 * que `MenuCardButton._badge` en el menú de escritorio (`src/gui/menu_principal.py`): oculto si
 * `n<=0`, muestra "99+" si `n>99`. Color `#FF3B30` fijo (no `colors.danger`) para que sea EXACTAMENTE
 * el mismo rojo que usa el escritorio, no el rojo de error de la paleta móvil.
 */
import React from 'react';
import {StyleSheet, Text, View} from 'react-native';

const ROJO_BADGE = '#FF3B30';

export default function Badge({n}: {n: number}) {
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
    top: 6,
    right: 6,
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: ROJO_BADGE,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
    zIndex: 10,
  },
  texto: {color: '#FFFFFF', fontSize: 11, fontWeight: '800'},
});
