"""Utilidades de layout reutilizables (foundation) — sin dependencias de `components`.

`reflow_grid` reordena una rejilla (`QGridLayout`) colocando solo los widgets que se deben MOSTRAR,
secuencialmente y sin dejar huecos. Pensado para paneles cuyos botones se OCULTAN según la edición de
Smart Manager (verticales) o por permisos: al retirar un botón, los demás se recolocan y no queda ese
hueco vacío tan feo. Aplica a cualquier módulo (TPV, menús, dashboards…).
"""

from __future__ import annotations


def reflow_grid(grid, widgets, cols: int = 3) -> int:
    """Coloca `widgets` (los que se deben mostrar) en `grid` fila a fila, izquierda→derecha, sin huecos.

    - Vacía primero el layout (sin destruir los widgets) para poder re-fluir dinámicamente.
    - Cada widget se hace visible; los que NO estén en `widgets` deben ocultarse por el llamador
      (`w.setVisible(False)`) para que no floten sueltos.
    - Devuelve el número de filas ocupadas.
    """
    cols = max(1, int(cols))
    # 1) Sacar del layout lo que hubiera (los widgets conservan su padre; se recolocan abajo).
    while grid.count():
        grid.takeAt(0)
    # 2) Colocar secuencialmente solo los widgets pedidos.
    fila = 0
    for i, w in enumerate(widgets):
        fila, col = divmod(i, cols)
        grid.addWidget(w, fila, col)
        try:
            w.setVisible(True)
        except Exception:
            pass
    return (fila + 1) if widgets else 0
