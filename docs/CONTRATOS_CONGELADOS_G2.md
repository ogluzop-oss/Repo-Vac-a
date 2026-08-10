# Contratos públicos congelados — Etapa G · Fase G2 (Release 1.0)

Inventario de los contratos públicos **certificados y congelados** para Smart Manager AI Enterprise 1.0.
Compatibilidad garantizada con semántica **SUPERSET**: se permiten adiciones (nuevos endpoints, eventos,
conectores, recursos); **eliminar o renombrar** un contrato certificado es una ruptura y está prohibido.
La guarda automática es [`tests/unit/test_g2_contratos.py`](../tests/unit/test_g2_contratos.py).

## 1. API REST v1 (`/api/v1`)

- **Versionado**: prefijo `/api/v1` (Blueprint Flask). OpenAPI **3.0.0** en `/api/v1/openapi.json`, Swagger en `/api/v1/docs`.
- **Seguridad**: `bearerAuth` (JWT) + `apiKey` (`X-API-Key` + `X-Empresa-Id`). Rate limit + RBAC vía `requiere_auth`.
- **23 rutas congeladas**: auth (login/refresh), communications, conversations, templates, campaigns
  (+process), contacts, audit (events/replay), commerce (+health), recordings (+dates/download),
  system (health/version/status/status·tenant/selftest/diagnostico), docs, openapi.json.

## 2. GraphQL (`src/api/graphql`)

Capa GraphQL preparada (resuelve solo vía servicios, 0 SQL). Contrato de esquema congelado; ejecutor degradable.

## 3. SDK oficial

- **Versión congelada: 1.0.0** (fuente única `api_publica.sdks.VERSION`).
- Distribuibles: **Python** (`smartmanager`, pip) y **JavaScript** (`@smartmanager/sdk`, npm) — misma versión en `pyproject.toml`/`package.json`.
- 6 lenguajes con snippets; fuente de verdad = OpenAPI.

## 4. Plugins / Marketplace

- SDK de plugins (`src/sdk`): manifest + `register(sdk)` + hooks/extension_points.
- Marketplace: catálogo, dependencias, **firmas/checksum de manifests**, licencias, instalación, actualización, rollback.

## 5. Event Bus

- **21 eventos catalogados** (contrato de integración): Audit/Campaign/Communication/Consent/Contract/
  Employee/Invoice/Notification/Plugin/PurchaseOrder/Stock/Transfer/Workflow. `publish`/`subscribe`/`replay`.

## 6. Webhooks salientes

- Firma **HMAC-SHA256** determinista (cabecera `X-SM-Signature`), reintentos e historial.

## 7. Conectores Enterprise (Adapter Pattern)

- **7 conectores congelados**: WooCommerce, PrestaShop, Magento, SAP, Salesforce, Business Central, Dynamics 365.
- Provider-agnostic; credenciales cifradas (Secret Manager); auto-registro.

## Política de evolución post-1.0

- **Permitido** (aditivo): nuevos endpoints, eventos, conectores, recursos SDK, versiones nuevas (`/api/v2`).
- **Prohibido** (ruptura): eliminar/renombrar rutas, eventos o conectores certificados; cambiar el esquema
  de seguridad; degradar el versionado. Cualquier cambio incompatible exige una **nueva versión mayor**.

**Contratos congelados oficialmente para Release 1.0.**
