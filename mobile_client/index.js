/**
 * Punto de entrada de la app (registro del componente raíz).
 * @format
 */
import {AppRegistry} from 'react-native';
import App from './src/App';
import {name as appName} from './app.json';

// Registramos explícitamente 'HelloWorld' para coincidir con la app nativa de Android
AppRegistry.registerComponent(appName || 'HelloWorld', () => App);