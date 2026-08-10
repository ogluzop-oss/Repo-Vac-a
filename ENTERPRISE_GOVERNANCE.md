# ENTERPRISE GOVERNANCE — Gobierno Corporativo

**Paquete Enterprise 7 — Smart Manager**
Sistema de gobierno organizativo: organigrama, responsabilidades, cadenas de aprobación,
delegación temporal, escalado automático, matriz de autoridad, herencia de políticas y
gobierno para la IA.

Estado: **implementado, verificado en local, sin commitear.**
Migración: `0093_gobierno_corporativo` (idempotente, reversible, aditiva).

---

## 1. Arquitectura

Punto de entrada único (fachada, patrón `servicio()` como el resto de paquetes Enterprise):

```python
from src.services import gobierno
gobierno.servicio().puede_aprobar("CAJA9", "compras", importe=7000)
gobierno.servicio().dashboard()
```

Módulos (`src/services/gobierno/`):

| Módulo | Subfase | Responsabilidad |
|---|---|---|
| `organigrama.py`   | 7.1 / 7.6 | Jerarquía grupo→empresa→zona→tienda→departamento→empleado. Materialized path (`ruta` + `nivel`) para subárbol/ancestros en una sola consulta. |
| `responsables.py`  | 7.2 | Asignación de roles orgánicos a usuarios por nodo; cadena de mando (nodo + ancestros). |
| `delegacion.py`    | 7.4 | Delegaciones temporales con ventana `desde/hasta`; sustitución de ausentes. |
| `aprobaciones.py`  | 7.3 | Catálogo de reglas (entidad + condición de importe → cadena de roles). Reutiliza Workflow/BPM. |
| `autoridad.py`     | 7.7 | Matriz rol_org → permisos; mapeo perfil ERP → rol orgánico. |
| `politicas.py`     | 7.8 | Políticas por nodo con **herencia** (nodo → ancestros → empresa). |
| `escalado.py`      | 7.5 | Escalado automático de pendientes vencidos por horas → tarea + auditoría. |
| `gobierno_ia.py`   | 7.9 | Rol efectivo + `puede_aprobar()` explicable para Copiloto/Agentes. |
| `dashboard.py`     | 7.10 | Indicadores directivos (solo lectura, agregados). |
| `motor.py`         | — | `GovernanceService`: fachada que delega en todos los módulos. |

**Principio de diseño:** ningún motor nuevo. Se reutilizan Workflow/BPM
(`workflow_engine.iniciar_proceso`), AutomationService (`acciones.crear_tarea` /
`solicitar_aprobacion`), Auditoría (`log_auditoria`), control por roles y el contexto
multiempresa/multitienda existente.

---

## 2. Integraciones (reutilización absoluta)

- **Workflow/BPM** — las cadenas de aprobación lanzan procesos reales vía
  `aprobaciones.iniciar_aprobacion → workflow_engine.iniciar_proceso`. No se reimplementa el
  motor de flujos.
- **AutomationService** — el escalado y las tareas se materializan a través del catálogo de
  acciones de automatización (`crear_tarea`, `solicitar_aprobacion`), no con inserciones ad-hoc.
- **Copiloto (Enterprise 5)** — `copilot/acciones.py` consulta al gobierno **antes** de proponer
  una aprobación: si el usuario no tiene autoridad, devuelve `estado="DENEGADA"` con el motivo
  ("corresponde al Administrador"), citando las fuentes *Gobierno Corporativo* y *Workflow/BPM*.
- **Agentes (Enterprise 6)** — `gobierno_ia.contexto()` expone rol, permisos, nodos y sustituciones.
- **Auditoría** — delegaciones y escalados registran `log_auditoria`.
- **Multiempresa/Multitienda** — todas las tablas llevan `id_empresa VARCHAR(36)`; las reglas de
  aprobación pueden ser globales (`id_empresa NULL`) o por empresa.

---

## 3. Jerarquías

Nodo (`org_nodos`): `tipo`, `nombre`, `padre_id`, `nivel`, `ruta` (materialized path, p.ej.
`/1/5/12/`), `estado`, `id_ref` (enlace a la entidad real: tienda, usuario…), `datos` (JSON).

- `subarbol(nodo)` — descendientes vía `ruta LIKE '<ruta>%'` (una consulta, sin recursión).
- `ancestros(nodo)` — se derivan de los ids de la `ruta` (sin N consultas).
- `cadena_mando(nodo)` — recorre el nodo y sus ancestros recogiendo director/principal/administrador.

Verificado: Grupo Kik → Zona Norte → Tienda Vic → Compras; `subarbol=4`, `mapa=4`;
cadena de mando de Compras = `[('Tienda Vic','GERENTE_VIC'), ('Grupo Kik','ADMIN')]`.

---

## 4. Delegaciones

`org_delegaciones`: `usuario_origen`, `usuario_delegado`, `motivo`, `desde`, `hasta`, `activa`.

- `delegar()` crea la delegación + auditoría `DELEGACION_CREADA`.
- `sustituye_a(usuario)` devuelve los orígenes que un usuario cubre dentro de la ventana activa.
- El **rol efectivo** de quien sustituye a un responsable ausente se eleva a ≥ `director`
  (SUBFASE 7.4), de modo que la cadena de aprobación no se rompe por una ausencia.

