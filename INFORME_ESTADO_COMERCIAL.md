# INFORME DE ESTADO COMERCIAL — Smart Manager AI

Fecha 2026-07-27. Evaluación honesta de la preparación del producto para actividad comercial. No se afirma
"100% terminado": existen dependencias de infraestructura externa (documentadas).

## ¿Para qué está técnicamente preparado HOY?

| Actividad comercial | Preparación | Justificación |
|---|---|---|
| Demostraciones comerciales | 🟢 SÍ | App de escritorio funcional (PyQt6) con módulos operativos: TPV, ventas, stock, compras, logística, RRHH, contabilidad, fiscalidad/AEAT, comercio digital, CRM, MRP, calidad, GMAO, SAT, IA predictiva visible + SOMA. Modo degradable donde falta hardware/infra. |
| Presentación a empresas | 🟢 SÍ | Cobertura funcional amplia y coherente; IA explicable y honesta; multi-tenant/RBAC/MFA/auditoría reales. |
| Pilotos (on-premise / entorno controlado) | 🟢/🟡 SÍ con matices | Funciona sobre MariaDB local; despliegue Docker preparado. Un piloto SaaS multi-cliente requiere provisionar infra (ver abajo). |
| Primeras ventas (licencia/on-prem) | 🟡 SÍ con provisión | El software es production-**ready**; la puesta en producción SaaS necesita infra externa. |
| Operación SaaS multi-región a escala | 🟣 NO todavía | Requiere cloud/DNS/TLS/CDN/2ª región/CD — no provisionado. |

## Fortalezas verificadas

- **Amplitud funcional** de ERP + retail + IA, con arquitectura coherente (N7, sin motores paralelos).
- **IA predictiva honesta**: distingue heurística/estadística/ML (Prophet real), explica y admite falta de
  datos; integrada en pantallas y en SOMA.
- **Multi-tenant real**: 404 tablas aisladas por tenant, 0 fugas nuevas; RBAC/MFA/WebAuthn/auditoría.
- **Tiempo real** (SSE autenticado, aislado por tenant) verificado E2E.
- **Preparación de despliegue**: Docker + compose de producción + CI + plantillas de entorno sin secretos +
  backup/restore + runbooks.

## Límites que deben comunicarse con honestidad

- **No desplegado en producción**: no existe infra cloud provisionada. Es *production-ready*, no *deployed*.
- **Aceptación fiscal AEAT en real**: el motor es real (mTLS + endpoints oficiales), pero la aceptación legal
  requiere certificado de producción + alta AEAT del cliente (condición externa).
- **Capacidades marcadas 🔵/🟡/🟣** (refresco SSE en vivo en UI, modelos globales, ML avanzado, multi-región):
  preparadas o bloqueadas por infra/decisión; no deben presentarse como operativas.

## Recomendación

Smart Manager AI está **técnicamente preparado para iniciar demostraciones, presentaciones y pilotos**, y para
**primeras ventas on-premise/licencia**. La comercialización SaaS a escala queda condicionada a provisionar la
infraestructura externa (una decisión del propietario, no una brecha de código).
