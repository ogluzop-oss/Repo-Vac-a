# Informe Técnico — Módulo 7: TPV

**Auditoría (ya existía):** promociones (descuento_pct, importe_fijo, 2x1, pack, regalo) con reglas y
evaluador de mejor descuento; fidelización (puntos/movimientos); devoluciones (+ baneados);
cierre Z con cadena hash y PDF; sesión/arqueo de caja (`db.caja`); reservas y pedidos de cliente
(`ventas_comercial`: presupuesto→pedido→venta con reserva de stock); báscula/autocobro.

**Gaps implementados:**
- **Promos escalonadas** (extensión ADITIVA del evaluador `db/promociones.py`, sin nueva tabla):
  tipos `nxm` (3x2/4x3: una unidad gratis por grupo de N) y `segunda_unidad` (2ª unidad al X%).
- **Aparcar/recuperar tickets** (migr 0107 `tpv_tickets_aparcados` + `tpv_pro.aparcar_ticket` ·
  `tickets_aparcados` · `recuperar_ticket`): multiticket paralelo por caja, sin tocar stock.
- **Arqueo por denominación** (`tpv_arqueo_denominaciones` + `registrar_arqueo_denominaciones` ·
  `detalle_arqueo`): recuento físico billetes/monedas EUR, diferencia frente al esperado
  **reutilizando `db.caja.arqueo`**.
- **Análisis del turno** (`analisis_turno`): **reutiliza `cierre_z.resumen_dia`** (por forma de pago).

**Reutilización:** evaluador de promociones existente; `db.caja.arqueo` (esperado); `cierre_z`; sin
duplicar fidelización/devoluciones/cierre. Multiempresa, auditado.

**Pruebas:** migr 0107; nxm 6×10→20€, segunda_unidad 4×10→10€; aparcar+recuperar; arqueo 262€ con 4
denominaciones. **smoke 5 passed.**

**Mejoras futuras:** click&collect explícito (flag de recogida en pedido online → aviso al cliente
por el módulo de comunicaciones); descuentos por umbral de importe en el ticket completo (hoy por
línea); GUI del arqueo por denominación en el cierre de caja.
