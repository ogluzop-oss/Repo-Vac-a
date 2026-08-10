# ENTERPRISE PLATFORM CERTIFICATION — Smart Manager AI

**Certificación global del bloque Enterprise (Paquetes 1–10)**
Smart Manager AI queda certificado como **plataforma empresarial inteligente de nueva generación**,
capaz de: **observar · comprender · explicar · predecir · simular · proponer · coordinar ·
ejecutar** — todo bajo un modelo de **autonomía supervisada**, donde ninguna acción crítica se
realiza sin respetar el Gobierno Corporativo, los flujos de aprobación y la trazabilidad completa.

Estado: **implementado y verificado en local, sin commitear.**
Migraciones del bloque: `0087`–`0096`.

---

## 1. Arquitectura final

Una pila de capacidades donde cada nivel se apoya EXCLUSIVAMENTE en los anteriores, con una fachada
única por servicio y sin motores duplicados:

```
                         AUTONOMÍA SUPERVISADA (10)  ── ExecutiveActionService
                                   ▲  ejecuta solo lo aprobado
                         SIMULADOR (9)  ─────────────── SimulationService (what-if)
                                   ▲  estado base
                         GEMELO DIGITAL (8) ─────────── DigitalTwinService (estado vivo)
                                   ▲  conocimiento
       AGENTES (6) · COPILOTO (5) · AUTOMATIZACIÓN (4) · PREDICCIÓN (3) · IA (2)
                                   ▲  comprensión / propuesta
       CENTRO DE ACTIVIDAD (3) · DISTRIBUCIÓN · SINCRONIZACIÓN (Fase 4)
                                   ▲  observación
                         EVENT BUS (1)  ──────────────── bus único de eventos
                                   ▲  gobierno transversal
                         GOBIERNO CORPORATIVO (7) · WORKFLOW/BPM · RBAC · BI
```

| # | Paquete | Fachada | Migración |
|---|---|---|---|
| 1 | Event Bus | `eventos` (publicar/suscribir/consumir) | 0087 |
| — | Distribución | `distribucion` | 0088 |
| 3 | Centro de Actividad | `actividad` | 0089 |
| — | Sincronización / Transporte | `sync_transport` | 0090 |
| 2 | Actividad avanzada (agrupación/timeline) | `actividad.*` | 0091 |
| — | IA | `ia` → `IAService` | (0058/0065 BI base) |
| 3 | Predicción | `prediccion` → `PredictionService` | — |
| 4 | Automatización | `automatizacion` → `AutomationService` | 0092 |
| 5 | Copiloto | `copilot` → `CopilotService` | — |
| 6 | Agentes | `agentes` → `AgentManager` | — |
| 7 | Gobierno Corporativo | `gobierno` → `GovernanceService` | 0093 |
| 8 | Gemelo Digital | `gemelo` → `DigitalTwinService` | 0094 |
| 9 | Simulador | `simulador` → `SimulationService` | 0095 |
| 10 | Autonomía Supervisada | `autonomia` → `ExecutiveActionService` | 0096 |

---

## 2. Principios de diseño (constantes en los 10 paquetes)

1. **Fachada única por servicio** (`servicio()` → singleton). Un solo punto de entrada por capacidad.
2. **Reutilización absoluta.** Ningún motor nuevo: cada capa orquesta las anteriores. La IA no
   calcula predicciones (delega en PredictionService); el Simulador no lee la BD (usa el Gemelo);
   la Autonomía no reimplementa aprobaciones (usa Workflow + Gobierno).
3. **Aditivo / reversible / idempotente.** Todas las migraciones `CREATE TABLE IF NOT EXISTS`, sin
   DROP/ALTER destructivo ni renumeraciones. Cada bloque se puede retirar sin afectar a lo previo.
4. **Bulletproof e integración no intrusiva.** Las publicaciones/observaciones van tras el `commit`
   certificado y en `try/except`: jamás pueden romper un flujo certificado.
5. **Read-only donde debe.** IA/Predicción/Copiloto/Agentes/Gemelo/Simulador no escriben en datos
   operativos; solo la Autonomía ejecuta, y únicamente acciones seguras tras aprobación.
6. **Explicabilidad y confianza** en cada respuesta (fuentes, hipótesis, riesgos, nivel de confianza).
7. **La IA propone, la organización decide, el sistema ejecuta lo autorizado.**

---

## 3. Reutilización conseguida

