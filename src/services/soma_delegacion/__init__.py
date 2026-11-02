"""
Delegación de tareas repetitivas al agente IA SOMA (SUPERADMIN) — "cuando pase X, que SOMA actúe
siguiendo estas instrucciones [texto libre]". Capa NUEVA (auditada previamente: ni el motor de
Automatización clásico — catálogo cerrado condición+acción — ni Autonomía IA — planes de
ejecución — ni el Mission Engine de SOMA soportan instrucciones en lenguaje natural persistidas
por empresa); reutiliza de esos y otros motores ya existentes todo lo que no es exclusivo de esto:
el cliente Anthropic de SOMA (`copilot.motor_llm`), el Event Bus (`services.eventos`), y el CRUD
de cada módulo de negocio (presupuestos de `db.ventas_comercial`, envío de `services.correo`,
centros de `db.centros`…) — nunca un motor de negocio paralelo.

- `catalogo.py` — catálogo EXTENSIBLE de tipos de delegación (módulo + evento disparador +
  ejecutor), para poder sumar más módulos sin tocar el motor.
- `reglas.py` — CRUD de las reglas (`soma_delegaciones`): una regla = tipo + instrucciones
  (obligatorias) + modo de aplicación + activa/inactiva.
- `historial.py` — registro de cada evaluación/ejecución (`soma_delegaciones_historial`).
- `motor.py` — dispatch: `procesar_evento(tipo, contexto, id_empresa)` evalúa todas las reglas
  activas de ese tipo y delega en el ejecutor del catálogo; `preguntar_soma(prompt, ...)` es el
  único punto de llamada a la IA (mismo cliente/medición que el resto de asistentes SOMA).
- `ejecutores/` — un módulo por dominio de negocio (correo, crm, centros…), cada uno SOLO
  construye el prompt específico y aplica la decisión reutilizando el CRUD real de su módulo.
"""
