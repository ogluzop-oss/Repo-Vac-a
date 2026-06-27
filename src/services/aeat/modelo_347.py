"""
Modelo 347 (Declaración anual de operaciones con terceras personas) — FASE AEAT-5.

Agrega, por EJERCICIO y por tercero, las operaciones con clientes (facturas de cliente, clave B)
y con proveedores (facturas de compra, clave A), con desglose trimestral, y aplica el umbral
legal de 3.005,06 € (se excluyen los terceros por debajo). El tercero ya existe a nivel de
documento (`facturas_cliente.id_cliente`, `compras_facturas.id_proveedor`), por lo que NO se
modifica el posting contable. Reutiliza la infraestructura común AEAT (persistencia, estados,
auditoría, PDF, exportación).
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.aeat import base as _B
from src.services.aeat import documento as _D
from src.services.aeat.modelo_303 import _rango as _rango_periodo

logger = logging.getLogger("aeat.m347")

MODELO = "347"
PERIODO_ANUAL = "0A"
UMBRAL = 3005.06            # umbral legal anual por tercero/clave
CLAVE_COMPRAS = "A"        # adquisiciones (proveedores)
CLAVE_VENTAS = "B"         # entregas (clientes)


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


class Declarado:
    """Operaciones anuales con un tercero (una clave A/B) con desglose trimestral."""

    __slots__ = ("clave", "nif", "nombre", "t1", "t2", "t3", "t4", "total")

    def __init__(self, clave, nif, nombre, t1, t2, t3, t4):
        self.clave = clave
        self.nif = nif or ""
        self.nombre = nombre or ""
        self.t1 = round(float(t1 or 0), 2)
        self.t2 = round(float(t2 or 0), 2)
        self.t3 = round(float(t3 or 0), 2)
        self.t4 = round(float(t4 or 0), 2)
        self.total = round(self.t1 + self.t2 + self.t3 + self.t4, 2)

    def como_dict(self):
        return {"clave": self.clave, "nif": self.nif, "nombre": self.nombre,
                "t1": self.t1, "t2": self.t2, "t3": self.t3, "t4": self.t4, "total": self.total}


class Modelo347:
    """Operaciones con terceras personas por declarado (clave A/B) sobre el umbral."""

    def __init__(self, ejercicio, id_empresa=None, umbral=UMBRAL):
        self.ejercicio = int(ejercicio)
        self.periodo = PERIODO_ANUAL
        self.id_empresa = _emp(id_empresa)
        self.umbral = float(umbral)
        self.desde, self.hasta = _rango_periodo(ejercicio, PERIODO_ANUAL)
        self._calcular()

    def _ventas_clientes(self):
        """Operaciones con clientes (clave B) por trimestre. Importe = total (IVA incluido)."""
        q = ("SELECT cli.nif, cli.nombre, "
             " SUM(CASE WHEN MONTH(COALESCE(f.fecha_emision,f.fecha)) BETWEEN 1 AND 3 THEN f.total ELSE 0 END) t1,"
             " SUM(CASE WHEN MONTH(COALESCE(f.fecha_emision,f.fecha)) BETWEEN 4 AND 6 THEN f.total ELSE 0 END) t2,"
             " SUM(CASE WHEN MONTH(COALESCE(f.fecha_emision,f.fecha)) BETWEEN 7 AND 9 THEN f.total ELSE 0 END) t3,"
             " SUM(CASE WHEN MONTH(COALESCE(f.fecha_emision,f.fecha)) BETWEEN 10 AND 12 THEN f.total ELSE 0 END) t4 "
             "FROM facturas_cliente f JOIN clientes cli ON cli.id=f.id_cliente "
             "WHERE f.id_empresa=%s AND f.id_cliente IS NOT NULL AND f.estado<>'anulada' "
             "AND COALESCE(f.fecha_emision,f.fecha) BETWEEN %s AND %s "
             "GROUP BY f.id_cliente, cli.nif, cli.nombre")
        out = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(q, (self.id_empresa, self.desde, self.hasta))
                for r in _filas(cur):
                    out.append(Declarado(CLAVE_VENTAS, r["nif"], r["nombre"],
                                         r["t1"], r["t2"], r["t3"], r["t4"]))
        except Exception as e:
            logger.error("_ventas_clientes: %s", e)
        return out

    def _compras_proveedores(self):
        """Operaciones con proveedores (clave A) por trimestre. Importe = base + IVA."""
        q = ("SELECT p.cif_nif AS nif, p.razon_social AS nombre, "
             " SUM(CASE WHEN MONTH(f.fecha_factura) BETWEEN 1 AND 3 THEN f.base+f.iva ELSE 0 END) t1,"
             " SUM(CASE WHEN MONTH(f.fecha_factura) BETWEEN 4 AND 6 THEN f.base+f.iva ELSE 0 END) t2,"
             " SUM(CASE WHEN MONTH(f.fecha_factura) BETWEEN 7 AND 9 THEN f.base+f.iva ELSE 0 END) t3,"
             " SUM(CASE WHEN MONTH(f.fecha_factura) BETWEEN 10 AND 12 THEN f.base+f.iva ELSE 0 END) t4 "
             "FROM compras_facturas f JOIN proveedores p ON p.id_proveedor=f.id_proveedor "
             "WHERE f.id_empresa=%s AND f.fecha_factura BETWEEN %s AND %s "
             "GROUP BY f.id_proveedor, p.cif_nif, p.razon_social")
        out = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(q, (self.id_empresa, self.desde, self.hasta))
                for r in _filas(cur):
                    out.append(Declarado(CLAVE_COMPRAS, r["nif"], r["nombre"],
                                         r["t1"], r["t2"], r["t3"], r["t4"]))
        except Exception as e:
            logger.error("_compras_proveedores: %s", e)
        return out

    def _calcular(self):
        todos = self._compras_proveedores() + self._ventas_clientes()
        # Umbral legal: se declaran solo los terceros cuyo total anual supera 3.005,06 €.
        self.declarados = [d for d in todos if d.total > self.umbral]
        self.excluidos = [d for d in todos if d.total <= self.umbral]
        total = round(sum(d.total for d in self.declarados), 2)
        cas = []

        def add(c, desc, imp):
            cas.append({"casilla": c, "descripcion": desc, "importe": round(float(imp), 2)})

        add("01", "Nº de declarados (sobre umbral)", len(self.declarados))
        add("02", "Importe total de las operaciones declaradas", total)
        for d in self.declarados:
            cod = "A_OP" if d.clave == CLAVE_COMPRAS else "B_OP"
            desc = (f"{d.nif} · {d.nombre} [clave {d.clave}] "
                    f"T1={d.t1:.2f} T2={d.t2:.2f} T3={d.t3:.2f} T4={d.t4:.2f}")
            add(cod, desc, d.total)

        self._casillas = cas
        self.resultado = total
        self.sentido = "informativa"

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "umbral": self.umbral, "resultado": self.resultado, "sentido": self.sentido,
                "declarados": [d.como_dict() for d in self.declarados], "casillas": self.casillas()}


def generar(ejercicio, *, id_empresa=None, usuario=None, observaciones=None) -> dict:
    """Genera (idempotente) el Modelo 347 del ejercicio: agrupa por tercero, aplica el umbral,
    persiste la declaración (modelo=347, periodo=0A), produce el PDF y lo enlaza. No sobreescribe
    una declaración PRESENTADA."""
    id_empresa = _emp(id_empresa)
    m = Modelo347(ejercicio, id_empresa)
    did = _B.guardar_declaracion(MODELO, ejercicio, PERIODO_ANUAL, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = _D.generar_pdf(modelo=MODELO, titulo="Modelo 347 — Operaciones con terceras personas",
                         ejercicio=m.ejercicio, periodo=PERIODO_ANUAL, id_declaracion=did,
                         casillas=m.casillas(), resultado=m.resultado, sentido=m.sentido,
                         hash_doc=decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "declarados": [d.como_dict() for d in m.declarados], "casillas": m.casillas(),
            "pdf": pdf, "hash": decl.get("hash")}