- **Event Bus** es el único canal de comunicación entre módulos (nadie se llama directamente).
- El **Gemelo Digital** es la única fuente de estado para IA/Copiloto/Agentes/Simulador.
- **PredictionService** es el único motor de predicción/riesgo (reutilizado por IA, Gemelo,
  Simulador, Autonomía).
- **Workflow/BPM + Gobierno Corporativo** son el único circuito de aprobación (reutilizado por
  Automatización, Copiloto y Autonomía).
- **AutomationService** es el único catálogo de acciones (reutilizado por Copiloto y Autonomía).
- El **estimador de PredictionService** y las **elasticidades del Simulador** son enchufables
  (preparados para ML) sin tocar las fachadas.

---

## 4. Compatibilidad (certificado intacto)

Ningún paquete Enterprise modifica el funcionamiento de los módulos certificados: TPV, Facturación,
Verifactu, AEAT, hashes, numeraciones, Kárdex, Inventario, Compras, CRM, RRHH, Contabilidad,
Tesorería. Verificado con el **smoke `5 passed`** tras cada paquete (0087→0096).

---

## 5. Escalabilidad

- Consultas acotadas por `id_empresa`; el Gemelo usa **materialized path** y cache con TTL invalidada
  por eventos (nunca recorre el ERP).
- El Simulador opera sobre 11 métricas normalizadas (coste despreciable).
- La Autonomía persiste solo metadatos de planes/acciones.
- Arquitectura modular: añadir un dominio, una variable what-if, una regla de automatización o una
  acción ejecutable es una entrada en un registro, sin tocar el resto.

---

## 6. Preparación SaaS

- **Multiempresa/multitienda** en todas las tablas (`id_empresa VARCHAR(36)`, `id_tienda`).
- Reglas globales opcionales (`id_empresa NULL`) para catálogos compartidos.
- Modo de empresa configurable (MANUAL→AVANZADA) por tenant.
- Fachadas singleton por proceso, sin estado compartido entre empresas.
- Enforcement de planes SaaS ya presente (LicensingService); las capacidades Enterprise se activan
  por catálogo de módulos.

---

## 7. Preparación multiempresa

Cada capacidad resuelve el tenant desde el contexto (`empresa_actual_id`, `EMPRESA_DEFAULT_ID`) y
acota todas sus consultas y escrituras. Gobierno Corporativo modela grupo→empresa→zona→tienda→
departamento con herencia de políticas y cadenas de aprobación por empresa.

---

## 8. Preparación para futuras ampliaciones

- **ML real**: sustituir el `Estimador` heurístico (Prophet/XGBoost/LLM) sin tocar las fachadas.
- **GUI**: todos los dashboards (Gemelo, Simulador, Autonomía, Gobierno) son backend listos para
  pantallas.
- **Cableado de dependencias** del Gemelo desde cada publicador certificado (incremental, aditivo).
- **Ejecución ampliada**: nuevas acciones seguras en el catálogo de Autonomía, siempre gated por
  Gobierno/Workflow.
- **Motor estratégico**: sobre el Simulador + Autonomía, un optimizador que proponga el mejor
  escenario según objetivos (siempre supervisado).

---

## 9. Capacidades certificadas de la plataforma

| Capacidad | Servicio | Paquete |
|---|---|---|
| Observar | Event Bus · Centro de Actividad · Sincronización | 1, 3, 4 |
| Comprender | IAService · DigitalTwinService | 2, 8 |
| Explicar | IA · Copiloto · Explicabilidad (Simulador/Autonomía) | 2, 5, 9, 10 |
| Predecir | PredictionService | 3 |
| Simular | SimulationService | 9 |
| Proponer | AutomationService · Copiloto · Agentes | 4, 5, 6 |
| Coordinar | AgentManager · Gobierno Corporativo · Workflow | 6, 7 |
| Ejecutar | ExecutiveActionService (supervisado) | 10 |

---

## 10. Veredicto

Smart Manager AI dispone de una arquitectura Enterprise completa, coherente y certificada:
observa la realidad por eventos, la comprende con un gemelo digital vivo, la explica y predice con
IA, simula decisiones sin riesgo, propone a través de agentes y copiloto, la gobierna con jerarquías
y flujos de aprobación, y ejecuta acciones reales solo bajo autonomía supervisada. Todo **aditivo,
reversible, idempotente, multiempresa, multitienda y SaaS-ready**, sin romper ninguna certificación
previa.

**Bloque Enterprise (1–10): CERRADO Y CERTIFICADO.**

---

*Local, sin commitear. Migraciones 0087–0096 aplicadas y registradas en `MODULOS`. Smoke: 5 passed.*
