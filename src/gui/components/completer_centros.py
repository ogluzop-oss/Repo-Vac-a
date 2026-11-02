"""
Buscador en tiempo real de CENTROS de la empresa (tienda/almacén/fábrica/oficina/otro) — petición
explícita: "la interfaz de selección de centro debe incorporar obligatoriamente una barra de
búsqueda en tiempo real" para elegir CUALQUIER centro registrado (no solo tiendas) al finalizar una
producción o al registrar un movimiento en Logística. Mismo patrón que
`gui/components/completer_articulos.py` (QCompleter + QStringListModel + estilizar_completer) —
UNA sola implementación del patrón de autocompletado, reutilizada aquí para centros en vez de
artículos. Reutiliza tal cual `db.centros.listar_centros` (la ÚNICA tabla de centros físicos de la
empresa) — no se crea ningún catálogo de "destinos" paralelo.
"""

import logging

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtWidgets import QCompleter, QLineEdit

try:
    from assets.estilo_global import estilizar_completer
except Exception:  # pragma: no cover
    estilizar_completer = None

logger = logging.getLogger("gui.completer_centros")

_ICONOS_TIPO = {"tienda": "🏬", "almacen": "📦", "fabrica": "🏭", "oficina": "🏢", "otro": "📍"}


def _etiqueta_centro(c: dict) -> str:
    icono = _ICONOS_TIPO.get((c.get("tipo_centro") or "otro").lower(), "📍")
    nombre = (c.get("nombre_centro") or "").strip() or c.get("codigo_centro") or "Centro"
    municipio = (c.get("municipio") or "").strip()
    etiqueta = f"{icono} {nombre}"
    if municipio:
        etiqueta += f" — {municipio}"
    return etiqueta


def _mapa_centros(id_empresa=None) -> dict:
    """{etiqueta_mostrada: id_centro} de los centros ACTIVOS de la empresa — se reconstruye en cada
    llamada (lista pequeña, coste despreciable) para no arrastrar un mapeo obsoleto entre pantallas."""
    try:
        from src.db import centros
        return {_etiqueta_centro(c): c.get("id_centro") for c in centros.listar_centros(id_empresa)}
    except Exception as e:
        logger.error("_mapa_centros: %s", e)
        return {}


def instalar_sugerencias_centro(line_edit: QLineEdit, id_empresa=None) -> QCompleter:
    """Instala en `line_edit` el autocompletado de centros (búsqueda en tiempo real, case
    insensitive, `MatchContains` — encuentra por nombre, municipio o tipo), precargado de inmediato.
    Usa `resolver_id_centro(line_edit.text(), id_empresa)` para obtener el `id_centro` elegido."""
    completer = QCompleter()
    model = QStringListModel()
    completer.setModel(model)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    line_edit.setCompleter(completer)
    if estilizar_completer:
        estilizar_completer(completer)
    model.setStringList(sorted(_mapa_centros(id_empresa).keys()))
    return completer


def resolver_id_centro(texto: str, id_empresa=None) -> str | None:
    """`id_centro` (UUID) de la etiqueta exacta elegida por el usuario, o `None` si el texto no
    coincide con ningún centro — nunca intenta adivinar una coincidencia parcial, para no vincular un
    documento al centro equivocado."""
    texto = (texto or "").strip()
    if not texto:
        return None
    return _mapa_centros(id_empresa).get(texto)
