# ENTERPRISE_COPILOT

## Paquete Enterprise 5 — Copiloto Empresarial IA
### Asistente Corporativo Inteligente de Smart Manager AI

> El punto **único** de interacción en lenguaje natural con TODO Smart Manager AI. No es un
> chatbot ni una IA paralela: es un **orquestador** que reutiliza por completo la arquitectura
> Enterprise. Estado: **implementado y verificado** (smoke 5/5, orquestación read-only, aditivo,
> sin tablas nuevas).

---

## 1. Arquitectura
Módulo nuevo `src/services/copilot/` con **`CopilotService` como fachada única** (SUBFASE 5.1).
**No calcula: coordina.** No crea IA, predicción, automatización ni Workflow nuevos: **delega**.

| Fichero | Rol |
|---|---|
| `motor.py` | `CopilotService`: orquesta preguntar/panel/async |
| `intencion.py` | comprensión NL: intención/dominio/periodo/acción/seguimiento (5.2) |
| `contexto.py` | contexto empresa/tienda/usuario/rol/idioma/periodo (5.3) |
| `memoria.py` | memoria conversacional por usuario (5.4) |
| `respuestas.py` | respuestas enriquecidas + explicabilidad + recomendaciones (5.5/5.7/5.8) |
| `acciones.py` | acciones desde la conversación → AutomationService/Workflow (5.6) |
| `seguridad.py` | acceso por rol (5.12) |

## 2. Reutilización absoluta (SUBFASE 5.10 — sin duplicar nada)
| Capacidad | Se reutiliza |
|---|---|
| Análisis / consultas | **IAService** (`ia.servicio().preguntar`, que ya delega en Predicción) |
| Predicciones / riesgos | **PredictionService** |
| Acciones / propuestas | **AutomationService** + **Workflow/BPM** |
| Timeline / actividad / sync | **Centro de Actividad** |
| Datos | adaptadores read-only existentes |
**Verificado**: 0 escrituras directas en `copilot/` — solo orquesta.

## 3. Flujo conversacional
```
Usuario (lenguaje natural)
  → CopilotService.preguntar
    → contexto (empresa/tienda/rol)         [5.3]
    → seguridad (¿rol autorizado?)          [5.12]
    → intención (dominio/periodo/acción/seguimiento) [5.2/5.4]
    → si ACCIÓN → AutomationService/Workflow (propuesta/aprobación) [5.6]
      si DATOS  → IAService (+ PredictionService)
    → respuesta ENRIQUECIDA (texto + fuentes + recomendaciones + alertas) [5.5/5.7/5.8]
    → memoria (recuerda dominio/periodo)     [5.4]
```

## 4. Pruebas realizadas
- **5.2 NL**: "¿cómo van las ventas?" → intent `ventas`, dato real (2.327). ✔
- **5.4 Memoria**: "¿y respecto a la semana pasada?" mantiene el dominio `ventas`. ✔
- **5.6 Acción**: "crea una tarea…" → `accion.crear_tarea` (PROPUESTA) vía AutomationService/Workflow. ✔
- **5.7 Explicabilidad**: fuentes reales `[IAService, PredictionService, Ventas]`. ✔
- **5.8 Recomendaciones contextuales**: presentes solo con evidencia. ✔
- **5.11 Panel**: historial/consultas/acciones/predicciones/riesgos/estado/atajos (8). ✔
- **5.12 Seguridad**: cajero (OPERARIO) → **denegado** en tesorería; permitido en reposición. ✔
- **5.13 Async**: `preguntar_async` responde por callback en hilo daemon. ✔
- **Compatibilidad**: smoke 5/5 verde.

## 5. Integración (SUBFASE 5.10/5.11)
El Copiloto se integra en el **Centro de Actividad**: el campo "Preguntar" ahora orquesta vía
`CopilotService` y muestra la respuesta con **Fuentes** y **"También podrías…"** (recomendaciones
contextuales). `CopilotService.panel` provee el panel del Copiloto (historial, acciones
propuestas, predicciones, riesgos, estado del sistema, atajos) **complementando** el Centro, sin
sustituirlo.

## 6. Seguridad (SUBFASE 5.12)
Acceso por rol: los roles no directivos (OPERARIO) no acceden a dominios sensibles (tesorería,
RRHH, nóminas, beneficios, contabilidad, facturación). Los directivos (ADMINISTRADOR/GERENTE/
SUPERADMIN) acceden a todo. Reutiliza los perfiles del ERP (no crea un RBAC nuevo).

## 7. Rendimiento (SUBFASE 5.13)
`preguntar_async` ejecuta en hilo daemon con callback; el Copiloto **nunca bloquea**
TPV/Facturación/Sincronización/Workflow. Reutiliza servicios ya optimizados (cache de IA,
consultas indexadas).

## 8. Compatibilidad
**Smoke 5/5 verde.** Aditivo; **sin tablas nuevas** (contexto/memoria en proceso). No modifica
IAService, PredictionService, AutomationService, Workflow, Event Bus, Centro de Actividad,
Verifactu, AEAT, TPV, Facturación, CRM, Inventario, Kárdex, RRHH, Tesorería, BI. Multiempresa/
multitienda, idempotente, reversible, retrocompatible. **Nunca inventa**: responde solo con datos
reales del sistema o predicciones fundamentadas.

## 9. Escalabilidad y futuras ampliaciones
- Intención por reglas deterministas → ampliable con un **LLM** detrás de la misma fachada
  (`CopilotService.preguntar`) sin tocar el resto.
- Nuevos dominios/acciones se añaden en `intencion`/`acciones` sin cambiar el orquestador.
- Memoria conversacional lista para persistencia opcional y multi-turno avanzado.
- Panel del Copiloto ampliable (voz — ya existe SOMA, streaming de respuestas, multi-idioma).

---

**Copiloto Empresarial IA implementado y verificado.** Smart Manager AI es ahora un **ERP
conversacional**: cualquier usuario autorizado interactúa con toda la plataforma en lenguaje
natural y obtiene respuestas explicables, predicciones, recomendaciones y acciones orquestadas
sobre la infraestructura Enterprise existente, sin duplicar lógica ni comprometer la estabilidad.
