"""
Modelo 349 (Declaración recapitulativa de operaciones intracomunitarias) — FASE AEAT-6.

Recapitula, por EJERCICIO y por operador intracomunitario (NIF-IVA + país), la base imponible de:
  • Entregas intracomunitarias   (clave E) → facturas de cliente a clientes intracomunitarios.
  • Adquisiciones intracomunitarias (clave A) → facturas de compra a proveedores intracomunitarios.
Arquitectura preparada para claves adicionales (T triangular, S servicios), no calculadas aún.
Reutiliza íntegramente la infraestructura común AEAT (persistencia, estados, auditoría, PDF,
exportación). Solo se incluyen operadores con `es_intracomunitario=1` y NIF-IVA.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.aeat import base as _B
from src.services.aeat import documento as _D
from src.services.aeat.modelo_303 import _rango as _rango_periodo

logger = logging.getLogger("aeat.m349")

MODELO = "349"
PERIODO_ANUAL = "0A"
CLAVE_ENTREGA = "E"          # entregas intracomunitarias (clientes UE)
CLAVE_ADQUISICION = "A"      # adquisiciones intracomunitarias (proveedores UE)
# Arquitectura extensible (no calculadas en esta fase): "T" triangular, "S" servicios.
CLAVES_FUTURAS = ("T", "S")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def _filas(cur):
    return [(r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r)))
            for r in cur.fetchall()]


class OperadorIntracom:
    """Operación recapitulativa con un operador intracomunitario (una clave)."""

    __slots__ = ("clave", "nif_iva", "pais", "nombre", "base")

    def __init__(self, clave, nif_iva, pais, nombre, base):
        self.clave = clave
        self.nif_iva = nif_iva or ""
        self.pais = (pais or "").upper()
        self.nombre = nombre or ""
        self.base = round(float(base or 0), 2)

    def como_dict(self):
        return {"clave": self.clave, "nif_iva": self.nif_iva, "pais": self.pais,
                "nombre": self.nombre, "base": self.base}


class Modelo349:
    """Operaciones intracomunitarias agrupadas por (NIF-IVA, país, clave)."""

    def __init__(self, ejercicio, id_empresa=None):
        self.ejercicio = int(ejercicio)
        self.periodo = PERIODO_ANUAL
        self.id_empresa = _emp(id_empresa)
        self.desde, self.hasta = _rango_periodo(ejercicio, PERIODO_ANUAL)
        self._calcular()

    def _entregas(self):
        """Clave E: facturas de cliente a clientes intracomunitarios. Base imponible."""
        q = ("SELECT cli.nif_iva, cli.pais_fiscal, cli.nombre, COALESCE(SUM(f.base),0) AS base "
             "FROM facturas_cliente f JOIN clientes cli ON cli.id=f.id_cliente "
             "WHERE f.id_empresa=%s AND cli.es_intracomunitario=1 AND f.estado<>'anulada' "
             "AND COALESCE(f.fecha_emision,f.fecha) BETWEEN %s AND %s "
             "GROUP BY f.id_cliente, cli.nif_iva, cli.pais_fiscal, cli.nombre")
        out = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(q, (self.id_empresa, self.desde, self.hasta))
                for r in _filas(cur):
                    if float(r["base"] or 0) == 0:
                        continue
                    out.append(OperadorIntracom(CLAVE_ENTREGA, r["nif_iva"], r["pais_fiscal"],
                                                r["nombre"], r["base"]))
        except Exception as e:
            logger.error("_entregas: %s", e)
        return out

    def _adquisiciones(self):
        """Clave A: facturas de compra a proveedores intracomunitarios. Base imponible."""
        q = ("SELECT p.nif_iva, p.pais_fiscal, p.razon_social AS nombre, COALESCE(SUM(f.base),0) AS base "
             "FROM compras_facturas f JOIN proveedores p ON p.id_proveedor=f.id_proveedor "
             "WHERE f.id_empresa=%s AND p.es_intracomunitario=1 "
             "AND f.fecha_factura BETWEEN %s AND %s "
             "GROUP BY f.id_proveedor, p.nif_iva, p.pais_fiscal, p.razon_social")
        out = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(q, (self.id_empresa, self.desde, self.hasta))
                for r in _filas(cur):
                    if float(r["base"] or 0) == 0:
                        continue
                    out.append(OperadorIntracom(CLAVE_ADQUISICION, r["nif_iva"], r["pais_fiscal"],
                                                r["nombre"], r["base"]))
        except Exception as e:
            logger.error("_adquisiciones: %s", e)
        return out

    def _calcular(self):
        self.operadores = self._adquisiciones() + self._entregas()
        total = round(sum(o.base for o in self.operadores), 2)
        cas = []

        def add(c, desc, imp):
            cas.append({"casilla": c, "descripcion": desc, "importe": round(float(imp), 2)})

        add("01", "Nº de operadores intracomunitarios", len(self.operadores))
        add("02", "Importe total de las operaciones (base imponible)", total)
        for o in self.operadores:
            cod = "E_OP" if o.clave == CLAVE_ENTREGA else "A_OP"
            add(cod, f"{o.nif_iva} · {o.pais} · {o.nombre} [clave {o.clave}]", o.base)

        self._casillas = cas
        self.resultado = total
        self.sentido = "informativa"

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "resultado": self.resultado, "sentido": self.sentido,
                "operadores": [o.como_dict() for o in self.operadores], "casillas": self.casillas()}


def generar(ejercicio, *, id_empresa=None, usuario=None, observaciones=None) -> dict:
    """Genera (idempotente) el Modelo 349 del ejercicio: agrupa por operador intracomunitario,
    persiste la declaración (modelo=349, periodo=0A), produce el PDF y lo enlaza. No sobreescribe
    una declaración PRESENTADA."""
    id_empresa = _emp(id_empresa)
    m = Modelo349(ejercicio, id_empresa)
    did = _B.guardar_declaracion(MODELO, ejercicio, PERIODO_ANUAL, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = _D.generar_pdf(modelo=MODELO, titulo="Modelo 349 — Operaciones intracomunitarias",
                         ejercicio=m.ejercicio, periodo=PERIODO_ANUAL, id_declaracion=did,
                         casillas=m.casillas(), resultado=m.resultado, sentido=m.sentido,
                         hash_doc=decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "operadores": [o.como_dict() for o in m.operadores], "casillas": m.casillas(),
            "pdf": pdf, "hash": decl.get("hash")}
