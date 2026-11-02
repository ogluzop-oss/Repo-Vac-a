"""
Motor de rutas A* (Ajuste post-lanzamiento · Módulo 3) — extraído de `gui/ubicacion_tienda.py` para
poder calcular una ruta desde un proceso headless (REST API) sin arrastrar PyQt6.

`PathFinder` es una copia literal (sin cambios de lógica) de la clase homónima de
`gui/ubicacion_tienda.py:12420` — ya era Python/NumPy puro, sin ninguna dependencia de Qt.

`construir_matriz` reimplementa `generar_matriz_desde_vectores` + `marcar_muro_en_matriz` de ese mismo
fichero con tuplas `(x, y)` en vez de `QPointF` (la única parte que usaba Qt, y solo para leer `.x()`/
`.y()`) y con las dimensiones del plano tomadas de la imagen real (Pillow) en vez de una
`QGraphicsScene` — mismo algoritmo de rasterización, mismo resultado.
"""

import heapq
import math

import numpy as np


class PathFinder:
    """Motor de cálculo de rutas A* de alta precisión. Optimizado para evitar colisiones
    perimetrales y cortes de esquina."""

    def __init__(self, matrix):
        self.matrix = matrix
        self.rows = len(matrix)
        self.cols = len(matrix[0]) if self.rows > 0 else 0

        # Definición estática de movimientos (dr, dc, costo)
        # 4 Ortogonales (1.0) + 4 Diagonales (1.414)
        self.neighbors_config = [
            (0, 1, 1.0),
            (0, -1, 1.0),
            (1, 0, 1.0),
            (-1, 0, 1.0),
            (1, 1, 1.414),
            (1, -1, 1.414),
            (-1, 1, 1.414),
            (-1, -1, 1.414),
        ]

    def heuristic(self, a, b):
        """Heurística Octil para movimiento en 8 direcciones."""
        dy = abs(a[0] - b[0])
        dx = abs(a[1] - b[1])
        return (dx + dy) + (1.41421356 - 2) * min(dx, dy)

    def get_path(self, start, end):
        """Calcula la ruta óptima evitando colisiones y cortes de vértice."""
        try:
            start_node = (int(round(start[0])), int(round(start[1])))
            end_node = (int(round(end[0])), int(round(end[1])))
        except (TypeError, IndexError):
            return []

        if not (0 <= start_node[0] < self.rows and 0 <= start_node[1] < self.cols):
            return []
        if not (0 <= end_node[0] < self.rows and 0 <= end_node[1] < self.cols):
            return []

        if (
            self.matrix[start_node[0]][start_node[1]] == 1
            or self.matrix[end_node[0]][end_node[1]] == 1
        ):
            return []

        close_set = set()
        came_from = {}
        gscore = {start_node: 0.0}
        fscore = {start_node: self.heuristic(start_node, end_node)}
        oheap = []
        heapq.heappush(oheap, (fscore[start_node], start_node))
        open_set_hash = {start_node}

        while oheap:
            current = heapq.heappop(oheap)[1]

            if current == end_node:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                return path[::-1]

            open_set_hash.discard(current)
            close_set.add(current)

            for dr, dc, costo_paso in self.neighbors_config:
                neighbor = (current[0] + dr, current[1] + dc)

                if not (0 <= neighbor[0] < self.rows and 0 <= neighbor[1] < self.cols):
                    continue

                if self.matrix[neighbor[0]][neighbor[1]] == 1 or neighbor in close_set:
                    continue

                # Seguridad diagonal estricta: no permite "raspar" la esquina de un muro.
                # Si vas a (1,1), verifica que (0,1) y (1,0) estén libres.
                if dr != 0 and dc != 0:
                    if (self.matrix[current[0] + dr][current[1]] == 1
                            or self.matrix[current[0]][current[1] + dc] == 1):
                        continue

                tentative_g_score = gscore[current] + costo_paso

                if tentative_g_score < gscore.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    gscore[neighbor] = tentative_g_score
                    fscore[neighbor] = tentative_g_score + self.heuristic(neighbor, end_node)

                    if neighbor not in open_set_hash:
                        heapq.heappush(oheap, (fscore[neighbor], neighbor))
                        open_set_hash.add(neighbor)

        return []


def _marcar_muro(matriz, p1, p2, celda_size, radio=0):
    """Rasteriza el segmento `p1`-`p2` (tuplas `(x, y)` en píxeles del plano) en `matriz` (NumPy,
    filas=y, columnas=x). Mismo algoritmo que `marcar_muro_en_matriz` (muestreo denso: 4 muestras por
    celda), sin ninguna dependencia de Qt."""
    filas, columnas = matriz.shape
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    distancia = math.hypot(dx, dy)
    pasos = 1 if distancia == 0 else max(int(distancia / (celda_size / 4.0)), 1)

    for i in range(pasos + 1):
        t = i / pasos
        curr_x = p1[0] + dx * t
        curr_y = p1[1] + dy * t
        col = int(curr_x // celda_size)
        row = int(curr_y // celda_size)
        r_min, r_max = max(0, row - radio), min(filas, row + radio + 1)
        c_min, c_max = max(0, col - radio), min(columnas, col + radio + 1)
        if r_min < r_max and c_min < c_max:
            matriz[r_min:r_max, c_min:c_max] = 1


def construir_matriz(muros, ancho_px, alto_px, celda_size=20) -> np.ndarray:
    """Matriz de obstáculos (0=libre, 1=muro) a partir de los muros vectoriales guardados en
    `configuracion_mapa.muros_vectoriales` (lista de `{"x1","y1","x2","y2"}`) y el tamaño real del
    plano en píxeles. `radio=0` (muro fino, "preciso"): los muros vienen calibrados de BD, mismo
    criterio que usa el escritorio al cargarlos (`es_muro_preciso=True`)."""
    cols = max(1, int(ancho_px // celda_size) + 1)
    rows = max(1, int(alto_px // celda_size) + 1)
    matriz = np.zeros((rows, cols), dtype=np.uint8)
    for m in muros or []:
        try:
            p1 = (float(m["x1"]), float(m["y1"]))
            p2 = (float(m["x2"]), float(m["y2"]))
        except (KeyError, TypeError, ValueError):
            continue
        _marcar_muro(matriz, p1, p2, celda_size, radio=0)
    return matriz
