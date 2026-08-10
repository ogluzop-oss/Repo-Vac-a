# INFORME — Marketplace · Integraciones Comerciales (Fase WEB-03)

Fecha 2026-07-29. Se amplía Marketplace con el submódulo **Integraciones Comerciales** (conexión con
plataformas ecommerce), separado de las "Extensiones Smart Manager" (plugins, intactas). **Arquitectura
PREPARADA, 0 conexiones reales, 0 APIs, 0 OAuth, 0 despliegue.** N7, compatibilidad total. Regresión:
**694 passed, 1 skipped** (687 → +7).

## Estructura entregada

```
Marketplace
├── Extensiones Smart Manager   (plugins existentes — NO tocados)
└── Integraciones Comerciales   (NUEVO submódulo, services/marketplace/integraciones_comerciales/)
        WooCommerce · Shopify · Prestashop · Magento · OpenCart · Amazon · eBay · Miravia · AliExpress · TikTok Shop
```

## Cambios

| Fichero | Rol |
|---|---|
| `services/marketplace/integraciones_comerciales/estados.py` | Modelo UNIFICADO de estado: NO_CONFIGURADA/CONFIGURADA/VALIDADA/SINCRONIZANDO/SINCRONIZADA/ERROR/DESHABILITADA + transiciones |
| `.../contratos.py` | Contratos reutilizables `ConectorMarketplace/Productos/Pedidos/Clientes/Inventario/Precios` (todos `NotImplementedError`) |
| `.../conector.py` | `ConectorPreparado` genérico (implementa los 6 contratos por plataforma, sin duplicar clases; `disponible()=False`) |
| `.../modelo.py` | `Integracion` (nombre/estado/tipo/url/version/última_sync/frecuencia/observaciones + `credenciales_ref`) — **NUNCA credencial real, solo referencia a Secret Manager** |
| `.../servicio.py` | Registro CRUD multi-tenant (crear/editar/eliminar/habilitar/deshabilitar) + auditoría estructural `INTEGRACION_*`; en memoria (degradable) |
| `.../__init__.py` | Fachada del submódulo; reutiliza el catálogo de plataformas de WEB-02 (N7, sin duplicar) |
| `services/marketplace/__init__.py` | **Ampliación** (única modificación de existente): expone `integraciones_comerciales`; plugins intactos |
| `tests/unit/test_integraciones_comerciales_web03.py` | 7 tests |

## Responsabilidades (cumplidas)

Marketplace/Integraciones Comerciales SOLO: conectar · desconectar · validar credenciales · sincronizar
productos/pedidos/clientes/stock/precios/estados. **NO**: publicar/crear webs, dominios, Hostinger (siguen en
Canal Web). El descriptor lo declara explícitamente (`no_responsabilidades: [publicar_web, crear_web, dominios,
hostinger]`).

## Preparación futura (arquitectura, sin implementar)

Contratos listos para: OAuth · API Keys · Webhooks · Polling · sync incremental/completa · jobs · colas ·
reintentos. Persistencia real reutilizará `db/ecommerce.py` (Escenario A) sin secretos en claro — **no se
implementa ni se conecta** en esta fase.

## Seguridad / auditoría

- **Sin credenciales reales**: el modelo sólo guarda `credenciales_ref` (nombre del secreto); el valor vive en
  Secret Manager. Verificado por test (no hay `api_key`/`secret` en el dict).
- Auditoría SOLO de eventos estructurales (`INTEGRACION_CREADA/EDITADA/ELIMINADA/HABILITADA/DESHABILITADA`);
  **no** se auditan sincronizaciones (no existen aún).
- Multi-tenant estricto (aislado por `id_empresa`; test A≠B).

## Compatibilidad y alcance

- Marketplace de plugins funciona **exactamente igual** (fachada + servicio + firmas/licencias/repositorios
  intactos; test de compatibilidad verde).
- **NO tocados**: Canal Web, TPV, Catálogo, Portal, sistema de Plugins, licencias SaaS, Entitlements, RBAC,
  AWS, Terraform, Docker.
- El módulo WEB-02 `comercio_digital.integraciones_comerciales` (catálogo compartido) se **reutiliza**, no se
  duplica ni se mueve (Canal Web sigue redirigiendo a "Marketplace › Integraciones Comerciales").
- **0 conexiones reales** con ninguna plataforma; **0 coste**.

## Pendiente (fases futuras, NO abordado aquí)

- GUI: alojar "Integraciones Comerciales" y "Extensiones Smart Manager" como dos apartados en `marketplace_gui`.
- Implementar OAuth/API/webhooks/sync por plataforma (conectores reales) + persistencia.
- **Extracción física del Canal Web fuera del TPV**: explícitamente **NO** se resuelve en esta fase (se hará
  cuando exista el Portal Back Office y el ecosistema pueda reorganizarse sin riesgo).

**FASE WEB-03 COMPLETADA. 0 regresiones, 0 integraciones reales, plugins intactos.**
