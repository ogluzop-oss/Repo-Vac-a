"""
Lookup de destinatarios para los campos Para/CC/Cco de circulares y encuestas internas.

Tres fuentes, todas tenant-safe por construcción (siempre filtran por `id_empresa`, nunca devuelven
nada de otra empresa) y todas DISTINTAS del Servicio Corporativo de Resolución de Destinatarios
genérico (`services/destinatarios`), que además resuelve clientes/proveedores/leads — fuera de
dominio para la mayoría de los casos de uso de circulares/encuestas:

  · `listar_usuarios_empresa` — usuarios INTERNOS (empleados) de la empresa. Desde la migración 0287
    (`usuarios.email`), el destinatario interno se identifica/inserta por EMAIL, no por nombre de
    usuario: un empleado SIN email no es sugerido (no puede recibir un correo real si algún día se
    reenvía fuera, y mantiene un único criterio con los otros dos orígenes, que también son email).
  · `listar_centros_empresa` — EMAILS de centro de trabajo (`centros_trabajo.email`): elegir uno
    difunde el mensaje a TODOS los empleados activos vinculados a ese centro (fan-out, ver
    `circulares.py`/`encuestas.py::expandir_destinatarios`).
  · `listar_contactos_externos` — contactos FUERA del ERP (clientes/proveedores/leads) a los que esta
    empresa YA ha escrito antes. Reutiliza el histórico tenant-safe de `services.destinatarios.
    historico` (aprendizaje de envíos reales) — NUNCA el directorio completo de clientes/proveedores/
    leads: "nunca filtrar información ENTRE empresas" no equivale a "nunca permitir escribir a nadie
    externo", pero tampoco a exponer aquí el CRM completo de la empresa.

Aislamiento multiempresa: ninguna de las tres funciones devuelve NADA sin un `id_empresa` válido.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("comunicacion_interna.usuarios_internos")


def _conn():
    from src.db.conexion import obtener_conexion
    return obtener_conexion()


def listar_usuarios_empresa(id_empresa=None, texto="", *, excluir_id=None, limite=15) -> list[dict]:
    """Empleados ACTIVOS y CON EMAIL de la empresa `id_empresa`, opcionalmente filtrados por `texto`
    (contra email como criterio principal, nombre como secundario — así escribir un nombre sigue
    encontrando a la persona). Un empleado sin email NUNCA se sugiere (comportamiento deliberado:
    necesita un email en ficha para ser destinatario válido de circulares/encuestas, ver migración
    0287 y `gui/gestion_usuarios.py`).

    Aislamiento estricto: sin `id_empresa` no se devuelve NADA (nunca una lista "de todos"). Devuelve
    [{"id":, "nombre":, "email":, "centro":}, ...] — `centro` (nombre del centro de trabajo vinculado,
    o None) es informativo, para el tooltip del chip en la GUI (ver `circulares_gui.py`)."""
    if not id_empresa:
        return []
    texto = (texto or "").strip()
    try:
        with _conn() as conn, conn.cursor() as cur:
            cond = ["u.id_empresa=%s", "u.activo=1", "u.email IS NOT NULL", "u.email<>''"]
            params = [id_empresa]
            if texto:
                cond.append("(u.email LIKE %s OR u.nombre LIKE %s)")
                params += [f"%{texto}%", f"%{texto}%"]
            if excluir_id is not None:
                cond.append("u.id != %s")
                params.append(excluir_id)
            where = " AND ".join(cond)
            params.append(int(limite) if limite else 15)
            cur.execute(
                "SELECT u.id, u.nombre, u.email, c.nombre_centro FROM usuarios u "
                "LEFT JOIN centros_trabajo c ON c.codigo_centro=u.centro_codigo "
                f"AND c.id_empresa=u.id_empresa WHERE {where} ORDER BY u.nombre ASC LIMIT %s",
                tuple(params))
            return [{"id": r[0], "nombre": r[1], "email": r[2], "centro": r[3]}
                    for r in cur.fetchall()]
    except Exception as e:
        logger.debug(f"listar_usuarios_empresa degradado: {e}")
        return []


def listar_centros_empresa(id_empresa=None, texto="", *, limite=10) -> list[dict]:
    """Centros de trabajo de la empresa CON EMAIL configurado (sin él, no tiene sentido como
    destinatario de difusión), activos y no archivados. Seleccionar uno en la GUI difunde el mensaje
    a TODOS los empleados activos vinculados (fan-out por `usuarios.centro_codigo = centros_trabajo.
    codigo_centro`, ver `circulares.py`/`encuestas.py::expandir_destinatarios`).

    Aislamiento estricto: sin `id_empresa` no se devuelve NADA. Devuelve
    [{"centro_codigo":, "nombre":, "email":}, ...]."""
    if not id_empresa:
        return []
    texto = (texto or "").strip()
    try:
        with _conn() as conn, conn.cursor() as cur:
            cond = ["id_empresa=%s", "email IS NOT NULL", "email<>''",
                    "(estado IS NULL OR estado<>'baja')", "(archivado IS NULL OR archivado=0)"]
            params = [id_empresa]
            if texto:
                cond.append("(nombre_centro LIKE %s OR email LIKE %s)")
                params += [f"%{texto}%", f"%{texto}%"]
            where = " AND ".join(cond)
            params.append(int(limite) if limite else 10)
            cur.execute(
                f"SELECT codigo_centro, nombre_centro, email FROM centros_trabajo WHERE {where} "
                f"ORDER BY nombre_centro ASC LIMIT %s", tuple(params))
            return [{"centro_codigo": r[0], "nombre": r[1], "email": r[2]} for r in cur.fetchall()]
    except Exception as e:
        logger.debug(f"listar_centros_empresa degradado: {e}")
        return []


def listar_contactos_externos(id_empresa=None, id_usuario=None, texto="", *, limite=10) -> list[dict]:
    """Contactos EXTERNOS (clientes/proveedores/leads/cualquier correo) a los que esta empresa YA ha
    escrito antes, vía el histórico tenant-safe de `services.destinatarios.historico` — NUNCA el
    directorio completo de clientes/proveedores/leads (`destinatarios.servicio.buscar_destinatarios`),
    que es un origen de datos distinto y fuera de alcance aquí.

    Aislamiento: `historico.listar_historico` ya filtra por `id_empresa` (sin él, no devuelve nada).
    Devuelve [{"email":, "nombre":}, ...]."""
    if not id_empresa:
        return []
    texto = (texto or "").strip().lower()
    try:
        from src.services.destinatarios import historico
        filas = historico.listar_historico(id_empresa, id_usuario)
    except Exception as e:
        logger.debug(f"listar_contactos_externos degradado: {e}")
        return []
    salida = []
    for f in filas:
        correo = (f.get("correo") or "").strip()
        nombre = f.get("nombre_mostrado") or ""
        if not correo:
            continue
        if texto and texto not in correo.lower() and texto not in nombre.lower():
            continue
        salida.append({"email": correo, "nombre": nombre})
        if len(salida) >= limite:
            break
    return salida


def expandir_destinatarios(cur, id_empresa, destinatarios) -> tuple[list[dict], list[dict]]:
    """Separa `destinatarios` (mezcla de 3 formas: `{"usuario_id":...}` interno ya resuelto,
    `{"centro_codigo":...}` centro a difundir, `{"email_externo":...,"nombre":...}` contacto externo)
    en `(usuario_entries, externo_entries)`:

      · `usuario_entries` = entradas `usuario_id` ORIGINALES + las que resultan de expandir cada
        `centro_codigo` a TODOS los empleados activos de ESE centro, EN ESTA empresa (fan-out). Pasan
        aún por `filtrar_destinatarios_de_empresa` después (el llamador no cambia esa frontera).
      · `externo_entries` = las entradas `email_externo`, intactas (no son usuario_id-addressable,
        no generan fila en `com_destinatarios` — ver `circulares.py`/`encuestas.py`).

    Frontera de seguridad real para el fan-out: un `centro_codigo` que no pertenece a `id_empresa`
    JAMÁS se expande (se descarta en silencio, igual que un `usuario_id` ajeno se descarta en
    `filtrar_destinatarios_de_empresa`) — nunca se confía en que la GUI ya solo ofreció centros de la
    empresa activa. Usa el cursor/transacción YA ABIERTA por el llamador."""
    usuario_entries: list[dict] = []
    externo_entries: list[dict] = []
    centros_tipo: dict[str, str] = {}
    for d in (destinatarios or []):
        if d.get("usuario_id") is not None:
            usuario_entries.append(d)
        elif d.get("centro_codigo"):
            centros_tipo.setdefault(d["centro_codigo"], (d.get("tipo") or "PARA").upper())
        elif (d.get("email_externo") or "").strip():
            externo_entries.append(d)
    if centros_tipo and id_empresa:
        marcadores = ",".join(["%s"] * len(centros_tipo))
        cur.execute(
            f"SELECT codigo_centro FROM centros_trabajo WHERE id_empresa=%s "
            f"AND codigo_centro IN ({marcadores})",
            tuple([id_empresa] + list(centros_tipo.keys())))
        centros_validos = {r[0] for r in cur.fetchall()}
        for codigo, tipo in centros_tipo.items():
            if codigo not in centros_validos:
                continue
            cur.execute(
                "SELECT id FROM usuarios WHERE id_empresa=%s AND centro_codigo=%s AND activo=1",
                (id_empresa, codigo))
            for r in cur.fetchall():
                usuario_entries.append({"usuario_id": r[0], "tipo": tipo})
    return usuario_entries, externo_entries


def filtrar_destinatarios_de_empresa(cur, id_empresa, destinatarios) -> list[dict]:
    """Filtra `destinatarios` ([{"usuario_id":int, ...}]) a SOLO aquellos cuyo `usuario_id`
    pertenece REALMENTE a `id_empresa` (activo=1). Frontera de seguridad real: la GUI ya ofrece
    únicamente usuarios de la empresa activa (vía `listar_usuarios_empresa`), pero esta función es
    la que de verdad impide que un `usuario_id` de otra empresa (por un bug en la GUI, o por venir
    de cualquier otro llamador que no sea la GUI) acabe insertado en `com_destinatarios` — la capa
    de servicio es la frontera de aislamiento real, nunca solo la interfaz. Usa el cursor/
    transacción YA ABIERTA por el llamador; sin `id_empresa` o sin ids, devuelve []."""
    ids = [d.get("usuario_id") for d in (destinatarios or []) if d.get("usuario_id") is not None]
    if not ids or not id_empresa:
        return []
    marcadores = ",".join(["%s"] * len(ids))
    cur.execute(
        f"SELECT id FROM usuarios WHERE id IN ({marcadores}) AND id_empresa=%s AND activo=1",
        tuple(ids) + (id_empresa,))
    validos = {r[0] for r in cur.fetchall()}
    return [d for d in destinatarios if d.get("usuario_id") in validos]


def insertar_destinatarios(cur, tipo_entidad, id_entidad, destinatarios, *, reenviado_por=None):
    """Inserta una fila `com_destinatarios` por entrada de `destinatarios`
    (= [{"usuario_id":int, "tipo":"PARA"|"CC"|"CCO", "nombre":str?}, ...]), usando el cursor/
    transacción YA ABIERTA por el llamador (atómico junto con el resto de la operación).

    Resuelve `usuario_nombre` con una única consulta extra para las entradas que no lo traen ya
    (el llamador puede incluirlo si ya lo tiene, p. ej. desde la GUI, para evitar ese round-trip)."""
    faltan_nombre = [d["usuario_id"] for d in destinatarios if not d.get("nombre")
                     and d.get("usuario_id") is not None]
    nombres = {}
    if faltan_nombre:
        marcadores = ",".join(["%s"] * len(faltan_nombre))
        cur.execute(f"SELECT id, nombre FROM usuarios WHERE id IN ({marcadores})",
                    tuple(faltan_nombre))
        nombres = {r[0]: r[1] for r in cur.fetchall()}
    for d in destinatarios:
        uid = d.get("usuario_id")
        if uid is None:
            continue
        nombre = d.get("nombre") or nombres.get(uid)
        tipo = (d.get("tipo") or "PARA").upper()
        cur.execute(
            "INSERT INTO com_destinatarios "
            "(tipo_entidad, id_entidad, usuario_id, usuario_nombre, tipo, reenviado_por) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (tipo_entidad, id_entidad, uid, nombre, tipo, reenviado_por))
