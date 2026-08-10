# AUDITORÍA DE DUPLICIDADES — Smart Manager AI (Fase 0)

Auditoría ERP-wide previa a la integración de la UI de los paquetes Enterprise. Clasifica
duplicidades en: **funcionales, dashboards, exportadores, buscadores/filtros, tablas, estadísticas
y estilos**. Cada hallazgo indica **valor** (de fusionarlo) y **riesgo** (de tocarlo ahora), y si
se **funde ahora** o va a **backlog** (Sprint 2+).

> Método: barrido read-only de `src/gui/*.py` (51 ventanas) y `src/services/*`. No se ha modificado
> ningún archivo. Los puntos de instanciación exactos se detallan en `DEPENDENCIAS_UI.md` (Fase 0.5).

---

## 0. Resumen ejecutivo

- Los 8 paquetes a hospedar **no tienen UI previa** (`prediccion`, `automatizacion`, `gobierno`,
  `gemelo`, `simulador`, `autonomia` = **0** referencias en GUI; `agentes` = 0). Por tanto su
  integración es **aditiva**: no hay ventanas duplicadas que sustituir → **riesgo bajo**.
- Presencia parcial ya existente (resúmenes, no gestión): `actividad` (2 GUIs), `ia` (1), `copilot`
  (1), `eventos` (1) — concentrada en `centro_actividad.py`.
- Duplicidad real de mayor valor: **familia de "cuadros de mando"** (BI + Dashboard Enterprise +
  ~9 dashboards de módulo) y **exportadores/buscadores** repetidos.

---

## 1. Duplicidades FUNCIONALES

| # | Solape | Componentes | Valor | Riesgo | Acción |
|---|---|---|---|---|---|
| F1 | **Dashboard Enterprise ⇆ BI** | `bi_dashboard.py` (KPIs por dominio + forecast) vs. panel ejecutivo de los paquetes | Alto | Bajo | **Fundir ahora** → pestaña "Dashboard Ejecutivo" del Centro de Inteligencia |
| F2 | **Predicción dispersa** | Alertas en `centro_actividad.py` + forecast en `bi_dashboard.py`; `PredictionService` sin ventana | Alto | Bajo | **Fundir ahora** → pestaña "Predicción" (abanico completo). El resumen del Centro se mantiene |
| F3 | **Automatización dispersa** | Métricas-resumen en `centro_actividad.py`; `AutomationService` sin gestión | Medio | Bajo | **Fundir ahora** → pestaña "Automatización" en Aprobaciones |
| F4 | **Delegaciones** | `gobierno.delegacion` (sustitución de autoridad) ⇆ `wf_delegaciones` (delegación de tareas) | Medio | Medio | **Fundir ahora** → pestaña única "Delegaciones" (Gobierno/Seguridad) que cubre ambos conceptos |
| F5 | **Autoridad/roles ⇆ RBAC** | `gobierno` (autoridad organizativa) ⇆ `seguridad_gui.py` (roles/permisos/ACL) | Medio | Bajo | **Co-alojar** en Seguridad (complementarios; no se fusionan datos) |
| F6 | **Estado de tiendas** | `gemelo` (estado por dominios) ⇆ `centro_actividad` (sync/tiendas) | Bajo | Bajo | **Co-alojar** como pestañas hermanas del Centro de Inteligencia |

---

## 2. Duplicidades de DASHBOARDS

~10 ventanas "cuadro de mando" con estructura KPI/grid similar:

`bi_dashboard.py`, `bi_corporativo.py`, `crm_dashboard.py`, `finanzas_dashboard.py`,
`calidad_dashboard.py`, `gmao_dashboard.py`, `mrp_dashboard.py`, `sat_dashboard.py`,
`dr_dashboard_gui.py`, `resiliencia_dashboard.py`.

- **Observación**: no se enrutan desde `menu_principal.py`; se abren **desde sus propios módulos**
  (CRM, Finanzas, GMAO, SAT, DR…). Cada uno reimplementa su rejilla de KPIs/estadística.
- **Acción AHORA**: solo `bi_dashboard.py` → "Dashboard Ejecutivo" del Centro de Inteligencia (F1).
  `bi_corporativo.py` = candidato a sub-vista (evaluar, no forzar).
