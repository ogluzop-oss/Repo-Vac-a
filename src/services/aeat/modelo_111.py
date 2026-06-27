"""
Modelo 111 (Retenciones e ingresos a cuenta del IRPF) — FASE AEAT-3.

Consolida, por trimestre (o mes), las retenciones de:
  A) Rendimientos del trabajo  → rrhh_nominas (irpf_importe).
  B) Actividades profesionales → compras_facturas (retencion_importe).
Sigue el patrón de 303/390: clase por casillas, persistencia en aeat_declaraciones/_lineas,
PDF + exportación a través de la infraestructura común. Reutiliza el rango de periodo del 303.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID, obtener_conexion
from src.services.aeat import base as _B
from src.services.aeat import documento as _D
from src.services.aeat.modelo_303 import _rango as _rango_periodo

logger = logging.getLogger("aeat.m111")

MODELO = "111"
PERIODOS = ("1T", "2T", "3T", "4T") + tuple(f"{m:02d}" for m in range(1, 13))


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def periodos_validos() -> tuple:
    return PERIODOS


def _meses(periodo):
    tri = {"1T": (1, 3), "2T": (4, 6), "3T": (7, 9), "4T": (10, 12)}
    if periodo in tri:
        return tri[periodo]
    if periodo.isdigit() and 1 <= int(periodo) <= 12:
        return (int(periodo), int(periodo))
    raise ValueError(f"periodo inválido para 111: {periodo}")


class Modelo111:
    """Retenciones IRPF por casillas (trabajo + actividades profesionales)."""

    def __init__(self, ejercicio, periodo, id_empresa=None):
        self.ejercicio = int(ejercicio)
        self.periodo = periodo
        self.id_empresa = _emp(id_empresa)
        self.desde, self.hasta = _rango_periodo(ejercicio, periodo)
        self._m1, self._m2 = _meses(periodo)
        self._calcular()

    def _retenciones_trabajo(self):
        """(perceptores, percepciones, retenciones) de rrhh_nominas en el periodo."""
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(DISTINCT id_empleado), COALESCE(SUM(bruto),0), "
                    "COALESCE(SUM(irpf_importe),0) FROM rrhh_nominas "
                    "WHERE id_empresa=%s AND anio=%s AND mes BETWEEN %s AND %s",
                    (self.id_empresa, self.ejercicio, self._m1, self._m2))
                r = cur.fetchone()
                v = list(r.values()) if isinstance(r, dict) else r
                return int(v[0] or 0), round(float(v[1] or 0), 2), round(float(v[2] or 0), 2)
        except Exception as e:
            logger.error("_retenciones_trabajo: %s", e)
            return 0, 0.0, 0.0

    def _retenciones_profesionales(self):
        """(perceptores, percepciones, retenciones) de compras_facturas con retención."""
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(DISTINCT id_proveedor), COALESCE(SUM(base),0), "
                    "COALESCE(SUM(retencion_importe),0) FROM compras_facturas "
                    "WHERE id_empresa=%s AND retencion_importe>0 AND fecha_factura BETWEEN %s AND %s",
                    (self.id_empresa, self.desde, self.hasta))
                r = cur.fetchone()
                v = list(r.values()) if isinstance(r, dict) else r
                return int(v[0] or 0), round(float(v[1] or 0), 2), round(float(v[2] or 0), 2)
        except Exception as e:
            logger.error("_retenciones_profesionales: %s", e)
            return 0, 0.0, 0.0

    def _calcular(self):
        nt_per, nt_imp, nt_ret = self._retenciones_trabajo()
        pf_per, pf_imp, pf_ret = self._retenciones_profesionales()
        cas = []

        def add(c, desc, imp):
            cas.append({"casilla": c, "descripcion": desc, "importe": round(float(imp), 2)})

        # Rendimientos del trabajo.
        add("01", "Trabajo · nº perceptores", nt_per)
        add("02", "Trabajo · importe percepciones", nt_imp)
        add("03", "Trabajo · importe retenciones", nt_ret)
        # Rendimientos de actividades económicas (profesionales).
        add("04", "Actividades · nº perceptores", pf_per)
        add("05", "Actividades · importe percepciones", pf_imp)
        add("06", "Actividades · importe retenciones", pf_ret)
        # Totales.
        total_ret = round(nt_ret + pf_ret, 2)
        add("28", "Suma de retenciones e ingresos a cuenta", total_ret)
        add("30", "Resultado a ingresar", total_ret)

        self._casillas = cas
        self.resultado = total_ret
        self.sentido = "a ingresar"

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "desde": self.desde, "hasta": self.hasta, "resultado": self.resultado,
                "sentido": self.sentido, "casillas": self.casillas()}


def generar(ejercicio, periodo, *, id_empresa=None, usuario=None, observaciones=None) -> dict:
    """Genera (idempotente) el Modelo 111 del periodo: consolida retenciones de nóminas y
    profesionales, persiste la declaración, produce el PDF y lo enlaza. No sobreescribe una
    declaración PRESENTADA."""
    id_empresa = _emp(id_empresa)
    m = Modelo111(ejercicio, periodo, id_empresa)
    did = _B.guardar_declaracion(MODELO, ejercicio, periodo, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = _D.generar_pdf(modelo=MODELO, titulo="Modelo 111 — Retenciones IRPF",
                         ejercicio=m.ejercicio, periodo=periodo, id_declaracion=did,
                         casillas=m.casillas(), resultado=m.resultado, sentido=m.sentido,
                         hash_doc=decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "casillas": m.casillas(), "pdf": pdf, "hash": decl.get("hash")}
