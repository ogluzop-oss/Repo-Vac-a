# INFORME TÉCNICO — FASE WEB-16.5 · Consolidación del Centro de Integraciones Comerciales

**Fecha:** 2026-07-31 · **Tipo:** solo interfaz/UX + agregación (NO modifica motor WEB-13 ni los adaptadores
Hostinger/WooCommerce/Shopify). **Regresiones:** 0 · **Suite:** 762 → **768 passed, 1 skipped** (+6).

## Objetivo

Convertir el Centro de Integraciones Comerciales en una herramienta empresarial escalable, capaz de gestionar
decenas de plataformas sin rediseñar la interfaz al añadir conectores. Todo local, reutilizando lo existente.

## Cambios (aditivos; nada del núcleo tocado)

| Fichero | Rol |
|---|---|
| `integraciones_comerciales/centro.py` (**nuevo**) | Capa de AGREGACIÓN **read-only**: `plataformas_soportadas()` (UNIÓN catálogo + adaptadores del motor → escalable), `resumen()` (estado/salud/versión/última sync), `estadisticas()` (reutiliza pedidos reales por plataforma + actividad de auditoría), `historial()` (lee `auditoria_logs`), `salud()`/`SALUD_EMOJI` (⚪🟡🟢🔴). |
| `integraciones_comerciales/cola_jobs.py` (**nuevo**) | Cola de trabajos sobre la **cola local del motor** (`motor.cola('local')`): ciclo `pendiente→sincronizando→completado/fallido`, `resumen()`, `encolar()`, `ejecutar_pendientes(runner)`. Backend intercambiable (local→SQS en el futuro) sin tocar el negocio. |
| `gui/integraciones_comerciales_gui.py` (**mejorado**) | Panel profesional: tabla de TODAS las plataformas (icono·proveedor·estado·**salud**·versión·última sync·habilitada), barra de **cola de trabajos**, detalle con **estadísticas + historial**, botón **Reintentar**, sincronización vía cola. Asistente y enrutado a adaptadores intactos. |

## Requisitos cubiertos

1. **Flujo sencillo**: el asistente existente (Añadir → plataforma → credenciales → Validar → Sincronizar →
   Finalizado) se conserva sin pasos ocultos.
2. **Panel único de todas las plataformas**: 11 filas (catálogo 10 + Hostinger), cada una con icono/estado/
   proveedor/versión/última sincronización. Construido desde `centro.plataformas_soportadas()`.
3. **Indicador de salud**: columna "Salud" con ⚪ No configurada · 🟡 Advertencia · 🟢 Correcto · 🔴 Error,
   derivado del **estado existente** del motor.
4. **Estadísticas**: por plataforma — productos/clientes/pedidos/reservas/stock (reutilizando pedidos reales
   por `plataforma` y la actividad de importación de la auditoría) + versión API + última ejecución. **No
   recalcula**: solo lee lo que ya existe.
5. **Historial**: validaciones/sincronizaciones/errores/cambios desde el **sistema de auditoría existente**
   (`auditoria_logs`, filtrado por plataforma). No hay sistema paralelo.
6. **Reintentos**: botón único **Reintentar** (reencola la sincronización sin reconfigurar la integración).
7. **Cola de trabajos**: barra con ⏳ Pendientes · 🔄 Sincronizando · ✅ Completados · ❌ Fallidos, usando la
   **cola local** del motor. Al llegar AWS, basta cambiar el backend (`cola('sqs')`).
8. **Preparado para futuras plataformas**: la lista es la unión catálogo + `motor.ADAPTADORES`, así que
   cualquier conector nuevo registrado **aparece automáticamente** sin tocar la UI (verificado por test).
9-10. **Arquitectura/restricciones**: no se tocó motor/Hostinger/WooCommerce/Shopify; sin OAuth/webhooks/
   polling/sincronizaciones programadas/Redis/SQS/AWS. Todo funciona en local.

## Escalabilidad (clave)

`centro.plataformas_soportadas()` = `catálogo ∪ motor.ADAPTADORES`. Registrar un adaptador nuevo (WEB-17…24)
lo hace aparecer en el panel con su icono/estado/salud/estadísticas/historial **sin modificar la interfaz**.
Verificado: al añadir una clave a `ADAPTADORES`, aparece en el panel.

## Pruebas (`test_web165_centro_integraciones.py`, 6)

Panel escalable (unión, incluye Hostinger) · un adaptador nuevo aparece solo · salud ⚪🟡🟢🔴 · estadísticas +
historial reutilizando datos existentes · cola de trabajos (ciclo de estados) · GUI profesional + reintento
(preserva selección tras refrescar). **Suite:** 768 passed, 1 skipped (0 regresiones sobre 762). WEB-12
actualizado (el panel muestra ≥ catálogo).

## No modificado (§9)

Motor WEB-13 · Hostinger · WooCommerce · Shopify · Marketplace de Plugins · Canal Web · Portal Web · TPV ·
Catálogo · Caja · RRHH · AWS · Terraform · Docker · Entitlements: intactos. Solo se añadió la capa de
agregación/cola (aditiva) y se mejoró la GUI del Centro.

## Siguiente

WEB-17 (PrestaShop) … WEB-24 (TikTok Shop): cada conector se implementa replicando el patrón WooCommerce/
Shopify y **aparecerá automáticamente** en este Centro sin más cambios de interfaz.
