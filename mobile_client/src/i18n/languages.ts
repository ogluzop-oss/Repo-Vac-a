/**
 * Catálogo de idiomas soportados — mismo conjunto de 21 idiomas que el escritorio y los portales
 * web (`src/utils/i18n.py::LANGUAGES`), para que un usuario vea el mismo idioma disponible en
 * cualquier superficie de Smart Manager.
 */
export interface IdiomaInfo {
  native: string;
  flag: string;
  rtl: boolean;
}

export const IDIOMA_POR_DEFECTO = 'es';

export const IDIOMAS: Record<string, IdiomaInfo> = {
  es: {native: 'Español', flag: '🇪🇸', rtl: false},
  en: {native: 'English', flag: '🇬🇧', rtl: false},
  zh: {native: '中文', flag: '🇨🇳', rtl: false},
  hi: {native: 'हिन्दी', flag: '🇮🇳', rtl: false},
  ar: {native: 'العربية', flag: '🇸🇦', rtl: true},
  pt: {native: 'Português', flag: '🇵🇹', rtl: false},
  fr: {native: 'Français', flag: '🇫🇷', rtl: false},
  ru: {native: 'Русский', flag: '🇷🇺', rtl: false},
  ja: {native: '日本語', flag: '🇯🇵', rtl: false},
  de: {native: 'Deutsch', flag: '🇩🇪', rtl: false},
  it: {native: 'Italiano', flag: '🇮🇹', rtl: false},
  ko: {native: '한국어', flag: '🇰🇷', rtl: false},
  tr: {native: 'Türkçe', flag: '🇹🇷', rtl: false},
  nl: {native: 'Nederlands', flag: '🇳🇱', rtl: false},
  pl: {native: 'Polski', flag: '🇵🇱', rtl: false},
  uk: {native: 'Українська', flag: '🇺🇦', rtl: false},
  id: {native: 'Indonesia', flag: '🇮🇩', rtl: false},
  vi: {native: 'Tiếng Việt', flag: '🇻🇳', rtl: false},
  th: {native: 'ไทย', flag: '🇹🇭', rtl: false},
  sv: {native: 'Svenska', flag: '🇸🇪', rtl: false},
  ca: {native: 'Català', flag: '🇪🇸', rtl: false},
};

export const CODIGOS_IDIOMA = Object.keys(IDIOMAS);

export function esIdiomaValido(codigo: string | null | undefined): codigo is string {
  return !!codigo && codigo in IDIOMAS;
}
