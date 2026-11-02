"""
Migración 0263 — Backfill: centros `tipo_centro='tienda'` huérfanos reciben su tienda real.

Antes de esta migración, "Centros de empresa" (`gui/gestion_usuarios.py`) podía crear un centro
`tipo_centro='tienda'` SIN crear (ni vincular) una fila real en `tiendas` — el formulario genérico
(`_FormDialogCorp`/`_CAMPOS_CT`) no tenía forma de escribir `centros_trabajo.id_tienda`. Un centro así
queda con `id_tienda IS NULL` y NUNCA puede activarse desde "Cambiar de Centro"
(`gui/selector_tienda.py::SelectorCentroDialog._elegir` exige `id_tienda`), dejando inalcanzables
funciones que dependen de una tienda conectada (p. ej. "Entrar al portal B2B"). Caso real detectado:
el centro "Kik Vic" (`codigo_centro='CDT-002'`).

El fix de raíz (mismo día) hace que `gui/gestion_usuarios.py::_de_add_centro` AUTO-PROVISIONE la
tienda real en el momento de crear el centro (vía `db/tiendas.py::crear_tienda`, nueva), así que este
caso ya no puede volver a producirse para centros NUEVOS. Esta migración es el backfill de DATOS para
los centros que quedaron huérfanos ANTES de ese fix: por cada `centros_trabajo` con
`tipo_centro='tienda' AND id_tienda IS NULL`, crea una tienda real (mismo criterio de identidad que
`crear_tienda`: reutiliza el propio nombre/código del centro, nunca inventa uno desconectado) y enlaza
`centros_trabajo.id_tienda` a ella.

ADITIVA sobre datos (no toca esquema), IDEMPOTENTE: una segunda ejecución no encuentra ya ningún
centro `tienda` con `id_tienda IS NULL` (o, tras un `revertir`, reutiliza la MISMA tienda que ya había
creado — ver `_tienda_ya_provisionada`, no duplica altas).

Reversibilidad (DATA migration — más blanda que una migración de esquema, a propósito, ver discusión
en el código de `revertir` más abajo): `revertir` SOLO deshace el ENLACE (`id_tienda` -> NULL) de los
centros cuya tienda vinculada lleva la "firma" de esta migración (`tiendas.codigo_tienda` idéntico al
propio `centros_trabajo.codigo_centro` del centro — nadie más produce esa coincidencia: las tiendas
sembradas usan `TND-NNN`, y un enlace manual anterior a una tienda YA existente apuntaría a un código
`TND-NNN` distinto del código del centro). Las filas de `tiendas` creadas NO se borran: para cuando
existe este backfill, la tienda ya puede tener almacén/stock/pedidos/auditoría colgando de su `id`
(vía `stock_almacen.ensure_almacenes_empresa`, `tiendas_db.cambiar_contexto_tienda`, etc.) — borrarla
sería una operación destructiva e insegura para una migración reversible por defecto. Full reversión
de los DATOS (borrar la tienda creada) no es el objetivo de esta migración; sí lo es poder deshacer el
ENLACE de forma segura, que es lo único que `aplicar` puede garantizar que no tiene efectos colaterales
en otras tablas.
"""

VERSION = "0263"
DESCRIPCION = "Backfill: centros tipo_centro='tienda' con id_tienda NULL reciben una tienda real vinculada"
REVERSIBLE = True
REQUIERE_BACKUP = True


def _centros_huerfanos(cur):
    cur.execute(
        "SELECT id_centro, id_empresa, codigo_centro, nombre_centro FROM centros_trabajo "
        "WHERE tipo_centro='tienda' AND id_tienda IS NULL")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) if not isinstance(row, dict) else row for row in cur.fetchall()]


def _tienda_ya_provisionada(cur, id_empresa, codigo_centro):
    """Idempotencia: si una ejecución previa (o un `revertir` que solo desenlazó) ya creó la tienda
    de este centro, la reutiliza en vez de duplicar el alta — misma firma que usa `revertir` para
    identificar sus propios enlaces (`tiendas.codigo_tienda == centros_trabajo.codigo_centro`)."""
    cur.execute(
        "SELECT id FROM tiendas WHERE id_empresa=%s AND codigo_tienda=%s LIMIT 1",
        (id_empresa, codigo_centro))
    r = cur.fetchone()
    return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None


def _nombre_libre(cur, nombre, codigo):
    """`tiendas.nombre` es UNIQUE GLOBAL (bootstrap_mariadb.sql). Mismo criterio defensivo que
    `db/tiendas.py::crear_tienda`: si el nombre ya existe, se sufija con el propio código del centro
    en vez de inventar un nombre irreconocible."""
    cur.execute("SELECT COUNT(*) FROM tiendas WHERE nombre=%s", (nombre,))
    r = cur.fetchone()
    existe = (r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0
    return f"{nombre} ({codigo})" if existe else nombre


def aplicar(cur):
    for ct in _centros_huerfanos(cur):
        id_empresa = ct.get("id_empresa")
        codigo = ct.get("codigo_centro") or ""
        nombre = (ct.get("nombre_centro") or "").strip() or f"CENTRO {codigo}".strip()
        if not codigo:
            # Salvaguarda: sin código propio no hay firma estable que reutilizar/revertir con
            # seguridad — no debería ocurrir (codigo_centro es NOT NULL, ver db/centros.py), pero
            # nunca se inventa uno aquí.
            continue
        id_tienda = _tienda_ya_provisionada(cur, id_empresa, codigo)
        if not id_tienda:
            nombre_final = _nombre_libre(cur, nombre, codigo)
            cur.execute(
                "INSERT INTO tiendas (nombre, activo, id_empresa, codigo_tienda) "
                "VALUES (%s,1,%s,%s)",
                (nombre_final, id_empresa, codigo))
            id_tienda = cur.lastrowid
        cur.execute(
            "UPDATE centros_trabajo SET id_tienda=%s WHERE id_centro=%s",
            (id_tienda, ct.get("id_centro")))


def revertir(cur):
    """Deshace SOLO el enlace (`id_tienda` -> NULL) de los centros cuya tienda vinculada lleva la
    firma de esta migración (`tiendas.codigo_tienda == centros_trabajo.codigo_centro`). No borra la
    fila de `tiendas` creada por `aplicar` (ver razonamiento en el docstring del módulo) — un
    `aplicar` posterior la reencuentra por esa misma firma (`_tienda_ya_provisionada`) y solo
    reconstruye el enlace, sin duplicar el alta.

    Caveat aceptado a propósito: el auto-provisioning en vivo (`gui/gestion_usuarios.py::
    _de_add_centro` -> `db/tiendas.py::crear_tienda`) usa la MISMA firma (reutiliza el código del
    propio centro) para que un centro creado por la migración y uno creado por el flujo normal sean
    indistinguibles (ver CLAUDE.md, "no debe haber distinción visual entre estilo antiguo y nuevo").
    Por tanto, ejecutar `revertir` de esta migración DESPUÉS de que existan centros 'tienda'
    auto-provisionados por el flujo normal desenlazaría también esos — mismo riesgo que cualquier
    downgrade de una migración de datos aplicado fuera de su ventana natural (justo al desplegar el
    fix). No se intenta diferenciar el origen aquí: ambos casos son, por diseño, la misma cosa."""
    cur.execute(
        "UPDATE centros_trabajo ct "
        "JOIN tiendas t ON t.id = ct.id_tienda "
        "SET ct.id_tienda = NULL "
        "WHERE ct.tipo_centro='tienda' AND t.codigo_tienda = ct.codigo_centro")
