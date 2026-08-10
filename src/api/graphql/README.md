# GraphQL Enterprise Layer (Fase IV · Bloque 1)

Capa GraphQL profesional que **reutiliza** la REST API y los servicios existentes. **No es una
segunda API**: es una capa de **consulta** sobre los servicios. (Evoluciona la preparación de Fase III · B8.)

## Regla inquebrantable

```
GraphQL → Servicios → Dominio → BD        (NUNCA GraphQL → SQL)
```

Los resolvers (`queries.py`, `mutations.py`) **solo** importan `src.services.*` / `src.sdk` — jamás
`src.db` ni SQL. Verificado por test (`tests/unit/test_graphql.py::test_resolvers_sin_sql_ni_bd`).

## Arquitectura

| Fichero | Rol |
|---|---|
| `registry.py` | Registro de tipos, queries, mutations y subscriptions (cada op declara su **servicio** de destino). |
| `context.py` | Contexto autenticado (JWT/API Key) reutilizando la seguridad REST. Tenant del token. |
| `middlewares.py` | Cadena: auth → rate limit → RBAC → scopes (misma infraestructura que REST). |
| `queries.py` | Resolvers de lectura → servicios (ccp, sdk, marketplace, observabilidad, scheduler, rules, bi, audit). |
| `mutations.py` | Resolvers de escritura → servicios (crear/editar/eliminar/activar/ejecutar). |
| `subscriptions.py` | **Preparadas**: Event Bus → Subscriptions → clientes GraphQL (sin tiempo real todavía). |
| `schema.py` | Ensambla el esquema, genera **SDL** y ejecuta operaciones (ejecutor propio ligero, degradable). |
| `descriptor.py` | Descriptor previo (Fase III · B8) reutilizado. |

## Uso

```python
from src.api.graphql import schema

schema.ejecutar("communications", {"limite": 20},
                contexto={"id_empresa": emp, "usuario": {"perfil": "ADMINISTRADOR"}})
schema.sdl()        # SDL del esquema
schema.esquema()    # tipos + operaciones + servicio de destino de cada una
```

## Seguridad

JWT · API Keys · Scopes · RBAC · Tenant · Rate Limit — **exactamente** la infraestructura REST
(`src.api.security` + `src.seguridad`). El `id_empresa` sale **siempre** del token/clave.

## Degradable / Federation

- **Sin librería GraphQL instalada** (graphene/strawberry/ariadne): ejecutor propio ligero. El
  `registry` queda listo para **alimentar** una librería real cuando se instale.
- **Federation**: no implementada; el registry y el SDL dejan la arquitectura preparada.
- **Subscriptions en tiempo real**: no implementadas; los canales se declaran sobre el Corporate
  Event Bus (`subscriptions.puente(...)` deja el enganche listo).
