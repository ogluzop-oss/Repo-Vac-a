# ENTERPRISE SIMULATION — Simulador Empresarial · What-If · Planificación Estratégica

**Paquete Enterprise 9 — Smart Manager**
Responde "¿qué ocurriría si...?" **sin modificar jamás los datos reales**, usando el Gemelo Digital
como estado base y PredictionService como motor de propagación de consecuencias. Herramienta de
planificación ejecutiva de nivel Enterprise.

Estado: **implementado, verificado en local, sin commitear.**
Migración: `0095_simulador` (idempotente, reversible, aditiva).

---

## 1. Arquitectura

Fachada pública UNICA (patrón `servicio()`). Toda simulación pasa por aquí:

```python
from src.services import simulador
r = simulador.servicio().simular_directo([{"variable": "precio", "valor": 5}])
eid = simulador.servicio().crear_escenario("Subida 5%")
simulador.servicio().añadir_variable(eid, "precio", 5)
simulador.servicio().simular(eid)
```

Módulos (`src/services/simulador/`):

| Módulo | Subfase | Responsabilidad |
|---|---|---|
| `motor.py` (`SimulationService`) | 9.1 | Fachada única. Orquesta escenarios, propagación, riesgo, comparador, agentes, dashboard. |
| `base.py`           | 9.17 | Extrae el cuadro de métricas base del Gemelo Digital (solo lectura). |
| `escenarios.py`     | 9.2 | CRUD de escenarios independientes y virtuales. |
| `variables.py`      | 9.3 | Registro de variables what-if dentro de un escenario. |
| `propagacion.py`    | 9.4 | Motor de propagación por cadena de valor (elasticidades heurísticas enchufables). |
| `dominios.py`       | 9.5-9.8 | Constructores comercial/logística/RRHH/financiera/estructura. |
| `riesgo.py`         | 9.9 | Recalcula el riesgo por escenario (nunca reutiliza el real). |
| `comparador.py`     | 9.13 | Compara Actual vs Escenario A vs B por métrica. |
| `dashboard.py` (en motor) | 9.14 | Backend comparativo de escenarios. |
| `explicabilidad.py` | 9.15 | Hipótesis, variables, servicios, cadena causal, confianza. |
| `seguridad.py`      | 9.16 | Garantía estructural de que todo es virtual. |
| `lenguaje.py`       | 9.10/9.11 | Intérprete NL "¿qué ocurriría si...?" → variables. |

---

## 2. Motor what-if y propagación (9.3 / 9.4)

Variables alterables **virtualmente**: `precio`, `descuento`, `promocion`, `salario`, `plantilla`,
`stock`, `proveedor`, `impuestos`, `gastos`, `tiendas`, `almacenes`.

Cuando una variable cambia, se propaga la cadena de valor (la que modela el grafo del Gemelo
Digital) con elasticidades por defecto (enchufables, mismo patrón que el `Estimador` de
PredictionService):

```
Subir precio +5% → demanda −6% (elasticidad −1.2) → ingresos −1.3% → coste_ventas −6%
                 → IVA −1.3% → beneficio recalculado
```

Verificado: `precio +5%` → unidades −6.0 %, ingresos −1.3 %, beneficio +14.5 %, IVA −1.3 %
(coherente: cae el volumen y con él el COGS, subiendo el margen). Cada paso queda registrado en la
cadena causal para la explicabilidad.

---

## 3. Escenarios (9.2)

Cada escenario es **independiente y virtual**: al crearse captura una foto de las métricas base del
Gemelo Digital (`base_json`), guarda las variables alteradas (`sim_variables`) y los resultados
calculados (`sim_resultados`). Estados: `BORRADOR → SIMULADO → ARCHIVADO`. Borrar un escenario no
afecta a nada real.

---

## 4. Simulaciones por dominio

- **9.5 Comercial** — campañas, descuentos, promociones, fidelización, nuevos clientes.
- **9.6 Logística** — retrasos, roturas, cambio de proveedor, nuevos almacenes, cierres.
- **9.7 RRHH** — contrataciones, despidos, subidas salariales, reorganización.
- **9.8 Financiera** — flujo de caja, liquidez, gastos, IVA, inversiones.

Todas son azúcar sobre el motor genérico (`simular_directo`); no añaden lógica paralela.

---

## 5. Riesgo por escenario (9.9)

PredictionService recalcula el riesgo para **cada** escenario a partir de las métricas simuladas;
nunca se reutiliza el riesgo real tal cual. Se parte del riesgo base (solo lectura) y se ajusta por
los deltas del escenario (beneficio negativo → ALTO, liquidez negativa → ALTO, roturas > 5 → ALTO,
margen bajo → MEDIO), con factores explicables.

---

## 6. Comparador y Dashboard (9.13 / 9.14)

