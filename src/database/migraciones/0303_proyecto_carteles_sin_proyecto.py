"""
Migración 0303 — Carteles/Folletos publicitarios dejan de requerir un proyecto Kanban.

Corrección de diseño (feedback directo del usuario): Carteles/Folletos es una rama funcional
independiente dentro del módulo Proyectos, no una característica de cada proyecto — obligar a
crear/seleccionar un proyecto Kanban solo para poder diseñar un cartel era una fricción
innecesaria. `id_proyecto` pasa de obligatorio a opcional (NULL = diseño independiente, el caso
normal desde la GUI); se conserva para quien quiera asociar manualmente un diseño a un proyecto
vía la capa de servicio.
"""

VERSION = "0303"
DESCRIPCION = "proyecto_carteles: id_proyecto pasa a opcional (diseños independientes de un proyecto)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("ALTER TABLE proyecto_carteles MODIFY COLUMN id_proyecto INT DEFAULT NULL")


def revertir(cur):
    cur.execute("UPDATE proyecto_carteles SET id_proyecto=0 WHERE id_proyecto IS NULL")
    cur.execute("ALTER TABLE proyecto_carteles MODIFY COLUMN id_proyecto INT NOT NULL")
