"""
Contabilidad (E6) — contabilidad operativa integrada (control financiero interno).

Consumidora de eventos del ERP (ventas/compras/devoluciones/mermas) vía cola
asíncrona; NUNCA bloquea la operación. Multiempresa por id_empresa. Doble partida.
Alcance v1 (DC1): plan, cuentas, ejercicios, asientos, diario, mayor, balances,
PyG, libros de IVA y borrador 303. NO incluye presentación telemática AEAT.
"""
