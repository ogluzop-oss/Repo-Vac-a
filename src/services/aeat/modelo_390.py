"""
Modelo 390 (Resumen anual de IVA) — FASE AEAT-2.

Se construye CONSOLIDANDO los cuatro trimestres del Modelo 303 del ejercicio (reutiliza
íntegramente `modelo_303.Modelo303`, sin recalcular ni duplicar lógica de IVA). Las casillas
anuales son la suma de las trimestrales (las casillas de "tipo %" se mantienen constantes).
Por construcción, el 390 coincide con la suma de los 303 del ejercicio.
"""

import logging

from src.db.conexion import EMPRESA_DEFAULT_ID
from src.services.aeat import base as _B
from src.services.aeat import documento as _D
from src.services.aeat.modelo_303 import Modelo303

logger = logging.getLogger("aeat.m390")

MODELO = "390"
PERIODO_ANUAL = "0A"
TRIMESTRES = ("1T", "2T", "3T", "4T")
# Casillas que representan un tipo impositivo (%) y NO se acumulan.
_CASILLAS_TIPO = {"02", "05", "08"}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


class Modelo390:
    """Resumen anual por casillas, consolidando los 4 trimestres del 303."""

    def __init__(self, ejercicio, id_empresa=None):
        self.ejercicio = int(ejercicio)
        self.periodo = PERIODO_ANUAL
        self.id_empresa = _emp(id_empresa)
        self.trimestres = list(TRIMESTRES)
        self._consolidar()

    def _consolidar(self):
        acc, orden = {}, []
        for q in TRIMESTRES:
            m = Modelo303(self.ejercicio, q, self.id_empresa)
            for c in m.casillas():
                k = c["casilla"]
                if k not in acc:
                    acc[k] = {"casilla": k, "descripcion": c["descripcion"], "importe": 0.0}
                    orden.append(k)
                if k in _CASILLAS_TIPO:
                    acc[k]["importe"] = round(float(c["importe"]), 2)         # tipo % constante
                else:
                    acc[k]["importe"] = round(acc[k]["importe"] + float(c["importe"]), 2)
        self._casillas = [acc[k] for k in orden]
        self.resultado = round(acc.get("71", {}).get("importe", 0.0), 2)
        self.sentido = "a ingresar" if self.resultado >= 0 else "a compensar/devolver"

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "trimestres": self.trimestres, "resultado": self.resultado,
                "sentido": self.sentido, "casillas": self.casillas()}


def generar(ejercicio, *, id_empresa=None, usuario=None, observaciones=None) -> dict:
    """Genera (idempotente) el Modelo 390 del ejercicio: consolida los 303, persiste la
    declaración (modelo=390, periodo=0A), produce el PDF anual y lo enlaza. Si ya está
    PRESENTADA no se sobreescribe."""
    id_empresa = _emp(id_empresa)
    m = Modelo390(ejercicio, id_empresa)
    did = _B.guardar_declaracion(MODELO, ejercicio, PERIODO_ANUAL, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = _D.generar_pdf(modelo=MODELO, titulo="Modelo 390 — Resumen anual IVA",
                         ejercicio=m.ejercicio, periodo=PERIODO_ANUAL, id_declaracion=did,
                         casillas=m.casillas(), resultado=m.resultado, sentido=m.sentido,
                         hash_doc=decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "casillas": m.casillas(), "pdf": pdf, "hash": decl.get("hash"),
            "trimestres": m.trimestres}
