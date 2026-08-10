# Informe Técnico — Módulo 18: SAT / Helpdesk

**Auditoría (ya existía, `services/sat/*`):** tickets con SLA (resolución de SLA por cliente/prioridad
desde `contratos_sla.py`), colas con auto-asignación, comentarios (cliente/interno), estados,
intervenciones, base de conocimiento (`kb.py`), email-to-ticket (`email_ticket.py` + job), portal de
cliente y analítica.

**Gaps implementados (migr 0118 + `src/services/sat/sat_pro.py`):**
- **Encuestas de satisfacción (CSAT)** (`sat_encuestas`): `enviar_encuesta` (token único, aviso por
  Comunicaciones al cierre), `responder_encuesta` (1-5, anti-doble-respuesta), `csat` (media, %
  satisfechos ≥4, nº respuestas por período).
- **Bolsa de horas de contrato** (`sat_bolsas_horas`, `sat_consumo_horas`): `crear_bolsa_horas`,
  `consumir_horas` (desde intervención; avisa saldo negativo/agotada y marca no vigente al agotar),
  `saldo_bolsa`.

**Reutilización:** tickets/intervenciones/contratos existentes; Comunicaciones/notificaciones para el
envío de la encuesta; auditoría; multiempresa.

**Pruebas:** migr 0118; encuesta con anti-doble-respuesta, CSAT medio 4,0 (50 % satisfechos); bolsa de
10 h con consumos → saldo −1 h y agotada. **smoke 5 passed.**

**Mejoras futuras:** disparo automático de la encuesta al cerrar el ticket (hook en
`tickets.cambiar_estado` → 'cerrado'); NPS además de CSAT; consumo de bolsa de horas automático desde
el tiempo real de cada intervención; alerta al cliente cuando la bolsa baja de un umbral.
