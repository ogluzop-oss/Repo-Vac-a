"""
Migracion 0067 — Preferencias de usuario (UX). ADITIVA, idempotente, reversible.

Almacen clave/valor por usuario para preferencias de interfaz (p. ej. sidebar colapsado).
NO toca ninguna tabla existente. Sin impacto en logica de negocio.
"""

VERSION = "0067"
DESCRIPCION = "Preferencias de usuario (clave/valor) para UX: sidebar colapsable, etc."
REVERSIBLE = True
REQUIERE_BACKUP = False

_TABLAS = [
    ("preferencias_usuario", """
        id INT AUTO_INCREMENT PRIMARY KEY,
        id_usuario INT NOT NULL,
        clave VARCHAR(80) NOT NULL,
        valor VARCHAR(255) DEFAULT NULL,
        actualizado DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_pref (id_usuario, clave)"""),
]


def aplicar(cur):
    for nombre, cols in _TABLAS:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {nombre} ({cols}) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def revertir(cur):
    for nombre, _ in reversed(_TABLAS):
        cur.execute(f"DROP TABLE IF EXISTS {nombre}")
