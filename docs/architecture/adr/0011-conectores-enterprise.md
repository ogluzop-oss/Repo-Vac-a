# ADR-0011: Conectores Enterprise oficiales (E2)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18 (Etapa E · Fase E2)

## Contexto

Existía el framework de conectores (Adapter Pattern + conexiones cifradas) pero no conectores oficiales
concretos hacia ERP/CRM/eCommerce de terceros.

## Decisión

Se añaden 7 conectores oficiales (WooCommerce, PrestaShop, Magento, SAP, Salesforce, Business Central,
Dynamics 365) como **subclases de `RestChannelAdapter`** (ADR-0008), en
`src/services/integraciones/enterprise/`. Cada uno:

- es **provider-agnostic** y **degradable**; solo cambia mapeo/rutas (traducción pura);
- resuelve credenciales en runtime vía `comercio_digital.conexiones` (Secret Manager) — **nunca en
  código**; multiempresa;
- se **auto-registra** en el registry Enterprise y publica su Service Contract en `platform.registry`;
- se expone también en el catálogo central `integraciones` (categoría `enterprise`).

No crea un framework paralelo (N7) ni toca el dominio.

## Consecuencias

- (+) Integraciones oficiales sin acoplar el dominio; extensible por terceros.
- (−) El mapeo cubre un subconjunto por proveedor (ampliable de forma aditiva).
