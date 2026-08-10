# ARQUITECTURA SaaS DE PRODUCCIÓN — Smart Manager AI

Arquitectura objetivo para operar Smart Manager AI como SaaS multi-tenant. Marca qué existe en el software
(🟢/🔵) y qué requiere provisionado externo (🟣). No se implementa nada ficticio.

## Topología

```
                Internet
                   │
                 DNS 🟣[EXTERNO]        (app./api./admin.smartmanager.ai)
                   │
             CDN / WAF 🟣[EXTERNO]      (recursos públicos; documentos privados NO por CDN)
                   │
           Load Balancer 🟣[EXTERNO]    (TLS termination; health /health/ready → 200/503)
                   │
        ┌──────────┴──────────┐
        │  Smart Manager API  │ 🟢 (Flask, stateless, escalable horizontal; src/api)
        │  + workers/jobs     │ 🟢 (idempotentes; scheduler)
        └──────────┬──────────┘
                   │
            Servicios internos 🟢 (services/*, N7: un motor por responsabilidad)
                   │
        ┌──────────┼───────────────┬───────────────┐
        │          │               │               │
     MariaDB 🟢   Object Storage   Backups 🟡      Observabilidad 🟢
     (pool)       🟣[EXTERNO]      (dr/backup_*)   (health/metricas/alertas/tracing)
     replicación  URLs firmadas    RPO≤24h /       logs estructurados (sin secretos)
     🟣[EXTERNO]  por tenant       RTO por medir
```

## Modelo de aislamiento (tenant)

`EMPRESA(id_empresa) → TIENDA(id_tienda) → ALMACÉN(id_almacen)`, usuarios con RBAC+MFA. Datos aislados por
`id_empresa` (directa / vía padre FK / vía usuario) o declarados globales de plataforma. **Un tenant nunca
accede a datos de otro** (verificado automáticamente). Región por tenant preparada en `saas_regiones`
(resolución Region→Cluster→Node→Tenant), activación 🟣[EXTERNO].

## Componentes: estado

| Capa | Estado | Nota |
|---|---|---|
| API stateless + workers | 🟢 | escalables horizontalmente |
| MariaDB (single) | 🟢 | replicación/2ª región 🟣[EXTERNO] |
| Object storage / CDN | 🟣 | documentos privados; público por CDN |
| Backups + restore | 🟡 | validado localmente; RPO/RTO prod 🟣[EXTERNO] |
| Observabilidad | 🟢 | backend de métricas externo opcional |
| Multi-región / failover | 🟣 | `platform/cloud` preparado (en memoria) |
| DNS / TLS | 🟣 | adaptadores listos; proveedor [EXTERNO] |
| SaaS licensing | 🟢 | enforcement cableado |
| API pública OAuth2 | 🟢 | scopes + OpenAPI verificados |

Ver `RUNBOOK_PRODUCCION.md` (procedimientos) y `CERTIFICACION_FASE_2_SAAS_DEPLOYMENT.md` (matriz).
