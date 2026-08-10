"""
Simuladores por dominio (Paquete Enterprise 9, SUBFASE 9.5-9.8). Constructores de conveniencia que
preparan las variables what-if tipicas de cada dominio y las simulan sobre el estado base. Son
azucar sobre el motor generico (SimulationService.simular_directo); no anaden logica paralela.

  9.5 Comercial   : campanas, descuentos, promociones, fidelizacion, nuevos clientes.
  9.6 Logistica   : retrasos, roturas, cambios de proveedor, nuevos almacenes, cierres.
  9.7 RRHH        : contrataciones, despidos, vacaciones, bajas, reorganizacion.
  9.8 Financiera  : flujo de caja, liquidez, cobros, pagos, financiacion, inversiones.
"""

from src.services.simulador import motor as _M


def _svc():
    return _M.servicio()


# ── 9.5 COMERCIAL ─────────────────────────────────────────────────────────────
def comercial(*, descuento=None, promocion=None, precio=None, nuevos_clientes_pct=None,
              id_empresa=None) -> dict:
    vs = []
    if precio is not None:
        vs.append({"variable": "precio", "valor": precio})
    if descuento is not None:
        vs.append({"variable": "descuento", "valor": descuento})
    if promocion is not None:
        vs.append({"variable": "promocion", "valor": promocion})
    if nuevos_clientes_pct is not None:
        # nuevos clientes/fidelizacion → mas demanda: se modela como promocion suave sin coste extra.
        vs.append({"variable": "promocion", "valor": nuevos_clientes_pct})
    return _svc().simular_directo(vs, id_empresa)


# ── 9.6 LOGISTICA ─────────────────────────────────────────────────────────────
def logistica(*, coste_proveedor=None, stock=None, nuevos_almacenes=None, rotura=None,
              id_empresa=None) -> dict:
    vs = []
    if coste_proveedor is not None:
        vs.append({"variable": "proveedor", "valor": coste_proveedor})
    if stock is not None:
        vs.append({"variable": "stock", "valor": stock})
    if rotura is not None:
        vs.append({"variable": "stock", "valor": -abs(rotura)})   # una rotura = menos stock efectivo
    if nuevos_almacenes is not None:
        vs.append({"variable": "almacenes", "valor": nuevos_almacenes})
    return _svc().simular_directo(vs, id_empresa)


# ── 9.7 RRHH ──────────────────────────────────────────────────────────────────
def rrhh(*, contrataciones=None, despidos=None, subida_salarial=None, id_empresa=None) -> dict:
    vs = []
    neto = (int(contrataciones or 0)) - (int(despidos or 0))
    if neto:
        vs.append({"variable": "plantilla", "valor": neto})
    if subida_salarial is not None:
        vs.append({"variable": "salario", "valor": subida_salarial})
    return _svc().simular_directo(vs, id_empresa)


# ── 9.8 FINANCIERA ────────────────────────────────────────────────────────────
def financiera(*, gastos=None, nuevo_iva=None, inversion=None, id_empresa=None) -> dict:
    vs = []
    if gastos is not None:
        vs.append({"variable": "gastos", "valor": gastos})
    if inversion is not None:
        # una inversion es un gasto/uso de liquidez en el periodo (proxy).
        vs.append({"variable": "gastos", "valor": inversion})
    if nuevo_iva is not None:
        vs.append({"variable": "impuestos", "valor": nuevo_iva})
    return _svc().simular_directo(vs, id_empresa)


# ── ESTRUCTURA (nueva tienda) ─────────────────────────────────────────────────
def estructura(*, nuevas_tiendas=None, nuevos_almacenes=None, id_empresa=None) -> dict:
    vs = []
    if nuevas_tiendas is not None:
        vs.append({"variable": "tiendas", "valor": nuevas_tiendas})
    if nuevos_almacenes is not None:
        vs.append({"variable": "almacenes", "valor": nuevos_almacenes})
    return _svc().simular_directo(vs, id_empresa)
