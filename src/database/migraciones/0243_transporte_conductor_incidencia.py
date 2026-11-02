"""
Migración 0243 — `transporte_rutas.id_conductor` (INT) + `transporte_paradas.motivo_incidencia`.

Rediseño móvil · Grupo B, módulo 5 (Transporte/Reparto): `transporte_rutas.conductor` es texto libre
(VARCHAR), sin vínculo a un id de usuario — a diferencia del `tecnico INT` de GMAO/SAT, no hay forma de
filtrar "mis rutas" desde el móvil. Se añade `id_conductor INT` (se mantiene `conductor` como nombre
mostrado, sin tocar). Además, `cerrar_ruta` ya tolera `estado='incidencia'` en `transporte_paradas` pero
ninguna función lo escribe nunca — hoy es imposible registrar que un cliente estuvo ausente o rechazó un
paquete; se añade `motivo_incidencia` para que `reportar_incidencia` (nueva) tenga dónde guardar la
razón. Aditiva/reversible, no borra datos.
"""

VERSION = "0243"
DESCRIPCION = "transporte_rutas.id_conductor (INT) + transporte_paradas.motivo_incidencia"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM transporte_rutas LIKE 'id_conductor'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE transporte_rutas ADD COLUMN id_conductor INT DEFAULT NULL")
    cur.execute("SHOW COLUMNS FROM transporte_paradas LIKE 'motivo_incidencia'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE transporte_paradas ADD COLUMN motivo_incidencia VARCHAR(255) DEFAULT NULL")


def revertir(cur):
    cur.execute("SHOW COLUMNS FROM transporte_paradas LIKE 'motivo_incidencia'")
    if cur.fetchone():
        cur.execute("ALTER TABLE transporte_paradas DROP COLUMN motivo_incidencia")
    cur.execute("SHOW COLUMNS FROM transporte_rutas LIKE 'id_conductor'")
    if cur.fetchone():
        cur.execute("ALTER TABLE transporte_rutas DROP COLUMN id_conductor")
