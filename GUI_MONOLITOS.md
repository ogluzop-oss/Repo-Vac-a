# GUI_MONOLITOS.md — GUIs excesivamente grandes

Fecha 2026-07-30. Inventario objetivo de ficheros GUI grandes (umbral de atención: **> 1.500 LOC**;
prioridad alta **> 5.000 LOC**). **NO se divide nada** en esta fase — solo diagnóstico y propuesta futura.
Toda división futura debe seguir el patrón Strangler (ver GUIA_EVOLUCION_ARQUITECTURA.md) + Enterprise Shell
(`gui/components`, regla de CLAUDE.md), conservando `v_id`/rutas/firmas públicas.

## Inventario (por tamaño)

| Archivo | LOC | Clases | Responsabilidad | Subcomponentes detectados | Propuesta futura de división |
|---|---|---|---|---|---|
| `gui/ubicacion_tienda.py` | **12.803** | 5 | Mapa/ubicación de tienda + RFID + búsqueda producto | Pocas clases pero enormes: mapa, celdas, buscador, rastreo RFID | Extraer: `mapa/`, `busqueda/`, `rfid_proximidad/`, `celdas/` como widgets del Enterprise Shell |
| `gui/tpv.py` | **8.958** | 37 | Punto de venta + **config Canal Web** + pedidos online + pagos + báscula | `_CanalWebConfigDialog`, `_GestionPedidosOnlineDialog`, cobro, báscula, devoluciones, pasarela | **Extraer Canal Web** (`_CanalWebConfigDialog`/`_GestionPedidosOnlineDialog` → `gui/canal_web_gui`, WEB-02 iniciado); separar cobro/báscula/pagos |
| `gui/gestion_usuarios.py` | **7.088** | 25 | Usuarios + roles + permisos + empresa + MFA | 25 diálogos/paneles mezclados | Dividir: `usuarios/`, `roles_permisos/`, `empresa/`, `mfa/` |
| `gui/recepcion_pale.py` | **7.079** | 28 | Recepción de palés + RFID + lotes + ubicación | 28 clases (sidebar 7 pestañas) | Dividir por pestaña (recepción/lotes/ubicación/…) |
| `gui/ventas.py` | **3.351** | 10 | Ventas/facturación cliente | 10 clases (calendario, popups, tablas) | Extraer calendario/tablas a componentes |
| `gui/menu_principal.py` | **1.990** | 3 | Menú + enrutado (`abrir_ventana_por_id`) | Factory de tarjetas + routing | Extraer el **routing** a un registro declarativo (útil para Strangler) |
| `gui/mostrar_stock.py` | 1.345 | 10 | Stock tienda + IA predictiva | páginas stock/reposición | Extraer páginas |
| `gui/informe_reposicion.py` | 1.240 | 6 | Reposición IA | páginas estado/editar/export | Extraer páginas |
| `gui/info_articulo.py` | 1.214 | 8 | Ficha de artículo | pestañas | Extraer pestañas |
| `gui/rrhh_gestion.py` | 1.041 | 5 | RRHH | documentos/expediente | Extraer |
| `gui/gestion_mermas.py` | 1.032 | 6 | Mermas | — | Menor prioridad |

## Observaciones

- **`ubicacion_tienda.py` (12.8k)** es el mayor monolito: pocas clases pero gigantes → alta complejidad
  interna. Máxima prioridad de división por widgets.
- **`tpv.py` (8.9k, 37 clases)** concentra responsabilidades ajenas (**Canal Web** + pedidos online). La
  extracción de Canal Web es deuda ya identificada (WEB-01/02) y **acopla** Canal Web a helpers privados de TPV
  (`_btn`, `_lbl`, `_QScrollArea`, `_RoundTableCorners`, `_ss_tabla_neon`).
- **Lección de riesgo (CLAUDE.md)**: no conectar como slot directo métodos con caracteres no-ASCII (ñ) →
  segfault SIP; y los modales desde módulos con audio SOMA pueden corromper el heap → usar feedback inline.
  Cualquier división debe respetar estas lecciones.

## Regla para la futura división (no ejecutar ahora)

1. Crear la nueva pantalla/ventana con `QtEnterpriseWindow`/`QtEnterprisePanel` + `gui/components`.
2. Registrar la sustitución en el mecanismo Strangler (menú/routing) → conmutable sin romper `v_id`.
3. Marcar la antigua `@deprecated`, mantener un ciclo, eliminar cuando no queden referencias.
4. Validar con tests offscreen en cada paso (0 regresiones).
