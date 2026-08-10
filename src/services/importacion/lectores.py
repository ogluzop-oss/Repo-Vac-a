"""
Lectores de fichero de la ingesta (Fase 1: universal). Normalizan cualquier origen soportado a una lista de
filas (dict cabecera→valor). Auto-detección de formato, codificación y separador. DEGRADABLE: usa pandas si
está (lo está), con respaldo a las librerías estándar (csv/json). Fase 3 añadirá Parquet/XML/EDIFACT.
"""

import csv
import io
import json
import logging
import os

logger = logging.getLogger("importacion.lectores")

FORMATOS = ("csv", "tsv", "txt", "xlsx", "json", "jsonl", "parquet", "xml", "edifact", "sql")

_EXT = {"csv": "csv", "tsv": "tsv", "txt": "txt", "xlsx": "xlsx", "json": "json", "jsonl": "jsonl",
        "parquet": "parquet", "pq": "parquet", "xml": "xml", "bmecat": "xml",
        "edi": "edifact", "pricat": "edifact", "edifact": "edifact", "sql": "sql", "dump": "sql"}


def detectar_formato(ruta) -> str | None:
    ext = os.path.splitext(str(ruta))[1].lower().lstrip(".")
    fmt = _EXT.get(ext)
    if fmt:
        return fmt
    # .txt puede ser en realidad un mensaje EDIFACT (empieza por UNA/UNB/UNH).
    if ext in ("", "txt", "dat"):
        try:
            with open(ruta, encoding="latin-1") as f:
                cabeza = f.read(3)
            if cabeza in ("UNA", "UNB", "UNH"):
                return "edifact"
        except Exception:
            pass
    return None


def _leer_texto(ruta) -> str:
    """Lee el fichero probando codificaciones habituales (UTF-8 con/sin BOM, Latin-1)."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(ruta, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(ruta, encoding="utf-8", errors="replace") as f:
        return f.read()


def _detectar_separador(cabecera: str) -> str:
    try:
        return csv.Sniffer().sniff(cabecera, delimiters=";,\t|").delimiter
    except Exception:
        # Heurística simple: el separador más frecuente en la cabecera.
        return max((";", ",", "\t", "|"), key=cabecera.count)


def _leer_tabular_texto(ruta) -> list[dict]:
    texto = _leer_texto(ruta)
    if not texto.strip():
        return []
    primera = texto.splitlines()[0]
    sep = _detectar_separador(primera)
    filas = list(csv.DictReader(io.StringIO(texto), delimiter=sep))
    return [{(k or "").strip(): v for k, v in fila.items()} for fila in filas]


def _leer_excel(ruta) -> list[dict]:
    try:
        import pandas as pd
    except Exception as e:
        raise RuntimeError("Falta pandas/openpyxl para leer Excel") from e
    df = pd.read_excel(ruta, dtype=object)
    df = df.where(df.notna(), None)                  # NaN → None
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict("records")


def _leer_json(ruta) -> list[dict]:
    texto = _leer_texto(ruta).strip()
    if not texto:
        return []
    try:
        data = json.loads(texto)
        if isinstance(data, dict):                   # {"productos": [...]} o un único objeto
            for v in data.values():
                if isinstance(v, list):
                    return [d for d in v if isinstance(d, dict)]
            return [data]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        pass
    filas = []                                        # JSONL (una fila por línea)
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            d = json.loads(linea)
            if isinstance(d, dict):
                filas.append(d)
        except json.JSONDecodeError:
            continue
    return filas


def _leer_parquet(ruta) -> list[dict]:
    """Parquet (gran volumen). DEGRADABLE: requiere pandas + un motor ('pyarrow' o 'fastparquet')."""
    try:
        import pandas as pd
    except Exception as e:
        raise RuntimeError("Falta pandas para leer Parquet") from e
    try:
        df = pd.read_parquet(ruta)
    except Exception as e:
        raise RuntimeError("Falta un motor Parquet (instala 'pyarrow') o el fichero no es válido: "
                           f"{e}") from e
    df = df.where(df.notna(), None)
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict("records")


def leer(ruta) -> tuple[list[dict], list[str]]:
    """Lee el fichero y devuelve (filas, columnas). Las columnas se toman de la unión de claves. Lanza
    ValueError si el formato no está soportado. Los formatos SEMÁNTICOS (BMEcat/EDIFACT) ya entregan columnas
    canónicas (codigo/nombre/precio/…), de modo que el mapeo queda casi automático."""
    fmt = detectar_formato(ruta)
    if fmt is None:
        raise ValueError("Formato no soportado (CSV/TSV/TXT, Excel, JSON/JSONL, Parquet, XML BMEcat o EDIFACT).")
    if fmt == "xlsx":
        filas = _leer_excel(ruta)
    elif fmt in ("json", "jsonl"):
        filas = _leer_json(ruta)
    elif fmt == "parquet":
        filas = _leer_parquet(ruta)
    elif fmt == "xml":
        from src.services.importacion.retail import leer_bmecat
        filas = leer_bmecat(ruta)
    elif fmt == "edifact":
        from src.services.importacion.retail import leer_edifact_pricat
        filas = leer_edifact_pricat(ruta)
    elif fmt == "sql":
        from src.services.importacion.dump_sql import leer_sql_dump
        filas = leer_sql_dump(ruta)
    else:
        filas = _leer_tabular_texto(ruta)
    columnas = []
    for fila in filas:
        for k in fila:
            if k and k not in columnas:
                columnas.append(k)
    return filas, columnas
