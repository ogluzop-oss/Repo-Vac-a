"""
Modelo 303 (IVA) completo por casillas — FASE AEAT-1.

EXTIENDE (no reescribe) src/services/contabilidad/iva.py: parte de `libro_iva` (que ya expone
`tipo_iva`, base y cuota por línea) para construir las CASILLAS oficiales del 303 en régimen
general (tipos 21/10/4). El resultado de liquidación coincide con `iva.resumen_303` (continuidad).

Arquitectura preparada para compensaciones (casilla 67), REDEME (periodos mensuales) y otros
regímenes, aunque en esta fase solo se calculan los bloques de IVA repercutido y soportado.
"""

import calendar
import logging

from src.db.conexion import EMPRESA_DEFAULT_ID
from src.services.aeat import base as _B
from src.services.contabilidad import iva as _IVA

logger = logging.getLogger("aeat.m303")

MODELO = "303"
TIPOS_GENERAL = (21.0, 10.0, 4.0)

# Casilla base/tipo/cuota por cada tipo de IVA devengado (régimen general).
_CASILLAS_DEVENGADO = {21.0: ("01", "02", "03"), 10.0: ("04", "05", "06"), 4.0: ("07", "08", "09")}


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


def periodos_validos() -> tuple:
    return ("1T", "2T", "3T", "4T") + tuple(f"{m:02d}" for m in range(1, 13)) + ("0A",)


def _rango(ejercicio, periodo):
    """(desde, hasta) ISO para el periodo: trimestre (NT), mes (NN) o anual (0A)."""
    y = int(ejercicio)
    trimestres = {"1T": (1, 3), "2T": (4, 6), "3T": (7, 9), "4T": (10, 12)}
    if periodo in trimestres:
        m1, m2 = trimestres[periodo]
    elif periodo == "0A":
        m1, m2 = 1, 12
    elif periodo.isdigit() and 1 <= int(periodo) <= 12:
        m1 = m2 = int(periodo)
    else:
        raise ValueError(f"periodo inválido: {periodo}")
    desde = f"{y}-{m1:02d}-01"
    hasta = f"{y}-{m2:02d}-{calendar.monthrange(y, m2)[1]:02d}"
    return desde, hasta


class Modelo303:
    """Modelo interno por casillas. `casillas()` → [{casilla, descripcion, importe}]."""

    def __init__(self, ejercicio, periodo, id_empresa=None):
        self.ejercicio = int(ejercicio)
        self.periodo = periodo
        self.id_empresa = _emp(id_empresa)
        self.desde, self.hasta = _rango(ejercicio, periodo)
        self._calcular()

    def _agrupa_por_tipo(self, libro):
        out = {t: {"base": 0.0, "cuota": 0.0} for t in TIPOS_GENERAL}
        for ln in libro["lineas"]:
            t = round(float(ln.get("tipo_iva") or 0), 2)
            if t in out:
                out[t]["base"] += float(ln["base"])
                out[t]["cuota"] += float(ln["cuota"])
        return out

    def _calcular(self):
        rep = _IVA.libro_iva("repercutido", self.id_empresa, self.ejercicio, self.desde, self.hasta)
        sop = _IVA.libro_iva("soportado", self.id_empresa, self.ejercicio, self.desde, self.hasta)
        self._rep, self._sop = rep, sop
        dev = self._agrupa_por_tipo(rep)
        cas = []

        def add(c, desc, imp):
            cas.append({"casilla": c, "descripcion": desc, "importe": round(float(imp), 2)})

        # IVA devengado régimen general (bloques 21/10/4).
        for tipo in TIPOS_GENERAL:
            cb, ct, cc = _CASILLAS_DEVENGADO[tipo]
            add(cb, f"Base imponible {tipo:.0f}%", dev[tipo]["base"])
            add(ct, f"Tipo {tipo:.0f}%", tipo)
            add(cc, f"Cuota {tipo:.0f}%", dev[tipo]["cuota"])
        cuota_devengada = round(rep["total_cuota"], 2)
        add("27", "Total cuota devengada", cuota_devengada)

        # IVA deducible (cuotas soportadas en operaciones interiores corrientes).
        add("28", "Base IVA deducible op. interiores corrientes", sop["total_base"])
        add("29", "Cuota IVA deducible op. interiores corrientes", sop["total_cuota"])
        total_deducir = round(sop["total_cuota"], 2)
        add("45", "Total a deducir", total_deducir)

        # Resultado.
        resultado_rg = round(cuota_devengada - total_deducir, 2)
        add("46", "Resultado régimen general", resultado_rg)
        add("64", "Suma de resultados", resultado_rg)
        add("67", "Cuotas a compensar de periodos anteriores", 0.0)   # arquitectura compensaciones
        resultado = round(resultado_rg - 0.0, 2)
        add("69", "Resultado de la liquidación", resultado)
        add("71", "Resultado de la declaración", resultado)

        self._casillas = cas
        self.resultado = resultado
        self.sentido = "a ingresar" if resultado >= 0 else "a compensar/devolver"

    def casillas(self) -> list:
        return list(self._casillas)

    def como_dict(self) -> dict:
        return {"modelo": MODELO, "ejercicio": self.ejercicio, "periodo": self.periodo,
                "desde": self.desde, "hasta": self.hasta, "resultado": self.resultado,
                "sentido": self.sentido, "casillas": self.casillas()}


def generar_pdf(modelo303: "Modelo303", id_declaracion, hash_doc, id_empresa=None) -> str | None:
    """Documento borrador PDF del 303 (delegado en el helper común aeat.documento)."""
    from src.services.aeat import documento as _D
    return _D.generar_pdf(modelo="303", titulo="Modelo 303 — IVA (borrador)",
                          ejercicio=modelo303.ejercicio, periodo=modelo303.periodo,
                          id_declaracion=id_declaracion, casillas=modelo303.casillas(),
                          resultado=modelo303.resultado, sentido=modelo303.sentido,
                          hash_doc=hash_doc, id_empresa=_emp(id_empresa))


def generar(ejercicio, periodo, *, id_empresa=None, usuario=None, observaciones=None) -> dict:
    """Genera (idempotente) el Modelo 303 del periodo: calcula casillas, persiste la declaración
    (estado GENERADO), produce el PDF borrador y lo enlaza. Devuelve {id, resultado, casillas, pdf}.
    Si ya existe PRESENTADA para la clave, no la sobreescribe."""
    id_empresa = _emp(id_empresa)
    m = Modelo303(ejercicio, periodo, id_empresa)
    did = _B.guardar_declaracion(MODELO, ejercicio, periodo, m.resultado, m.casillas(),
                                 observaciones=observaciones, usuario=usuario, id_empresa=id_empresa)
    if not did:
        return {"ok": False, "errores": "declaración ya presentada (no se sobreescribe)"}
    decl = _B.obtener_declaracion(did, id_empresa=id_empresa)
    pdf = generar_pdf(m, did, decl.get("hash"), id_empresa=id_empresa)
    if pdf:
        _B.guardar_fichero(did, pdf, id_empresa=id_empresa)
    return {"ok": True, "id": did, "resultado": m.resultado, "sentido": m.sentido,
            "casillas": m.casillas(), "pdf": pdf, "hash": decl.get("hash")}