`comparar([A, B])` genera una tabla Actual vs Escenario A vs Escenario B con delta y delta% por
cada una de las 11 métricas normalizadas (ingresos, unidades, coste_ventas, coste_personal, gastos,
IVA, beneficio, margen, liquidez, plantilla, roturas). El dashboard reúne el estado actual, la lista
de escenarios y la comparativa para el panel ejecutivo.

---

## 7. Integraciones

- **IA (9.10)** — `IAService.simular(texto)` interpreta "¿qué ocurriría si subimos los precios un
  5%?" y responde vía SimulationService (fuentes: SimulationService + Gemelo Digital +
  PredictionService).
- **Copiloto (9.11)** — crea escenarios conversacionalmente ("Crea un escenario donde contratemos
  dos empleados más" → escenario persistido + impacto). Detectado ANTES del gate por dominio (es una
  capacidad transversal) y **restringido a roles globales** (administrador/gerente).
- **Agentes (9.12)** — `evaluar_con_agentes()` hace que cada agente (Comercial/RRHH/Financiero/
  Inventario/Compras) evalúe el impacto del escenario en su dominio, más titulares derivados de la
  propia simulación.
- **Gemelo Digital / PredictionService / BI** — única fuente del estado base y de la propagación.

---

## 8. Seguridad (9.16)

**Garantía estructural**: una simulación NUNCA puede generar pedidos, generar facturas, modificar
stock, cambiar contratos ni enviar correos. Verificado por análisis estático: **0 escrituras fuera
de las tablas `sim_*`**; el simulador solo LEE del Gemelo Digital/PredictionService y solo escribe
en `sim_escenarios`/`sim_variables`/`sim_resultados` (contenido virtual y borrable sin efecto real).
No existe ninguna ruta de escritura hacia datos operativos.

---

## 9. Rendimiento (9.17)

- Reutiliza el estado ya materializado por el Gemelo Digital (que a su vez cachea y reutiliza
  PredictionService/BI): **nunca recorre el ERP**.
- La propagación es aritmética sobre un cuadro de 11 métricas: coste despreciable.
- Persistencia mínima (metadatos del escenario + resultados), acotada por `id_empresa`.

---

## 10. Escalabilidad / SaaS

- **Multiempresa/multitienda**: todo acotado por `id_empresa`.
- **Modular**: añadir una variable what-if nueva es registrar una regla en `propagacion._REGLAS`
  sin tocar el resto; añadir un dominio es una función en `dominios.py`.
- **Estimador/elasticidades enchufables**: se pueden sustituir por modelos ML sin cambiar la API.

---

## 11. Compatibilidad (9.18)

Aditivo y no intrusivo. No modifica el funcionamiento de: TPV, Facturación, CRM, RRHH, Inventario,
Compras, Tesorería, Workflow, IA, Copiloto, Agentes, Gobierno, Centro de Actividad, Event Bus ni
Digital Twin. Integraciones IA/Copilot envueltas en `try/except`: si el simulador no está
disponible, cada uno se comporta como antes. **Certificado intacto**.

---

## 12. Pruebas

Verificación end-to-end (`DB_NAME=smart_manager_test`):

- 9.1/9.3/9.4 Simulación directa `precio +5%`: ingresos −1.3 %, unidades −6.0 %, beneficio +14.5 %,
  IVA −1.3 %; cadena causal registrada. ✔
- 9.2/9.9 Escenario persistido + riesgo recalculado. ✔
- 9.5 comercial(descuento 10 %); 9.6 logística(proveedor −10 % → beneficio +35 %); 9.7 rrhh(+2
  plantilla); 9.3 estructura(+1 tienda → ingresos +60 %). ✔
- 9.13 Comparador: columnas [Actual, Escenario A, Escenario B] × 11 métricas. ✔
- 9.12 Agentes: 5 evaluaciones + 3 titulares por dominio. ✔
- 9.14 Dashboard comparativo. ✔
- 9.10 IA `simular`; 9.11 Copiloto `simulacion.escenario` (ADMIN crea; OPERARIO restringido). ✔
- 9.16 Seguridad: 0 escrituras fuera de `sim_*`. ✔

**Smoke:** `5 passed`.

---

## 13. Preparación para Enterprise 10

El Simulador deja lista la base para el siguiente paquete (autonomía supervisada / motor
estratégico):

- Los **escenarios** son la unidad sobre la que un motor estratégico puede razonar y recomendar.
- El **comparador** permite elegir automáticamente el mejor escenario según objetivos.
- La **explicabilidad + confianza** habilitan decisiones supervisadas (proponer, no ejecutar).
- La **garantía virtual** es el cortafuegos que separa "simular" de "actuar": Enterprise 10 podrá
  proponer que una simulación aprobada se convierta en acción real, siempre a través de
  Workflow/BPM y Gobierno Corporativo, nunca de forma automática.

---

*Local, sin commitear. Migración 0095 aplicada y registrada en `MODULOS`. Smoke: 5 passed.*
