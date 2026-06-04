"""
Compatibilidad de Pillow para librerías que usan la API antigua de fuentes.

Pillow ≥ 10 eliminó `ImageFont.FreeTypeFont.getsize()` / `getsize_multiline()`,
que algunas dependencias (p. ej. `python-barcode` → `ImageWriter`) siguen
llamando, provocando:
    AttributeError: 'FreeTypeFont' object has no attribute 'getsize'

Este módulo re-implementa esos métodos a partir de `getbbox()`/`getmetrics()`
si no existen. Importarlo una vez al arranque (lo hace `src/main.py`) basta.
Es inocuo en versiones antiguas de Pillow (no sobrescribe si ya existen).
"""

try:
    from PIL import ImageFont

    _FF = ImageFont.FreeTypeFont

    if not hasattr(_FF, "getsize"):
        def _getsize(self, text, *args, **kwargs):
            try:
                left, top, right, bottom = self.getbbox(text)
                return (right - left, bottom - top)
            except Exception:
                # Último recurso: ancho por longitud + alto por métricas.
                try:
                    asc, desc = self.getmetrics()
                    return (int(self.getlength(text)), asc + desc)
                except Exception:
                    return (0, 0)

        _FF.getsize = _getsize

    if not hasattr(_FF, "getsize_multiline"):
        def _getsize_multiline(self, text, direction=None, spacing=4,
                               features=None, language=None, *args, **kwargs):
            lines = (text or "").split("\n")
            widths, total_h = [], 0
            for ln in lines:
                w, h = self.getsize(ln)
                widths.append(w)
                total_h += h + spacing
            total_h = max(0, total_h - spacing)
            return (max(widths) if widths else 0, total_h)

        _FF.getsize_multiline = _getsize_multiline
except Exception:
    # Si Pillow no está disponible, no hacemos nada (la app degrada por su cuenta).
    pass
