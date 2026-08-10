# ENTERPRISE AUTONOMY — Autonomía Supervisada · Ejecución Controlada

**Paquete Enterprise 10 — Smart Manager** (cierre del bloque Enterprise)
Smart Manager AI ejecuta acciones reales **de forma supervisada**: la IA propone, la organización
decide, el sistema ejecuta únicamente lo autorizado. Ninguna acción crítica se realiza sin respetar
Gobierno Corporativo, los flujos de aprobación y la trazabilidad completa.

Estado: **implementado, verificado en local, sin commitear.**
Migración: `0096_autonomia` (idempotente, reversible, aditiva).

---

## 1. Arquitectura

`ExecutiveActionService` — **fachada pública única y único servicio autorizado a ejecutar acciones
reales**. Ningún otro módulo ejecuta directamente.

```python
from src.services import autonomia
pid = autonomia.servicio().plan_desde_escenario(id_escenario)   # 10.2
autonomia.servicio().solicitar_aprobacion(pid)                  # Workflow
autonomia.servicio().aprobar_plan(pid, usuario="ADMIN", perfil="ADMINISTRADOR")  # Gobierno
autonomia.servicio().ejecutar(pid, usuario="ADMIN", perfil="ADMINISTRADOR", solo_fase=1)  # 10.5
```

Módulos (`src/services/autonomia/`):

| Módulo | Subfase | Responsabilidad |
|---|---|---|
| `motor.py` (`ExecutiveActionService`) | 10.1 | Fachada única autorizada. Aprobación, ejecución, reversión, dashboard. |
| `planes.py`         | 10.2/10.3 | Convierte escenario→plan; genera plan (acciones/fases/impacto/riesgos/responsables/tiempo). |
| `validaciones.py`   | 10.4 | Gobierno + Workflow + permisos + disponibilidad + conflictos + dependencias. |
| `ejecucion.py`      | 10.5/10.6/10.15 | Ejecución por fases con validación entre cada una; reversión; auditoría. |
| `catalogo.py`       | 10.14 | Acciones seguras (AutomationService) vs críticas (solo propuesta). |
| `seguridad.py`      | 10.14 | Garantía: acciones críticas nunca automáticas. |
| `modos.py`          | 10.13 | Modo de empresa (MANUAL/ASISTIDA/SEMIAUTO/AVANZADA). |
| `explicabilidad.py` | 10.7 | Qué/por qué/módulos/riesgos/servicios/confianza. |
| `agentes_revision.py` | 10.8 | Cada agente revisa el plan (aprobado/observaciones/riesgos/recomendaciones). |
| `indicador.py`      | 10.12 | Nivel de automatización real (solo acciones ejecutadas). |
| `dashboard.py`      | 10.11 | Panel: planes pendientes/aprobados/ejecutados/cancelados, reversiones, tiempo ahorrado. |

---

## 2. ExecutiveActionService y flujo de gobierno

El ciclo de una acción real: **proponer → decidir → ejecutar**, nunca saltos.

```
Escenario simulado (Enterprise 9)
   → plan_desde_escenario           (BORRADOR)
   → solicitar_aprobacion → Workflow (PENDIENTE_APROBACION)
   → aprobar_plan → Gobierno.puede_aprobar + Workflow.aprobado  (APROBADO)
   → ejecutar (por fases, con validación entre cada una)         (EN_EJECUCION → EJECUTADO)
   → revertir (si procede)                                       (REVERTIDO)
```

Un plan solo se ejecuta si está **APROBADO**. Intentar ejecutar un plan no aprobado se rechaza
(verificado: `estado=BORRADOR → error`).

---

## 3. Workflow y Gobierno (10.4)

Antes de ejecutar, `validaciones.validar` comprueba (bloquean las esenciales): estado APROBADO,
**autoridad de Gobierno Corporativo** (`gobierno.puede_aprobar`), **Workflow aprobado**
(`workflow_engine.aprobado`), disponibilidad; e informan: permisos RBAC, conflictos, dependencias.
Si cualquiera esencial falla → se cancela.

---

## 4. Seguridad (10.14)

Acciones que **nunca** se ejecutan automáticamente (sin autorización válida): generar pedidos,
modificar precios, despedir empleados, emitir facturas, realizar pagos, mover stock. Estas acciones
**no tienen ejecutor real** en el catálogo: se convierten SIEMPRE en propuesta gobernada
(Workflow + Gobierno). Verificado end-to-end: en un plan con acción de precio, la fase crítica se
ejecutó como **0 ejecutadas / 1 propuesta**.

**Aislamiento de escrituras:** el paquete solo escribe en `exec_planes` / `exec_acciones` /
`exec_config`. Las acciones "reales" se materializan a través de AutomationService (avisos, tareas,
propuestas — subsistemas seguros y reversibles), nunca por escritura directa a tablas certificadas.

