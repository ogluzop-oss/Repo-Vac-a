# ADR-0004: Multitenancy estricta (tenant desde el token)

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

La plataforma es multiempresa (SaaS) y multitienda/almacén. Un fallo de aislamiento entre tenants sería
crítico (fuga de datos entre empresas).

## Decisión

- El identificador de tenant (`id_empresa`) **sale SIEMPRE del token/clave** autenticado, **nunca del
  cuerpo** de la petición.
- Todo acceso a datos filtra por `id_empresa` (y `id_tienda`/`id_almacen` donde aplica). Existe un
  `tenant_guard` y un `TenantContext` por petición.
- Los conectores, conexiones y secretos son estrictamente por tenant.

## Consecuencias

- (+) Aislamiento fuerte por diseño; auditable.
- (+) Un mismo despliegue sirve a muchas empresas.
- (−) Cada consulta/servicio debe propagar el tenant; se verifica con pruebas de aislamiento.

## Alternativas consideradas

- Base de datos por tenant: mayor aislamiento físico pero coste operativo alto; se reserva para casos
  específicos (backup/restore por tenant ya soportado).
