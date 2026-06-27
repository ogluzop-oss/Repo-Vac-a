"""
Modelo 190 (Resumen anual de retenciones e ingresos a cuenta del IRPF) — FASE AEAT-4.

Consolida el EJERCICIO completo de las mismas fuentes que el 111 (rrhh_nominas + compras_facturas
con retención), pero a nivel de PERCEPTOR. Reutiliza la infraestructura común AEAT (persistencia,
estados, auditoría, PDF, exportación). Por construcción, el total anual de retenciones del 190
coincide con la suma de los cuatro 111 trimestrales del ejercicio.

Claves internas (categorías) en esta fase: TRABAJO / PROFESIONAL. Arquitectura extensible para
las claves oficiales AEAT (A/B/C/…), que NO se implementan todavía.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.aeat import base as _B
from src.services.aeat import documento as _D
from src.services.aeat.modelo_303 import _rango as _rango_periodo

logger = logging.getLogger("aeat.m190")

MODELO = "190"
PERIODO_ANUAL = "0A"
CLAVE_TRABAJO = "TRABAJO"
CLAVE_PROFESIONAL = "PROFESIONAL"


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


class Perceptor:
    """Registro anual de un perceptor: identificación, percepciones y retención."""

    __slots__ = ("clave", "nif", "nombre", "percepciones", "retenciones")

    def __init__(self, clave, nif, nombre, percepciones, retenciones):
        self.clave = clave
        self.nif = nif or ""
        self.nombre = nombre or ""
        self.percepciones = round(float(percepciones or 0), 2)
        self.retenciones = round(float(retenciones or 0), 2)

    def como_dict(self):
        return {"clave": self.clave, "nif": self.nif, "nombre": self.nombre,
                "percepciones": self.percepciones, "retenciones": self.retenciones}


class Modelo190:
    """Resumen anual por perceptor + casillas agregadas."""

    def __init__(self, ejercicio, id_empresa=None):
        self.ejercicio = int(ejercicio)
        self.periodo = PERIODO_ANUAL
        self.id_empresa = _emp(id_empresa)
        self.desde, self.hasta = _rango_periodo(ejercicio, PERIODO_ANUAL)
        self._calcular()

    def _perceptores_trabajo(self):
        out = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT e.nif, e.nombre, e.apellidos, COALESCE(SUM(n.bruto),0), "
                    "COALESCE(SUM(n.irpf_importe),0) FROM rrhh_nominas n "
                    "JOIN rrhh_empleados e ON e.id=n.id_empleado "
                    "WHERE n.id_empresa=%s AND n.anio=%s "
                    "GROUP BY n.id_empleado, e.nif, e.nombre, e.apellidos",
                    (self.id_empresa, self.ejercicio))
                for r in cur.fetchall():
                    v = list(r.values()) if isinstance(r, dict) else r
                    nombre = (f"{v[1] or ''} {v[2] or ''}").strip()
                    out.append(Perceptor(CLAVE_TRABAJO, v[0], nombre, v[3], v[4]))
        except Exception as e:
            logger.error("_perceptores_trabajo: %s", e)
        return out

    def _perceptores_profesionales(self):
        out = []
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT p.cif_nif, p.razon_social, COALESCE(SUM(f.base),0), "
                    "COALESCE(SUM(f.retencion_importe),0) FROM compras_facturas f "
                    "JOIN proveedores p ON p.id_proveedor=f.id_proveedor "
                    "WHERE f.id_empresa=%s AND f.retencion_importe>0 "
                    "AND f.fecha_factura BETWEEN %s AND %s "
                    "GROUP BY f.id_proveedor, p.cif_nif, p.razon_social",
                    (self.id_empresa, self.desde, self.hasta))
                for r in cur.fetchall():
                    v = list(r.values()) if isinstance(r, dict) else r
                    out.append(Perceptor(CLAVE_PROFESIONAL, v[0], v[1], v[2], v[3]))
        except Exception as e:
            logger.error("_perceptores_profesionales: %s", e)
        return out

    def _calcular(self):
        self.perceptores = self._perceptores_trabajo() + self._perceptores_profesionales()
        trab = [p for p in self.perceptores if p.clave == CLAVE_TRABAJO]
        prof = [p for p in self.perceptores if p.clave == CLAVE_PROFESIONAL]

        def _sum(lst, attr):
            return round(sum(getattr(p, attr) for p in lst), 2)

        t_per, t_ret = _sum(trab, "percepciones"), _sum(trab, "retenciones")
        p_per, p_ret = _sum(prof, "percepciones"), _sum(prof, "retenciones")
        cas = []

        def add(c, desc, imp):
            cas.append({"casilla": c, "descripcion": desc, "importe": round(float(imp), 2)})

        # Agregados totales.
        add("01", "Nº total de perceptores", len(self.perceptores))
        add("02", "Total percepciones íntegras", round(t_per + p_per, 2))
        add("03", "Total retenciones e ingresos a cuenta", round(t_ret + p_ret, 2))
        # Subtotales por categoría interna.
        add("T_NUM", "Trabajo · nº perceptores", len(trab))
        add("T_PER", "Trabajo · percepciones", t_per)
        add("T_RET", "Trabajo · retenciones", t_ret)
        add("P_NUM", "Profesional · nº perceptores", len(prof))
        add("P_PER", "Profesional · percepciones", p_per)
        add("P_RET", "Profesional · retenciones", p_ret)
        # Detalle por perceptor (la identificación va en la descripción; importe = retención).
        for p in self.perceptores:
            cod = "T_PERC" if p.clave == CLAVE_TRABAJO else "P_PERC"
            add(cod, f"{p.nif} · {p.nombre} (percep {p.percepciones:.2f})", p.retenciones)

        self._casillas = cas
        self.resultado = round(t_ret + p_ret, 2)
        self.sentido = "resumen anual"

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "resultado": self.resultado, "sentido": self.sentido,
                "perceptores": [p.como_dict() for p in self.perceptores],
                "casillas": self.casillas()}


def generar(ejercicio, *, id_empresa=None, usuario=None, observaciones=None) -> dict:
    """Genera (idempotente) el Modelo 190 del ejercicio: consolida perceptores, persiste la
    declaración (modelo=190, periodo=0A), produce el PDF y lo enlaza. No sobreescribe una
    declaración PRESENTADA."""
    id_empresa = _emp(id_empresa)
    m = Modelo190(ejercicio, id_empresa)
    did = _B.guardar_declaracion(MODELO, ejercicio, PERIODO_ANUAL, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = _D.generar_pdf(modelo=MODELO, titulo="Modelo 190 — Resumen anual de retenciones IRPF",
                         ejercicio=m.ejercicio, periodo=PERIODO_ANUAL, id_declaracion=did,
                         casillas=m.casillas(), resultado=m.resultado, sentido=m.sentido,
                         hash_doc=decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "perceptores": [p.como_dict() for p in m.perceptores], "casillas": m.casillas(),
            "pdf": pdf, "hash": decl.get("hash")}
