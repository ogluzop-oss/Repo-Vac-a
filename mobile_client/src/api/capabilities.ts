/**
 * Capacidades de la plataforma móvil — espejo de `src/services/mobile/core.py`.
 *
 * Mapa `capacidad -> recurso REST oficial` que las alimenta (SIEMPRE /api/v1, nunca SQL). El
 * Dashboard construye su menú a partir de este catálogo, de modo que añadir una capacidad en el
 * servidor se refleja aquí con una sola línea.
 */
import {api} from './client';

export interface Capability {
  key: string;
  /** Etiqueta legible para el menú. */
  label: string;
  /** Ruta REST (relativa a /api/v1) que alimenta la capacidad. */
  endpoint: string;
  /** Emoji/símbolo para la tarjeta (placeholder hasta integrar un set de iconos). */
  icon: string;
}

/**
 * Rediseño móvil (Grupo A — trabajo físico que escritorio ya intentaba torpemente — y Grupo B —
 * trabajo físico que escritorio ni intentaba, requiere una captura nueva como una foto): el móvil ya
 * NO es una versión reducida de escritorio — solo contiene los pasos que exigen presencia física
 * (escanear un código/QR, caminar hasta una ubicación, fotografiar algo in situ). Cada capacidad de
 * aquí corresponde a un momento concreto de ese tipo (ver comentarios de cada entrada). Todo lo que
 * sea buscar/listar/rellenar un formulario sin componente físico se queda en escritorio, donde ya
 * funciona bien — duplicarlo en móvil sería el mismo sistema dos veces.
 */
export const CAPABILITIES: Capability[] = [
  // Stock: recuento físico de un inventario abierto — solo tiene sentido estando delante de la
  // estantería contando; Stock tienda/Almacén/Editar/Lotes (búsqueda y formularios) se quedan en
  // escritorio.
  {key: 'stock', label: 'Inventario', endpoint: '/stock/inventory', icon: '🧮'},
  // Mermas (Grupo B, módulo 1): fotografiar el producto dañado/caducado en el momento — la foto es el
  // componente físico, por eso esta vez SÍ vuelve a móvil (a diferencia de la versión sin foto
  // retirada en el Grupo A, un formulario idéntico al de escritorio).
  {key: 'mermas', label: 'Mermas', endpoint: '/losses', icon: '📸'},
  // Logística: recepción de palet (escanear EAN al llegar mercancía) + picking de traspasos (checklist
  // mientras se camina el almacén recogiendo artículos). Traspasos/Expediciones/Incidencias/Historial
  // se quedan en escritorio (crear/consultar, sin componente físico).
  {key: 'logistica', label: 'Logística', endpoint: '/logistics/transfers', icon: '🚚'},
  // Ubicación: escanear el QR de un satélite físico para autolocalizarse y trazar una ruta hasta un
  // artículo, o escanear la etiqueta de una estantería para asignarle un artículo.
  {key: 'ubicacion', label: 'Ubicación', endpoint: '/location', icon: '📍'},
  // Etiquetas: localizar una etiqueta ESL físicamente en el lineal (hacerla parpadear y encontrarla).
  {key: 'etiquetas', label: 'Etiquetas', endpoint: '/labels/esl', icon: '🔖'},
  // Distribución (pedidos B2B): picking — caminar el almacén siguiendo la ruta óptima para recoger un
  // pedido de cliente. Crear/expedir el pedido se queda en escritorio (gestión, no trabajo físico).
  {key: 'pedidos', label: 'Pedidos', endpoint: '/distribution/picking', icon: '🧾'},
  // GMAO (Grupo B, módulo 2): escanear el QR de un activo para abrir sus OTs in situ, iniciarlas y
  // fotografiar la reparación antes de finalizar. Crear/planificar la OT se queda en escritorio.
  {key: 'gmao', label: 'Mantenimiento', endpoint: '/gmao/assets', icon: '🔧'},
  // Calidad (Grupo B, módulo 3): fotografiar el artículo/lote inspeccionado in situ (recepción/
  // producción/final). Si el resultado es "rechazada" el backend abre la No Conformidad solo.
  {key: 'calidad', label: 'Calidad', endpoint: '/calidad/inspections', icon: '🔬'},
  // SAT (Grupo B, módulo 4): fotografiar la intervención técnica in situ. Un ticket puede llevar varias
  // visitas antes de resolverse, cada una con su propia foto. Sin firma (ver api/sat.ts).
  {key: 'sat', label: 'SAT', endpoint: '/sat/tickets', icon: '🛠️'},
  // Transporte/Reparto (Grupo B, módulo 5): fotografiar la entrega in situ, o reportar una incidencia
  // (cliente ausente/rechazo/dirección incorrecta) si no se pudo entregar. Sin firma (ver api/transporte.ts).
  {key: 'transporte', label: 'Reparto', endpoint: '/transporte/routes', icon: '📦'},
  // Obrador (Grupo B, módulo 6, edición Bakery): fotografiar el lote terminado al registrar un parte de
  // producción diaria — un único punto de guardado, sin iniciar/finalizar como GMAO/SAT.
  {key: 'obrador', label: 'Obrador', endpoint: '/obrador/parts', icon: '🥖'},
  // MRP (Grupo B, módulo 7, último): fotografiar el lote producido al registrar producción de una OF —
  // repetible, una foto por lote. Consumir materiales no lleva foto (nada fotografiable en ese instante).
  {key: 'mrp', label: 'Producción', endpoint: '/mrp/orders', icon: '🏭'},
  // Correo: ÚNICA excepción deliberada a la regla de "solo presencia física" de arriba — no hay
  // componente físico, pero sí urgencia real (leer/responder una circular, encuesta o correo
  // urgente sin esperar a volver al escritorio). Bandeja unificada (Gmail solo lectura + circulares/
  // encuestas internas) + responder/reenviar + un compositor básico de Nuevo mensaje/Nueva encuesta
  // con Para/CC/Cco real; SIN borradores/papelera/programados/pospuestos/estrella (administración de
  // escritorio, mismo criterio de recorte que el resto del catálogo — ver CorreoScreen.tsx).
  {key: 'correo', label: 'Correo', endpoint: '/correo/bandeja', icon: '📧'},
  // Gastos de viaje: ÚNICA pieza de autoservicio RRHH que vuelve al móvil (petición explícita,
  // decisión confirmada tras auditoría — ver api/gastosViaje.ts): fotografiar el ticket EN EL
  // MOMENTO con lectura automática por IA SÍ tiene componente físico, igual que Mermas/Calidad/
  // SAT. Nóminas/vacaciones/documentos pendientes de firma se quedan en escritorio (Portal del
  // Empleado/RRHH, donde ya existían y maduran) — son formularios/consultas sin componente físico.
  {key: 'gastos_viaje', label: 'Gastos de viaje', endpoint: '/rrhh/me/gastos', icon: '🧾'},
  // Info Artículo: ÚNICA capacidad del catálogo con DOS pestañas (petición explícita), solo las que
  // escritorio llama "Buscar artículo" e "Imagen artículo" — NO "Editar artículo" ni "Familias"
  // (administración pura, sin componente físico, se quedan en escritorio). "Imagen artículo" es
  // Grupo B puro (fotografiar el artículo en el lineal). "Buscar artículo" se incluye junto a ella
  // por la misma petición: consultar stock/ubicación/precio de pie frente a la estantería. La ficha
  // mostrada reutiliza EXACTAMENTE los mismos datos que escritorio (ver api/articles.ts).
  {key: 'info_articulo', label: 'Info artículo', endpoint: '/articles', icon: '🔍'},
];
// El escaneo remoto (delegar un escaneo de escritorio al móvil) ya NO es una capacidad con tarjeta
// propia: se atiende desde cualquier pantalla vía el aviso global `EscaneoRemotoOverlay` — antes
// tenía dos entradas redundantes aquí ("Escanear artículo" y "Escaneo remoto") que duplicaban el
// botón "Escanear" que ya existía en el Dashboard.

