"""
Parsers de extractos bancarios (rama Tesorería, FASE 8).

Convierten el contenido de un extracto en una lista normalizada de apuntes:
    {"fecha": "YYYY-MM-DD", "importe": float(signo), "concepto": str, "referencia": str, "saldo": float|None}
Formatos soportados: CSV (flexible), Norma 43 (Cuaderno 43 AEB) y CAMT.053 (ISO 20022 XML).
Sin dependencias externas (csv y xml.etree de la stdlib).
"""

import csv as _csv
import datetime as _dt
import io
import logging
import re
import xml.etree.ElementTree as _ET

logger = logging.getLogger("extractos")

FORMATOS = ("CSV", "N43", "CAMT")


def _num(s):
    """Convierte un importe textual ('1.234,56' o '1234.56' o '-12,00') a float."""
    s = (s or "").strip()
    if not s:
        return 0.0
    s = s.replace(" ", "")
    if "," in s and "." in s:           # 1.234,56 → 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                       # 12,50 → 12.50
        s = s.replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return 0.0


# ─────────────────────────────── CSV ───────────────────────────────
_ALIAS = {
    "fecha": {"fecha", "date", "fecha_operacion", "fecha operación", "f. valor", "fecha valor"},
    "importe": {"importe", "amount", "monto", "cantidad", "import"},
    "concepto": {"concepto", "concept", "description", "descripcion", "descripción", "detalle"},
    "referencia": {"referencia", "reference", "ref", "documento"},
    "saldo": {"saldo", "balance"},
}


def _col(headers, campo):
    al = _ALIAS[campo]
    for i, h in enumerate(headers):
        if (h or "").strip().lower() in al:
            return i
    return None


def _fecha_norm(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:10]


def parse_csv(contenido: str, *, delimiter=None) -> list:
    """Parsea un CSV con cabecera. Detecta columnas por nombre (fecha/importe/concepto/...)."""
    if delimiter is None:
        muestra = contenido.splitlines()[0] if contenido.strip() else ""
        delimiter = ";" if muestra.count(";") >= muestra.count(",") else ","
    rd = list(_csv.reader(io.StringIO(contenido), delimiter=delimiter))
    if not rd:
        return []
    headers = rd[0]
    ci = {c: _col(headers, c) for c in _ALIAS}
    if ci["fecha"] is None or ci["importe"] is None:
        raise ValueError("CSV sin columnas reconocibles de fecha/importe")
    out = []
    for fila in rd[1:]:
        if not fila or all(not c.strip() for c in fila):
            continue
        def g(c):
            i = ci[c]
            return fila[i] if i is not None and i < len(fila) else ""
        out.append({"fecha": _fecha_norm(g("fecha")), "importe": _num(g("importe")),
                    "concepto": g("concepto").strip(), "referencia": g("referencia").strip(),
                    "saldo": _num(g("saldo")) if ci["saldo"] is not None else None})
    return out


# ─────────────────────────────── Norma 43 (Cuaderno 43 AEB) ───────────────────────────────
def parse_n43(contenido: str) -> list:
    """Parsea un fichero Norma 43. Lee registros 22 (movimientos) y concatena los 23
    (conceptos complementarios). Importe con signo (campo debe/haber: 1=cargo, 2=abono)."""
    out = []
    actual = None
    for linea in contenido.splitlines():
        if len(linea) < 24:
            continue
        cod = linea[:2]
        if cod == "22":
            # Cuaderno 43 AEB (posiciones 1-based): 7-12 fecha op, 13-18 fecha valor,
            # 19-20 concepto común, 21-23 propio, 24 debe/haber, 25-38 importe (14).
            f = linea[12:18]                              # fecha valor YYMMDD
            dh = linea[23:24]                             # debe/haber (1=cargo, 2=abono)
            imp = linea[24:38]                            # importe 14
            try:
                fecha = _dt.datetime.strptime(f, "%y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                fecha = f
            importe = round(int(re.sub(r"\D", "", imp) or 0) / 100.0, 2)
            if dh == "1":                                 # cargo → salida
                importe = -importe
            actual = {"fecha": fecha, "importe": importe,
                      "concepto": linea[18:20].strip(), "referencia": linea[48:60].strip(),
                      "saldo": None}
            out.append(actual)
        elif cod == "23" and actual is not None:          # concepto complementario
            extra = linea[4:].strip()
            if extra:
                actual["concepto"] = (actual["concepto"] + " " + extra).strip()
    return out


# ─────────────────────────────── CAMT.053 (ISO 20022) ───────────────────────────────
def _tag(el):
    return el.tag.split("}")[-1]


def _find(el, nombre):
    for c in el.iter():
        if _tag(c) == nombre:
            return c
    return None


def _findall(el, nombre):
    return [c for c in el.iter() if _tag(c) == nombre]


def parse_camt053(contenido: str) -> list:
    """Parsea un extracto CAMT.053 (ISO 20022). Lee cada <Ntry>: importe, signo
    (CdtDbtInd CRDT/DBIT), fecha contable y concepto (AddtlNtryInf / RmtInf)."""
    try:
        root = _ET.fromstring(contenido)
    except _ET.ParseError as e:
        raise ValueError(f"CAMT.053 no es XML válido: {e}")
    out = []
    for ntry in _findall(root, "Ntry"):
        amt_el = _find(ntry, "Amt")
        ind_el = _find(ntry, "CdtDbtInd")
        if amt_el is None or ind_el is None:
            continue
        importe = round(float(amt_el.text or 0), 2)
        if (ind_el.text or "").upper() == "DBIT":
            importe = -importe
        bookg = _find(ntry, "BookgDt")
        fecha = ""
        if bookg is not None:
            dt_el = _find(bookg, "Dt")
            if dt_el is None:
                dt_el = _find(bookg, "DtTm")
            fecha = (dt_el.text or "")[:10] if dt_el is not None else ""
        info = _find(ntry, "AddtlNtryInf")
        if info is None:
            ustrd = _find(ntry, "Ustrd")
            info = ustrd
        ref_el = _find(ntry, "AcctSvcrRef")
        out.append({"fecha": fecha, "importe": importe,
                    "concepto": (info.text.strip() if info is not None and info.text else ""),
                    "referencia": (ref_el.text.strip() if ref_el is not None and ref_el.text else ""),
                    "saldo": None})
    return out


def parsear(contenido: str, formato: str) -> list:
    """Dispatcher por formato (CSV / N43 / CAMT)."""
    f = (formato or "").upper()
    if f == "N43":
        return parse_n43(contenido)
    if f == "CAMT":
        return parse_camt053(contenido)
    return parse_csv(contenido)
