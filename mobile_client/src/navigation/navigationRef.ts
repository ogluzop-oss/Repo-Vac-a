/**
 * Ref de navegación global — permite navegar desde FUERA del árbol de pantallas (p. ej.
 * `EscaneoRemotoOverlay`, montado como hermano del `Stack.Navigator`, no como una pantalla) sin
 * pasar por el prop `navigation` de ningún componente. Patrón oficial de React Navigation.
 */
import {createNavigationContainerRef} from '@react-navigation/native';
import type {AppStackParamList} from './types';

export const navigationRef = createNavigationContainerRef<AppStackParamList>();
