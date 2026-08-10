"""
Lector de VOLCADOS SQL (.sql de mysqldump/pg_dump) → *staging* en memoria. Parsea `CREATE TABLE` (para conocer
las columnas) e `INSERT INTO ... VALUES (...)` (para las filas) SIN EJECUTAR nada: el esquema ajeno no se toca,
solo se leen los datos. Elige la tabla más 'producto' y entrega sus filas al pipeline. stdlib, €0.

Parser pragmático: separa sentencias respetando comillas (un ';' dentro de una cadena no rompe), y valores
respetando comillas/escapes (\\' y '' y \\\\). No cubre toda la gramática SQL; suficiente para dumps estándar.
"""

import logging
import re

logger = logging.getLogger("importacion.dump_sql")

_RE_INSERT = re.compile(r"^\s*INSERT\s+(?:IGNORE\s+)?INTO\s+[`\"']?(\w+)[`\"']?\s*(\(.*?\))?\s*VALUES\s*(.+)$",
                        re.IGNORECASE | re.DOTALL)
_RE_CREATE = re.compile(r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)[`\"']?\s*\((.+)\)[^)]*$",
                        re.IGNORECASE | re.DOTALL)
_NO_COL = re.compile(r"^\s*(PRIMARY|UNIQUE|KEY|INDEX|CONSTRAINT|FOREIGN|CHECK|FULLTEXT|SPATIAL)\b", re.IGNORECASE)


def _leer_texto(ruta) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(ruta, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(ruta, encoding="utf-8", errors="replace") as f:
        return f.read()


def _sentencias(texto):
    """Divide en sentencias por ';' de nivel superior (respeta comillas)."""
    out, cur, enq, esc = [], [], None, False
    for ch in texto:
        cur.append(ch)
        if enq:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == enq:
                enq = None
        elif ch in ("'", '"'):
            enq = ch
        elif ch == ";":
            out.append("".join(cur)); cur = []
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


def _split_top(cuerpo):
    """Divide por comas de nivel superior (respeta paréntesis y comillas). Para columnas de CREATE TABLE."""
    partes, cur, prof, enq, esc = [], [], 0, None, False
    for ch in cuerpo:
        if enq:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == enq:
                enq = None
            continue
        if ch in ("'", '"'):
            enq = ch; cur.append(ch)
        elif ch == "(":
            prof += 1; cur.append(ch)
        elif ch == ")":
            prof -= 1; cur.append(ch)
        elif ch == "," and prof == 0:
            partes.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        partes.append("".join(cur))
    return partes


def _columnas_create(cuerpo):
    cols = []
    for parte in _split_top(cuerpo):
        parte = parte.strip()
        if not parte or _NO_COL.match(parte):
            continue
        m = re.match(r"[`\"']?(\w+)[`\"']?", parte)
        if m:
            cols.append(m.group(1))
    return cols


def _valores(texto):
    """Parsea la parte VALUES (t1),(t2),... → lista de filas (cada una lista de valores; NULL → None)."""
    filas, i, n = [], 0, len(texto)
    while i < n:
        while i < n and texto[i] != "(":
            i += 1
        if i >= n:
            break
        i += 1
        vals, cur, enq, esc, quoted = [], [], None, False, False
        while i < n:
            ch = texto[i]
            if enq:
                if esc:
                    cur.append(ch); esc = False
                elif ch == "\\":
                    esc = True
                elif ch == enq:
                    if i + 1 < n and texto[i + 1] == enq:      # comilla duplicada ('')
                        cur.append(enq); i += 1
                    else:
                        enq = None
                else:
                    cur.append(ch)
            elif ch in ("'", '"'):
                enq = ch; quoted = True
            elif ch == ",":
                vals.append(_val("".join(cur), quoted)); cur = []; quoted = False
            elif ch == ")":
                vals.append(_val("".join(cur), quoted)); i += 1; break
            else:
                cur.append(ch)
            i += 1
        filas.append(vals)
    return filas


def _val(bruto, quoted):
    if quoted:
        return bruto
    s = bruto.strip()
    if s.upper() == "NULL" or s == "":
        return None
    return s


def parsear_dump(ruta) -> dict:
    """Devuelve {tabla: {'columnas': [...], 'filas': [dict, ...]}} — el *staging* del volcado."""
    texto = _leer_texto(ruta)
    esquema, staging = {}, {}
    for sent in _sentencias(texto):
        mc = _RE_CREATE.match(sent)
        if mc:
            esquema[mc.group(1)] = _columnas_create(mc.group(2))
            continue
        mi = _RE_INSERT.match(sent)
        if not mi:
            continue
        tabla = mi.group(1)
        cols = None
        if mi.group(2):
            cols = [c.strip().strip("`\"'") for c in mi.group(2).strip()[1:-1].split(",")]
        cols = cols or esquema.get(tabla)
        for fila in _valores(mi.group(3)):
            if cols and len(cols) == len(fila):
                d = dict(zip(cols, fila))
            elif cols:
                d = {c: (fila[i] if i < len(fila) else None) for i, c in enumerate(cols)}
            else:
                d = {f"col{i}": v for i, v in enumerate(fila)}
            staging.setdefault(tabla, {"columnas": cols or [], "filas": []})["filas"].append(d)
    return staging


def _puntuar(columnas) -> int:
    """Cuántas columnas encajan con campos de producto (para elegir la tabla de catálogo del dump)."""
    from src.services.importacion.mapeo import sugerir_mapeo
    return len(sugerir_mapeo(list(columnas)))


def tablas_dump(ruta) -> list:
    """Nombres de tabla presentes en el volcado (para que el usuario elija en la GUI)."""
    return list(parsear_dump(ruta).keys())


def leer_sql_dump(ruta, tabla=None) -> list:
    """Filas de la tabla indicada, o de la tabla más 'producto' del volcado (mayor coincidencia de columnas)."""
    staging = parsear_dump(ruta)
    if not staging:
        return []
    if tabla and tabla in staging:
        return staging[tabla]["filas"]
    mejor = max(staging.items(),
                key=lambda kv: (_puntuar(kv[1]["columnas"] or (kv[1]["filas"][0].keys() if kv[1]["filas"] else [])),
                                len(kv[1]["filas"])))
    return mejor[1]["filas"]
