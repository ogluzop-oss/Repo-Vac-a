# Diagramas de arquitectura

Vistas de la arquitectura del ERP Enterprise en **Mermaid** (se renderizan en GitHub). Documentan la
estructura existente; ver el porqué en los [ADR](adr/).

## 1. Contexto (C4 nivel 1)

```mermaid
graph TB
    U[Usuario ERP<br/>PyQt6 escritorio]
    T[Tercero / Integrador<br/>SDK Python·JS]
    OPS[DevOps / SRE]
    SM[(Smart Manager AI<br/>ERP Enterprise)]
    EXT[Sistemas externos<br/>ERP·CRM·eCommerce·Correo·Firma·Pagos]
    PROM[Prometheus]

    U -->|UI| SM
    T -->|REST /api/v1 · GraphQL| SM
    OPS -->|Kubernetes·Helm| SM
    SM -->|Adapter Pattern| EXT
    SM -->|/api/v1/metrics| PROM
```

## 2. Contenedores (C4 nivel 2)

```mermaid
graph TB
    subgraph Cliente
      GUI[UI PyQt6<br/>src/gui]
      SDKP[SDK Python<br/>sdk/python]
      SDKJ[SDK JavaScript<br/>sdk/javascript]
    end
    subgraph Backend
      API[REST API Flask<br/>src/api · /api/v1]
      GQL[GraphQL<br/>src/api/graphql]
      WSGI[gunicorn wsgi:app]
      SVC[Servicios de dominio<br/>src/services]
      PLT[Plataforma<br/>src/platform]
    end
    DB[(MariaDB)]

    GUI --> SVC
    SDKP --> API
    SDKJ --> API
    API --> SVC
    GQL --> SVC
    WSGI --- API
    SVC --> PLT
    SVC --> DB
```

## 3. Componentes (servicios transversales — motores únicos, ADR-0002)

```mermaid
graph LR
    SVC[Servicios de dominio]
    CAP[platform.capabilities]
    SVC --> CAP
    CAP --> EB[Event Bus]
    CAP --> WF[Workflow]
    CAP --> RU[Rules]
    CAP --> SCH[Scheduler]
    CAP --> IA[IA / Inteligencia]
    CAP --> OBS[Observabilidad]
    CAP --> RBAC[RBAC / Seguridad]
    CAP --> SEC[Secret Manager]
    CAP --> MKT[Marketplace]
    CAP --> BI[BI / BI corp]
```

## 4. Dependencias (capas — dependencia estricta)

```mermaid
graph TD
    UI[gui] --> SVC[services]
    APIREST[api] --> SVC
    SVC --> DOM[dominio / db]
    SVC --> PLT[platform.capabilities]
    subgraph UI Enterprise Shell
      FND[foundation] 
      CMP[components] --> FND
      PAN[panels] --> CMP
      WIN[windows] --> PAN
    end
    UI --- WIN
```

## 5. Flujo — venta → fulfillment (kárdex único)

```mermaid
sequenceDiagram
    participant C as Canal / TPV
    participant TX as Transacción comercial
    participant RES as Reservation Ledger
    participant FUL as Fulfillment
    participant K as Kárdex único (salida_stock)
    participant EB as Event Bus
    C->>TX: crear transacción + líneas
    TX->>RES: reservar (ATP)
    TX->>FUL: plan de cumplimiento
    FUL->>K: salida de stock (política única)
    K->>EB: publica evento (KARDEX_MOVIMIENTO)
    EB-->>FUL: confirmación / seguimiento
```

## 6. Integraciones (conectores Enterprise, ADR-0008/0011)

```mermaid
graph TB
    DOM[Dominio] -->|mensaje neutro| AD[RestChannelAdapter<br/>traducción pura]
    CX[conexiones<br/>credenciales cifradas] -->|AdapterContext| AD
    SEC[Secret Manager] --> CX
    AD --> WOO[WooCommerce]
    AD --> PS[PrestaShop]
    AD --> MG[Magento]
    AD --> SAP[SAP]
    AD --> SF[Salesforce]
    AD --> BC[Business Central]
    AD --> D365[Dynamics 365]
```

## 7. Eventos (Event Bus, ADR-0006)

```mermaid
graph LR
    P[Productores<br/>servicios/dominio] -->|publish| BUS[(Event Bus)]
    BUS --> STORE[(event_store)]
    BUS --> SUBS[Suscriptores<br/>Rules·Automatización·Sync]
    BUS --> WH[Webhooks salientes<br/>HMAC-SHA256]
    STORE --> RP[Audit Replay]
```

## 8. Marketplace de extensiones

```mermaid
graph TB
    CAT[catalogo] --> DET[detalle/manifest]
    DEP[dependencias] --> INS[instalacion]
    FIR[firmas / checksum] --> INS
    LIC[licencias] --> INS
    INS --> SDKP[src/sdk<br/>plugin_loader]
    SDKP --> REG[platform.registry]
    ACT[actualizacion] --> INS
```

## 9. SDK oficial (desde OpenAPI, ADR-0012)

```mermaid
graph LR
    OA[OpenAPI /api/v1/openapi.json<br/>fuente única] --> META[api_publica.sdks<br/>VERSION · metadata]
    META --> PY[sdk/python<br/>pip: smartmanager]
    META --> JS[sdk/javascript<br/>npm: @smartmanager/sdk]
    PY --> API[REST API]
    JS --> API
```

## 10. API (superficie REST, ADR-0001/0010)

```mermaid
graph TB
    CLI[Cliente] -->|Bearer JWT / X-API-Key| AUTH[requiere_auth<br/>JWT·API Key·RBAC·Rate Limit·Tenant]
    AUTH --> R[Routers /api/v1<br/>communications·templates·campaigns·contacts·audit·commerce·system]
    R --> PAG[paginacion<br/>limit·offset·cursor·sort·order·filters]
    R --> SVC[Servicios]
    R --> OAPI[OpenAPI + Swagger /docs]
```