- **Backlog (Sprint 2+)**: unificar la rejilla de KPIs mediante `EnterpriseDashboardGrid` +
  `EnterpriseCard`; **NO mover** los dashboards de módulo en esta iteración (regla 12). Solo
  documentados aquí.

---

## 3. Duplicidades de EXPORTACIÓN

5 ventanas con exportación propia (Excel/PDF), lógica repetida:

`bi_dashboard.py`, `gestion_mermas.py`, `informe_reposicion.py`, `mostrar_stock.py`,
`ubicacion_tienda.py`.

- **Valor**: Alto · **Riesgo**: Bajo.
- **Acción AHORA**: crear `foundation/export.py::exportar_excel(...)` y migrar **solo** el
  exportador de las pantallas modificadas en esta iteración (p.ej. el de `bi_dashboard.py` al pasar
  a Dashboard Ejecutivo). Resto → Sprint 2.

---

## 4. Duplicidades de BUSCADORES / FILTROS

16 ventanas con su propio buscador/filtro (`textChanged.connect`, `_filtrar`, `_buscar`).

- **Valor**: Alto (consistencia) · **Riesgo**: Medio (tocar 16 pantallas ahora).
- **Acción AHORA**: crear `EnterpriseSearch`/`EnterpriseFilter` y usarlos **solo en las tablas
  nuevas** de los paneles Enterprise. Adopción en las 16 pantallas antiguas → backlog incremental
  (Strangler, regla 4).

---

## 5. Duplicidades de TABLAS y ESTILOS

- **Tablas**: ya hay base compartida (`catalogo_gestion._tabla`), pero sin filtros/paginación/menú
  contextual homogéneos. → `EnterpriseTable` los unifica; adopción incremental.
- **Estilos/colores/iconos**: cada pantalla define colores ad-hoc (múltiples cian/rojos, iconos
  distintos por concepto). → `foundation/tokens.py` (color semántico) + `foundation/icons.py`
  (un icono por concepto). Base para la unificación visual.

---

## 6. Duplicidades de ESTADÍSTICAS

- Cálculos de KPIs/estadística repetidos en varios dashboards de módulo, cuando ya existen motores
  (`bi`, `prediccion`, calculadores por dominio). **No se recalcula en la GUI** (regla 5). Backlog:
  que cada dashboard consuma el motor correspondiente. Documentado; no se toca ahora.

---

## 7. Plan de fusión (qué se hace en esta iteración)

**Se funde AHORA** (valor alto / riesgo bajo, dentro del alcance):
- F1 Dashboard Enterprise ⇆ BI → "Dashboard Ejecutivo".
- F2 Predicción → pestaña unificada.
- F3 Automatización → pestaña de gestión en Aprobaciones.
- F4 Delegaciones → pestaña única.
- Exportación única (`export.py`) para las pantallas modificadas.
- Componentes `EnterpriseTable`/`Search`/`Card` en los paneles nuevos.

**Backlog documentado (Sprint 2+, Strangler)**:
- Migrar el resto de exportadores y buscadores a la librería.
- Unificar la rejilla de KPIs de los dashboards de módulo (`EnterpriseDashboardGrid`).
- **NO mover** CRM/Finanzas/Calidad/GMAO/DR/BI Corporativo dashboards (regla 12): solo documentados.

---

## 8. Riesgos y mitigación

- **Riesgo principal**: dependencias cruzadas ocultas (imports/señales) en las ventanas host
  (BI, Seguridad, Aprobaciones, Centro de Actividad). → mitigado por `DEPENDENCIAS_UI.md` (Fase 0.5)
  antes de tocar GUI.
- **Compatibilidad hacia atrás**: se conservan `v_id`, rutas y firmas públicas (regla 2).
- **Paquetes sin UI previa** (0 referencias) → integración aditiva, sin sustitución → riesgo mínimo.

---

*Fase 0 completada. Siguiente: Fase 0.5 → `DEPENDENCIAS_UI.md` (inventario de dependencias UI de las
ventanas host antes de modificarlas).*
