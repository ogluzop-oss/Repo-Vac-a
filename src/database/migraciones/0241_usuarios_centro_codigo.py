"""
Migración 0241 — Renombra `usuarios.tienda_id` a `usuarios.centro_codigo`.

`usuarios.tienda_id` nunca fue un `id_tienda` (el entero FK a `tiendas.id` que usan
`documentos_logisticos`/`ventas`/`mermas`/`esl_labels` para aislar filas por tienda) — siempre fue un
CÓDIGO DE CENTRO en texto libre (p. ej. "ALMC" para el almacén, "TND-001" para una tienda), el mismo
valor que escritorio usa como `codigo_local`/`centro_receptor`/`origen`/`destino` en logística. El
nombre parecido a la columna `id_tienda` (entera) de otras tablas indujo a confundirlos (Ajuste
post-lanzamiento · Módulo 8) — se renombra para que el esquema refleje lo que realmente es.
Aditiva/reversible: solo renombra, no cambia tipo ni datos.
"""

VERSION = "0241"
DESCRIPCION = "Renombra usuarios.tienda_id -> usuarios.centro_codigo (código de centro, no id_tienda)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    cur.execute("SHOW COLUMNS FROM usuarios LIKE 'tienda_id'")
    tiene_vieja = cur.fetchone()
    cur.execute("SHOW COLUMNS FROM usuarios LIKE 'centro_codigo'")
    tiene_nueva = cur.fetchone()
    if tiene_vieja and not tiene_nueva:
        cur.execute("ALTER TABLE usuarios CHANGE COLUMN tienda_id centro_codigo VARCHAR(50) NULL")


def revertir(cur):
    cur.execute("SHOW COLUMNS FROM usuarios LIKE 'centro_codigo'")
    tiene_nueva = cur.fetchone()
    cur.execute("SHOW COLUMNS FROM usuarios LIKE 'tienda_id'")
    tiene_vieja = cur.fetchone()
    if tiene_nueva and not tiene_vieja:
        cur.execute("ALTER TABLE usuarios CHANGE COLUMN centro_codigo tienda_id VARCHAR(50) NULL")
