# ENTERPRISE_AGENTS

## Paquete Enterprise 6 — Agentes Especializados IA
### Smart Manager AI

> El Copiloto sigue siendo el **punto único de entrada**, pero internamente **delega** cada
> consulta al agente especialista más adecuado. No son IAs independientes: son especialistas que
> **solo aportan conocimiento**, reutilizando la infraestructura Enterprise. Estado:
> **implementado y verificado** (smoke 5/5, 0 escrituras, aditivo, sin tablas nuevas).

---

## 1. Arquitectura
Módulo nuevo `src/services/agentes/` con **`AgentManager`** (SUBFASE 6.1) que registra, localiza,
delega y coordina agentes. `base.Agente` define el contrato; `especialistas.py` contiene los 9
agentes. **CopilotService** (Enterprise 5) sigue siendo la fachada y ahora **delega en el
AgentManager**; si ningún especialista atiende el dominio, cae a IAService (retrocompatible).

```
Usuario → CopilotService (único punto)
            → AgentManager.delegar(dominio) → Agente especialista
                 → reutiliza IAService / PredictionService / AutomationService / BI / Actividad
            → (o) AgentManager.coordinar(...) → varios agentes → respuesta integrada
          → respuesta EXPLICABLE (agente + fuentes + datos + predicciones)
```

## 2. Agentes disponibles (SUBFASE 6.2–6.10)
| Agente | Dominios | Reutiliza |
|---|---|---|
| **Comercial** | ventas, CRM, clientes, margen, inactivos | CRM · BI · PredictionService · IAService |
| **Compras** | proveedores, pedidos, roturas, reposiciones | Compras · PredictionService · AutomationService |
| **Inventario** | stock, kárdex, rotación, mermas, sobrestock, roturas | Inventario · Kárdex · PredictionService |
| **Financiero** | tesorería, liquidez, impagos, facturación, previsiones | Tesorería · Facturación · PredictionService |
| **RRHH** | empleados, contratos, vacaciones, nóminas | RRHH · PredictionService (respeta permisos) |
| **Fiscal** | IVA, IRPF, Verifactu, AEAT, recargo, intracomunitarias | Contabilidad/IVA · AEAT (**solo informa**) |
| **Logístico** | almacenes, recepciones, expediciones, transporte | Logística · Kárdex · Sincronización |
| **TPV** | ventas del día, cajas, cierres, devoluciones | TPV · Ventas · IAService |
| **Auditoría** | logs, hashes, integridad, Workflow, actividad, riesgos | Auditoría · Workflow · Automatización · Sync |

## 3. Flujo de delegación (SUBFASE 6.11/6.12)
- **Delegación automática**: "¿cómo van las ventas?" → Comercial; "¿habrá roturas?" → Inventario.
- **Colaboración entre agentes**: Compras consulta a Inventario (`manager.consultar('stock', …)`) —
  respuestas coherentes, nunca contradictorias.
- **Coordinación multi-agente**: "¿qué debería hacer hoy?" → `AgentManager.coordinar` agrega
  Inventario+Comercial+Financiero+Compras en una respuesta integrada con sus fuentes.

## 4. Pruebas realizadas
- 9 agentes registrados; delegación a Comercial/Inventario/Financiero/Fiscal/Auditoría. ✔
- Colaboración (Compras↔Inventario). ✔
- Coordinación multi-agente. ✔
- Copiloto→agente Inventario con **fuentes fusionadas** `[IAService, Inventario, Kárdex, PredictionService]`. ✔
- **Seguridad**: cajero (OPERARIO) → **denegado** en fiscal/tesorería/auditoría/RRHH. ✔
- **Panel** con estadísticas por agente (nº consultas, tiempo medio). ✔
- **0 escrituras** en `agentes/`; smoke 5/5 verde.

## 5. Reutilización (SUBFASE 6.17 — sin duplicar nada)
Ningún agente accede a la BD ni duplica lógica: todos pasan por **CopilotService (entrada única)**
e **IAService / PredictionService / AutomationService / Workflow / Centro de Actividad / Event Bus
/ BI**. Los agentes son *stateless* (coordinan servicios existentes).

## 6. Seguridad (SUBFASE 6.13)
Cada consulta respeta empresa/tienda/usuario/rol/permisos: el gate de `copilot.seguridad` veta a
roles no directivos los dominios sensibles (tesorería, RRHH, nóminas, contabilidad, facturación,
**fiscal, financiero, auditoría**) **antes** de delegar en el agente.

## 7. Explicabilidad (SUBFASE 6.14)
Toda respuesta indica el **agente responsable**, las **fuentes/servicios** usados, las
**predicciones** intervinientes y las automatizaciones relacionadas. Nunca inventa: todo deriva de
datos reales o predicciones fundamentadas.

## 8. Rendimiento (SUBFASE 6.18)
Los agentes no bloquean TPV/Facturación/Workflow/Sincronización: se invocan dentro del flujo del
Copiloto (que dispone de `preguntar_async` en hilo daemon) y reutilizan servicios ya optimizados
(cache de IA, consultas indexadas).

## 9. Compatibilidad
**Smoke 5/5 verde.** Aditivo, **sin tablas nuevas** (estadísticas en proceso). No modifica ningún
servicio Enterprise ni el ERP. Multiempresa/multitienda, idempotente, reversible, retrocompatible.

## 10. Escalabilidad y futuras ampliaciones (SUBFASE 6.16)
Añadir un agente = crear una clase `Agente` y `manager().registrar(...)` — **sin tocar** el
AgentManager ni el Copiloto. Futuros: **Jurídico, Marketing, Calidad, Producción, Seguridad, IA
Externa (LLM)**. La misma fachada admite enrutado por LLM y colaboración multi-turno sin rediseño.

---

**Agentes Especializados IA implementados y verificados.** Smart Manager AI es ahora una
**organización empresarial inteligente**: el Copiloto actúa de director de orquesta y coordina una
red de agentes especialistas que colaboran para ofrecer respuestas precisas, contextualizadas y
explicables, reutilizando toda la infraestructura Enterprise sin duplicar lógica.
