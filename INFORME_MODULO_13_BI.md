# Informe Técnico — Módulo 13: Business Intelligence

**Auditoría (ya existía):** Data Warehouse (`bi_corp/dw.py`), motor único de KPIs con **registro de
KPIs personalizados** (`bi/kpis.py: registrar_kpi`), calculadores por dominio, forecasting Prophet
(`bi/forecasting.py`, `forecast_corp.py`), snapshots con scheduler, dashboard, y a nivel corporativo
OLAP (cubos/drill/slice/dice), consolidación multiempresa, benchmarking, alertas explicables, export
(PDF/Excel/CSV/JSON) e IA ejecutiva. También el hub UI "Centro de Inteligencia Empresarial".

**Gaps implementados (migr 0113 + `src/services/bi/suscripciones.py`):**
- **Suscripciones / distribución programada de informes-KPI** (`bi_suscripciones`): `crear_suscripcion`
  (usuarios/roles, canal, periodicidad), `enviar_suscripcion` (**reutiliza `bi.kpis.obtener_dashboard`**
  para el contenido y **Comunicaciones** para la entrega) + job `bi_suscripciones_distribucion`
  registrado en el JobRegistry (envía los vencidos y reprograma).
- **Cuadros de mando personales por usuario** (`bi_cuadros_personales`): `guardar_cuadro` (layout JSON
  de widgets/KPIs, uno predeterminado por usuario) · `cuadros_de_usuario`.

**Reutilización:** motor de KPIs existente (0 recálculo); Comunicaciones/notificaciones para la
entrega; Scheduler/JobRegistry; auditoría; multiempresa. La definición de KPIs personalizados YA
existía (`registrar_kpi`), por lo que no se reimplementó.

**Pruebas:** migr 0113; suscripción mensual + envío con contenido de KPIs + job distribuye ≥1; cuadro
personal con layout de widgets recuperado; job en `CATALOGO`. **smoke 5 passed.**

**Mejoras futuras:** entrega por email con PDF adjunto (reutilizar `bi_corp/export.py`); editor visual
de cuadros personales en el Centro de Inteligencia; suscripción a un cubo OLAP concreto con filtros.