---

## 5. Ejecución por fases y reversión (10.5 / 10.6)

Nunca se ejecuta todo a la vez: el plan se divide en fases y se **valida entre cada una**. Se puede
ejecutar `solo_fase=N`. Cada acción guarda su **estado previo** (`estado_previo_json`) para poder
revertirse; la reversión emite una compensación trazable y marca la acción `REVERTIDA`. Verificado:
ejecución de 3 fases y reversión de las 2 acciones seguras ejecutadas.

---

## 6. Explicabilidad (10.7) y revisión por agentes (10.8)

Antes de ejecutar, el sistema explica: qué hará, por qué, qué módulos afectará, qué riesgos existen,
qué servicios participan y el nivel de confianza. Cada agente implicado emite un dictamen
(APROBADO / OBSERVACIONES + riesgos + recomendaciones). Verificado: dictámenes de agentes
comercial/compras/auditoría con veredicto OBSERVACIONES ante acciones críticas.

---

## 7. Modo de empresa (10.13)

`MANUAL` (nunca ejecuta, solo propone) · `ASISTIDA` (solo informativas) · `SEMIAUTO` (reversibles no
críticas) · `AVANZADA` (todas las reversibles; críticas siempre gated). Cada modo limita
automáticamente qué puede auto-ejecutar el sistema. Persistente por empresa.

---

## 8. Indicador de autonomía (10.12) y Dashboard (10.11)

El nivel de automatización se calcula **solo con acciones realmente ejecutadas**
(`ejecutadas / (ejecutadas + propuestas)`), nunca con estimaciones. El dashboard agrega planes por
estado, reversiones, tiempo ahorrado y el indicador. Verificado con datos reales de `exec_acciones`.

---

## 9. IA (10.10) y Copiloto (10.9)

- **IA** — `IAService.recomendar_ejecucion(plan)`: "¿Es recomendable ejecutar este plan?",
  "¿Qué riesgos quedan?", "¿Qué tareas revisar antes?" (usando datos reales del plan).
- **Copiloto** — "Muéstrame el plan", "Ejecuta solo la primera fase", "Ejecuta la simulación
  aprobada", "No"/"Cancela", "Revierte". Detectado antes del gate por dominio y **restringido a
  roles globales**; nunca ejecuta sin autorización. Verificado: ADMIN muestra/ejecuta; OPERARIO
  restringido.

---

## 10. Auditoría (10.15)

Todo queda registrado (`log_auditoria` existente): quién, cuándo, qué, por qué, resultado y
reversión, en cada transición (SOLICITA_APROBACION, APROBADO, EN_EJECUCION, ACCION_EJECUTADA/OMITIDA,
CANCELADO, EJECUTADO, ACCION_REVERTIDA, PLAN_REVERTIDO, MODO_AUTONOMIA_CAMBIADO).

---

## 11. Rendimiento (10.16)

Reutiliza por completo Workflow, AutomationService, Gemelo, IA, Predicción y Simulación; no
recalcula información existente. El impacto/riesgo del plan proviene del escenario ya simulado.

---

## 12. Compatibilidad (10.17)

Aditivo y no intrusivo. No modifica: TPV, Facturación, CRM, Compras, Inventario, RRHH, Tesorería,
Workflow, Copilot, Agentes, IA, Gobierno, Gemelo Digital, Simulador, PredictionService, Centro de
Actividad, Event Bus, Verifactu, AEAT, hashes ni numeraciones. Integraciones IA/Copilot en
`try/except`. **Certificado intacto.**

---

## 13. Pruebas

Verificación end-to-end (`DB_NAME=smart_manager_test`):

- 10.13 modo SEMIAUTO establecido. ✔
- 10.2/10.3 plan desde escenario (3 acciones, 3 fases, crítica=['Ajuste de precios'], tiempo 45 min). ✔
- 10.8 dictámenes de agentes (compras/ventas/auditoría → OBSERVACIONES). ✔
- 10.4 validación bloquea ejecución sin aprobar; ejecutar sin aprobar → error. ✔
- Aprobación: Gobierno (ADMINISTRADOR) → APROBADO. ✔
- 10.5 ejecución por fases; **10.14 fase crítica: 0 ejecutadas / 1 propuesta.** ✔
- 10.6 reversión de las 2 acciones seguras. ✔
- 10.12 indicador (solo ejecutadas reales); 10.11 dashboard. ✔
- 10.10 IA recomienda; 10.9 Copiloto (ADMIN ejecuta, OPERARIO restringido). ✔
- Aislamiento: 0 escrituras fuera de `exec_*`. ✔

**Smoke:** `5 passed`.

---

*Local, sin commitear. Migración 0096 aplicada y registrada en `MODULOS`. Smoke: 5 passed.*