export const PLATFORM = {
  version: '1.0.0',
  offlineFirst: true,
} as const;

/** Edición/vertical de esta instalación + qué capacidades del catálogo le corresponden — mismo motor
 * que ya gatea escritorio (`services.verticales`), para no mostrar módulos de una edición distinta a
 * la elegida al instalar (p. ej. nunca Obrador Y Producción/MRP a la vez: son excluyentes). Público
 * (sin token): hace falta ANTES incluso de iniciar sesión para construir el catálogo del Dashboard. */
export async function capacidadesVisibles(): Promise<Capability[]> {
  try {
    const r = await api.get<{edicion: string; capacidades_visibles: string[]}>('/system/edition', {
      auth: false,
    });
    const visibles = r.ok && Array.isArray(r.json?.capacidades_visibles)
      ? new Set(r.json!.capacidades_visibles)
      : null;
    if (!visibles) {
      return CAPABILITIES; // backend no disponible: degradar mostrando el catálogo completo
    }
    return CAPABILITIES.filter(c => visibles.has(c.key));
  } catch {
    return CAPABILITIES;
  }
}

/** Módulos/sub-pestañas cuya visibilidad depende del ROL (y de una posible concesión individual) del
 * usuario autenticado — espejo de `GET /me/modules`. `true` = visible; ausencia de la clave (backend
 * caído/no disponible) se trata como visible por defecto, mismo criterio degradable que
 * `capacidadesVisibles`. Distinto de esa función: esta requiere sesión iniciada (se llama DESPUÉS del
 * login), no antes. */
export async function modulosEfectivos(): Promise<Record<string, boolean>> {
  try {
    const r = await api.get<Record<string, boolean>>('/me/modules');
    return r.ok && r.json ? r.json : {};
  } catch {
    return {};
  }
}

/** `true` si la clave no viene en el mapa (degradable: sin datos, se asume visible) o si viene `true`. */
export function moduloVisible(modulos: Record<string, boolean>, clave: string): boolean {
  return modulos[clave] !== false;
}