Verificado: `SUPLENTE_X` sustituye a `['GERENTE_VIC']`; delegaciones activas = 1.

---

## 5. Escalados

`org_escalados`: `referencia`, `desde_usuario`, `hacia_usuario`, `nivel`, `horas`, `motivo`.

`escalado.revisar()` recorre las ejecuciones `PENDIENTE` (`automatizaciones_ejecuciones`) más
antiguas que el umbral y escala según nivel horario: 24h→supervisor, 48h→director,
72h→administrador. Cada escalado genera una tarea (AutomationService) y traza `log_auditoria`.
`registrar_job()` lo integra en el scheduler existente (idempotente).

---

## 6. Compatibilidad

- **Aditivo:** solo `CREATE TABLE IF NOT EXISTS`; sin DROP/ALTER destructivo ni renumeraciones.
- **Reversible:** eliminar las 6 tablas de `0093` y quitar la entrada del `MODULOS` devuelve el
  sistema al estado previo; ningún flujo certificado depende del gobierno para funcionar.
- **No intrusivo:** la integración con Copiloto está envuelta en `try/except` — si el gobierno
  falla o no está disponible, el Copiloto sigue proponiendo la aprobación como antes.
- **Certificado intacto:** Verifactu, AEAT, Facturación, hashes, numeraciones, TPV, Kárdex,
  Contabilidad, Tesorería, CRM, RRHH, Workflow, BI y Event Bus no se han modificado.

---

## 7. Pruebas

Verificación end-to-end (`DB_NAME=smart_manager_test`):

- 7.1 Organigrama: 4 nodos, subárbol=4, mapa=4. ✔
- 7.2 Cadena de mando (Compras): `[('Tienda Vic','GERENTE_VIC'),('Grupo Kik','ADMIN')]`. ✔
- 7.3 Cadena de compras 7000: `APR_COMPRAS_5000` → `['principal','director','administrador']`. ✔
- 7.4 Sustitución: `SUPLENTE_X` sustituye a `['GERENTE_VIC']`. ✔
- 7.8 Herencia de políticas: tienda hereda 5000, override local 2000, empresa sigue 5000. ✔
- 7.9 Autoridad IA:
  - `cajero` (OPERARIO/suplente) compras 7000 → **False** — "corresponde al Administrador". ✔
  - `admin` (ADMINISTRADOR) compras 7000 → **True** (rol administrador). ✔
  - `gerente` (GERENTE) compras 3000 (sin cadena) → **True** — autorizado por rol. ✔
- Copiloto → gobierno: intención `solicitar_aprobacion`, estado `DENEGADA` cuando falta autoridad. ✔
- 7.10 Dashboard: `{nodos_total:4, tiendas:1, delegaciones_activas:1, aprobaciones_pendientes:0}`. ✔

**Smoke:** `5 passed`.

---

## 8. Rendimiento

- Subárbol/ancestros resueltos con **materialized path** (una consulta, sin recursión ni N+1).
- Dashboard con conteos agregados (`COUNT(*)`), solo lectura.
- Consultas de gobierno acotadas por `id_empresa` (índice natural del patrón multiempresa).

---

## 9. Seguridad

- **Matriz de autoridad** explícita rol_org → permisos; `administrador` es el único con todos.
- **Rol efectivo = máximo** entre el rol orgánico asignado y el rol derivado del perfil ERP:
  un ADMINISTRADOR conserva su autoridad aunque esté asignado a un nodo con rol inferior; y un
  OPERARIO no puede elevar su autoridad por estar asignado a un nodo.
- Toda decisión de aprobación es **explicable** (motivo textual con la cadena y el rol requerido).
- Delegaciones y escalados quedan **auditados**.
- IA/Copiloto solo **consultan** el gobierno (no escriben en sus tablas).

---

## 10. Limitaciones (v1)

- El catálogo de reglas de aprobación se siembra con 3 reglas de ejemplo
  (`APR_COMPRAS_5000`, `APR_FACTURA_10000`, `APR_GASTO_1000`); la edición desde GUI queda para
  una fase posterior.
- La condición de las reglas se evalúa sobre `importe` (comparadores simples); condiciones
  compuestas multivariable quedan pendientes.
- El escalado se apoya en `automatizaciones_ejecuciones` (pendientes de automatización); otros
  orígenes de pendientes se pueden añadir de forma aditiva.
- No hay aún pantalla dedicada de organigrama; los indicadores se exponen vía dashboard/servicio.

---

## 11. Preparación futura

- **Digital Twin / Simulador (Enterprise 8+):** el organigrama y la matriz de autoridad son la
  base para simular reorganizaciones y su impacto en cadenas de aprobación.
- **Motor estratégico / autonomía supervisada:** `gobierno_ia.puede_aprobar` ya delimita hasta
  dónde puede decidir un agente por sí mismo y cuándo debe escalar.
- **Editor visual de organigrama y de reglas** desde la GUI del Centro de Actividad.
- **Estimador ML** conectable en la evaluación de riesgo de aprobaciones (mismo patrón pluggable
  que el motor predictivo).

---

*Local, sin commitear. Migración 0093 aplicada y registrada en `MODULOS`. Smoke: 5 passed.*
