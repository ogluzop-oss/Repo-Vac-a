# Informe Técnico — Módulo 17: GMAO

**Auditoría (ya existía, `services/gmao/*`):** activos (`activos.py`), planes de mantenimiento
**preventivo por calendario** (diario…anual + job de Scheduler que genera OT preventivas —
`planes.py`), órdenes de trabajo con **repuestos por kárdex y costes** (`ordenes.py`, tipos
preventiva/correctiva/**predictiva**), analítica MTTR/MTBF e IA predictiva (`analitica.py`).

**Gaps implementados (migr 0117 + `src/services/gmao/gmao_pro.py`):**
- **Mantenimiento por uso/condición** (`gmao_medidores`, `gmao_lecturas`): `alta_medidor`
  (horas/km/ciclos con umbral), `registrar_lectura` — cuando el uso desde la última OT alcanza el
  umbral **genera una OT preventiva reutilizando `gmao.ordenes.crear_ot`** y reinicia el contador.
- **Rondas / checklists de inspección** (`gmao_checklists`, `gmao_ronda_ejecuciones`):
  `crear_checklist`, `ejecutar_ronda` — si algún ítem falla, **genera una OT correctiva** (crear_ot).

**Reutilización:** `gmao.ordenes.crear_ot` (OT con su ciclo/repuestos/costes intactos); auditoría;
multiempresa. El preventivo por calendario y su job existentes no se tocan: el nuevo dispara por uso.

**Pruebas:** migr 0117; medidor umbral 500 → lectura 520 genera OT preventiva y reinicia (uso 80);
ronda conforme sin OT, ronda con fallo → OT correctiva. **smoke 5 passed.**

**Mejoras futuras:** mantenimiento predictivo real por lecturas de sensores (integración IoT →
tipo 'predictiva'); rondas programadas por Scheduler; garantías de activos con alertas.
