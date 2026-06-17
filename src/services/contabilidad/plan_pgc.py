"""
Semilla del Plan General Contable de PYMES (subconjunto retail) — E6.1.

Cada cuenta: (codigo, nombre, tipo, naturaleza). El grupo se deriva del 1er dígito.
tipo ∈ activo|pasivo|pn|gasto|ingreso ; naturaleza ∈ deudora|acreedora.
Se clona POR EMPRESA al activar la contabilidad. Editable luego por empresa.
"""

# (codigo, nombre, tipo, naturaleza)
CUENTAS_PGC = [
    # Grupo 1 — Financiación básica (Patrimonio neto / pasivo)
    ("100", "Capital social", "pn", "acreedora"),
    ("112", "Reserva legal", "pn", "acreedora"),
    ("129", "Resultado del ejercicio", "pn", "acreedora"),
    ("170", "Deudas a largo plazo con entidades de crédito", "pasivo", "acreedora"),
    # Grupo 2 — Activo no corriente
    ("206", "Aplicaciones informáticas", "activo", "deudora"),
    ("216", "Mobiliario", "activo", "deudora"),
    ("217", "Equipos para procesos de información", "activo", "deudora"),
    ("280", "Amortización acumulada del inmovilizado intangible", "activo", "acreedora"),
    ("281", "Amortización acumulada del inmovilizado material", "activo", "acreedora"),
    # Grupo 3 — Existencias
    ("300", "Mercaderías", "activo", "deudora"),
    # Grupo 4 — Acreedores y deudores
    ("400", "Proveedores", "pasivo", "acreedora"),
    ("410", "Acreedores por prestaciones de servicios", "pasivo", "acreedora"),
    ("430", "Clientes", "activo", "deudora"),
    ("436", "Clientes de dudoso cobro", "activo", "deudora"),
    ("440", "Deudores", "activo", "deudora"),
    ("465", "Remuneraciones pendientes de pago", "pasivo", "acreedora"),
    ("472", "Hacienda Pública, IVA soportado", "activo", "deudora"),
    ("475", "Hacienda Pública, acreedora por conceptos fiscales", "pasivo", "acreedora"),
    ("4750", "Hacienda Pública, acreedora por IVA", "pasivo", "acreedora"),
    ("476", "Organismos de la Seguridad Social, acreedores", "pasivo", "acreedora"),
    ("477", "Hacienda Pública, IVA repercutido", "pasivo", "acreedora"),
    ("4700", "Hacienda Pública, deudora por IVA", "activo", "deudora"),
    # Grupo 5 — Cuentas financieras
    ("520", "Deudas a corto plazo con entidades de crédito", "pasivo", "acreedora"),
    ("570", "Caja, euros", "activo", "deudora"),
    ("572", "Bancos e instituciones de crédito c/c vista, euros", "activo", "deudora"),
    # Grupo 6 — Compras y gastos
    ("600", "Compras de mercaderías", "gasto", "deudora"),
    ("608", "Devoluciones de compras y operaciones similares", "gasto", "acreedora"),
    ("609", "Rappels por compras", "gasto", "acreedora"),
    ("610", "Variación de existencias de mercaderías", "gasto", "deudora"),
    ("621", "Arrendamientos y cánones", "gasto", "deudora"),
    ("622", "Reparaciones y conservación", "gasto", "deudora"),
    ("628", "Suministros", "gasto", "deudora"),
    ("629", "Otros servicios", "gasto", "deudora"),
    ("640", "Sueldos y salarios", "gasto", "deudora"),
    ("642", "Seguridad Social a cargo de la empresa", "gasto", "deudora"),
    ("659", "Otras pérdidas en gestión corriente", "gasto", "deudora"),
    ("662", "Intereses de deudas", "gasto", "deudora"),
    # Grupo 7 — Ventas e ingresos
    ("700", "Ventas de mercaderías", "ingreso", "acreedora"),
    ("705", "Prestaciones de servicios", "ingreso", "acreedora"),
    ("708", "Devoluciones de ventas y operaciones similares", "ingreso", "deudora"),
    ("709", "Rappels sobre ventas", "ingreso", "deudora"),
    ("710", "Variación de existencias de mercaderías", "ingreso", "acreedora"),
    ("769", "Otros ingresos financieros", "ingreso", "acreedora"),
]
