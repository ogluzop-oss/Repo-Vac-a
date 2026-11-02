/**
 * Internacionalización de la app móvil (i18next + react-i18next).
 *
 * Mismo criterio que los portales web (`src/backend/portal_i18n.py`): el idioma es una preferencia
 * de visitante NO sensible (se persiste en AsyncStorage, nunca en el Keychain reservado a tokens),
 * independiente del idioma del escritorio. Cada `t('clave', 'Texto por defecto en español')` ya
 * funciona en español sin necesidad de que exista el recurso `es` — el segundo argumento es el
 * fallback honesto (mismo patrón que `tr()` en el escritorio), así que la app nunca muestra una
 * clave sin traducir.
 *
 * Los 21 catálogos se cargan con `require()` estático (no `import()` dinámico): Metro no resuelve
 * una ruta con variable en tiempo de compilación, y el bundle ya es local/offline-first, así que no
 * hay descarga de red que ahorrar con carga perezosa — son ~21 JSON de texto, peso irrelevante.
 *
 * Detección del idioma del dispositivo SIN depender de `react-native-localize` (evita una
 * dependencia nativa nueva solo para esto): se lee el locale ya expuesto por los módulos nativos
 * de RN (`NativeModules.I18nManager` / `SettingsManager`).
 */
import {NativeModules, Platform} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import i18next from 'i18next';
import {initReactI18next} from 'react-i18next';
import {CODIGOS_IDIOMA, IDIOMA_POR_DEFECTO, esIdiomaValido} from './languages';

const STORAGE_KEY = 'sm.idioma';

const RECURSOS: Record<string, object> = {
  es: require('./locales/es.json'),
  en: require('./locales/en.json'),
  zh: require('./locales/zh.json'),
  hi: require('./locales/hi.json'),
  ar: require('./locales/ar.json'),
  pt: require('./locales/pt.json'),
  fr: require('./locales/fr.json'),
  ru: require('./locales/ru.json'),
  ja: require('./locales/ja.json'),
  de: require('./locales/de.json'),
  it: require('./locales/it.json'),
  ko: require('./locales/ko.json'),
  tr: require('./locales/tr.json'),
  nl: require('./locales/nl.json'),
  pl: require('./locales/pl.json'),
  uk: require('./locales/uk.json'),
  id: require('./locales/id.json'),
  vi: require('./locales/vi.json'),
  th: require('./locales/th.json'),
  sv: require('./locales/sv.json'),
  ca: require('./locales/ca.json'),
};

function localeDispositivo(): string {
  try {
    const raw =
      Platform.OS === 'ios'
        ? NativeModules.SettingsManager?.settings?.AppleLocale ||
          NativeModules.SettingsManager?.settings?.AppleLanguages?.[0]
        : NativeModules.I18nManager?.localeIdentifier;
    const codigo = String(raw || '').slice(0, 2).toLowerCase();
    return codigo || IDIOMA_POR_DEFECTO;
  } catch {
    return IDIOMA_POR_DEFECTO;
  }
}

let inicializado: Promise<void> | null = null;

export function iniciarI18n(): Promise<void> {
  if (inicializado) {
    return inicializado;
  }
  inicializado = (async () => {
    let guardado: string | null = null;
    try {
      guardado = await AsyncStorage.getItem(STORAGE_KEY);
    } catch {
      // Sin AsyncStorage disponible: arranca con el idioma del dispositivo, sin romper el inicio.
    }
    const inicial = esIdiomaValido(guardado) ? guardado : localeDispositivo();
    const idioma = esIdiomaValido(inicial) ? inicial : IDIOMA_POR_DEFECTO;

    const resources: Record<string, {translation: object}> = {};
    for (const codigo of CODIGOS_IDIOMA) {
      resources[codigo] = {translation: RECURSOS[codigo] ?? {}};
    }

    await i18next.use(initReactI18next).init({
      lng: idioma,
      fallbackLng: IDIOMA_POR_DEFECTO,
      resources,
      interpolation: {escapeValue: false},
      returnNull: false,
      compatibilityJSON: 'v4',
    });
  })();
  return inicializado;
}

/** Cambia el idioma activo (todos los catálogos ya están cargados en memoria desde el arranque). */
export async function cambiarIdioma(codigo: string): Promise<void> {
  if (!esIdiomaValido(codigo)) {
    return;
  }
  await i18next.changeLanguage(codigo);
  try {
    await AsyncStorage.setItem(STORAGE_KEY, codigo);
  } catch {
    // Preferencia no persistida (almacenamiento no disponible): sigue activa solo esta sesión.
  }
}

export function idiomaActual(): string {
  return i18next.language || IDIOMA_POR_DEFECTO;
}

export {CODIGOS_IDIOMA};
export default i18next;
