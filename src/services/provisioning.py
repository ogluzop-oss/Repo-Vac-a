"""
Aprovisionamiento automático de un centro nuevo (botón 🔑 en Configuración → Datos de empresa →
Centros): genera/resuelve un código corto, de un solo uso y caduco que el instalador de un
ordenador nuevo canjea (vía el endpoint público `POST /provisioning/emparejar`,
`src.api.routers.provisioning`) para recibir su `.env` completo sin tener que copiar credenciales
a mano.

Credenciales POR INSTALACIÓN (2026-11-14, cierre de brecha de seguridad — petición explícita):
cada ordenador que se empareja recibe su PROPIO usuario de MariaDB (`CREATE USER` real, ver
`crear_credencial_db`), NUNCA el usuario compartido `DB_REMOTE_USER`/`DB_REMOTE_PASSWORD`. Antes,
TODOS los ordenadores de TODAS las empresas compartían la misma credencial — si el `.env` de uno
se filtraba, solo se podía cortar rotando esa contraseña global (afectando a todo el mundo). Ahora
se puede revocar un único ordenador (`revocar_credencial_db`) sin tocar a los demás.

OJO (límite real, no resuelto por esto): el usuario nuevo tiene los MISMOS privilegios sobre TODA
`smart_manager_db` que tenía el usuario compartido — MariaDB no da aislamiento de FILAS por
empresa vía GRANT. Esto solo acota el daño de una fuga a UN ordenador revocable; no aísla los
datos entre empresas distintas a nivel de base de datos (eso exigiría que la app de escritorio
dejara de conectar directamente a la BD y hablara solo por la API).
"""

import logging
import os
import random
import secrets
import string
from datetime import datetime, timedelta

from src.db.conexion import obtener_conexion

logger = logging.getLogger("services.provisioning")

MINUTOS_EXPIRACION = 30
_ALFABETO = string.ascii_uppercase.replace("O", "").replace("I", "") + "".join(
    c for c in string.digits if c not in ("0", "1"))  # sin O/0/I/1 (confusión al dictar/teclear)

# Mismos privilegios que tenía el usuario compartido `DB_REMOTE_USER` (ver migración 0339) — un
# recorte real (p. ej. quitar CREATE/DROP/ALTER) podría romper `ensure_schema()`/migraciones que la
# propia app de escritorio aplica contra esta BD remota al arrancar.
_PRIVILEGIOS_INSTALACION = (
    "SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, REFERENCES, INDEX, ALTER, "
    "CREATE TEMPORARY TABLES, LOCK TABLES, EXECUTE"
)


def _generar_codigo(longitud=8) -> str:
    return "".join(random.choice(_ALFABETO) for _ in range(longitud))


# ── Bases de datos propias por tenant (2026-11-14, aislamiento real) ────────────────────────────
def _config_tenant(nombre_db) -> dict:
    """Mismo host/usuario/contraseña/puerto que la conexión de este proceso, apuntando a OTRA
    base de datos — el dict que espera `obtener_conexion(config=...)`."""
    from src.db.conexion import DB_CONFIG
    cfg = DB_CONFIG.copy()
    cfg["database"] = nombre_db
    return cfg


def _resolver_nombre_db(id_empresa) -> str | None:
    """`tenants_db` (base compartida) → nombre de la base física de esta empresa, o `None` si no
    tiene fila ahí (empresas de ANTES de este cambio, que siguen en la base compartida de
    siempre — comportamiento sin cambios para ellas)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre_db FROM tenants_db WHERE id_empresa=%s", (id_empresa,))
            fila = cur.fetchone()
            if not fila:
                return None
            return fila["nombre_db"] if isinstance(fila, dict) else fila[0]
    except Exception as e:
        logger.error("_resolver_nombre_db(%s): %s", id_empresa, e)
        return None


def config_tenant(id_empresa) -> dict | None:
    """Config de conexión (para `obtener_conexion`/`config=` de cualquier módulo) de la base
    PROPIA de esta empresa, o `None` si es una empresa de ANTES del aislamiento por tenant (sigue
    en la base compartida de siempre — sin cambios para ella). Envoltorio público de
    `_resolver_nombre_db`/`_config_tenant` para que otros módulos (p. ej. `services.
    alta_comercial`) no tengan que tocar los privados."""
    nombre_db = _resolver_nombre_db(id_empresa)
    return _config_tenant(nombre_db) if nombre_db else None


def aprovisionar_tenant_nuevo(nombre_empresa, email) -> dict:
    """Alta de una empresa NUEVA con su PROPIA base de datos MariaDB, aislada de verdad del resto
    de clientes (en vez de una fila más en `smart_manager_db` compartida). Devuelve
    {ok, id_empresa, id_centro, nombre_db} o {ok: False, error}.

    1. Crea la base de datos (nombre único, `sm_t_<hex>`) — `obtener_conexion()` la crea sola la
       primera vez que falla con "no existe" (auto-recovery YA construido, `db.conexion.
       obtener_conexion`/`asegurar_base_de_datos`), así que basta con aplicar el esquema completo
       contra ella para que aparezca.
    2. Aplica el esquema completo (`db.migrador.aplicar_pendientes`, las mismas ~339 migraciones
       que cualquier instalación nueva — mismo camino ya probado al arrancar `backend_central` por
       primera vez, ahora con `config=` apuntando a la base del tenant en vez de a la central).
       `backup=False`: una base recién creada no tiene nada que perder.
    3. Crea la empresa + su centro principal + sincroniza el catálogo de planes, todo con
       `config=cfg_tenant` — igual que crear cualquier empresa, solo que en su propia base. La
       SUSCRIPCIÓN (qué plan, de pago o no, activación/facturación) la crea el LLAMADOR
       (`services.alta_comercial`, que ya sabe el plan contratado y el precio real cobrado) — esta
       función solo deja el tenant listo para que ese paso pueda ejecutarse.
    4. Registra el mapeo `id_empresa -> nombre_db` en `tenants_db` (base compartida), para que el
       sitio web pueda resolver más adelante a qué base conectarse por esta empresa."""
    from src.db.centros import crear_centro
    from src.db.empresa import crear_empresa
    from src.db.migrador import aplicar_pendientes
    from src.services.saas import planes as _P

    nombre_db = f"sm_t_{secrets.token_hex(6)}"
    cfg_tenant = _config_tenant(nombre_db)

    try:
        res_mig = aplicar_pendientes(
            conexion_fn=lambda: obtener_conexion(cfg_tenant), backup=False, config=cfg_tenant)
        if res_mig.get("error"):
            logger.error("aprovisionar_tenant_nuevo: fallo aplicando esquema en %s: %s",
                        nombre_db, res_mig["error"])
            return {"ok": False, "error": "no_se_pudo_crear_base"}
    except Exception as e:
        logger.error("aprovisionar_tenant_nuevo: no se pudo crear/migrar %s: %s", nombre_db, e)
        return {"ok": False, "error": "no_se_pudo_crear_base"}

    id_empresa = crear_empresa(nombre_empresa, email_principal=email, config=cfg_tenant)
    if not id_empresa:
        return {"ok": False, "error": "no_se_pudo_crear_empresa"}
    id_centro = crear_centro(id_empresa, nombre_centro="Centro principal", es_principal=True,
                             config=cfg_tenant)
    if not id_centro:
        return {"ok": False, "error": "no_se_pudo_crear_centro"}

    _P.sincronizar_planes(config=cfg_tenant)

    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO tenants_db (id_empresa, nombre_db) VALUES (%s,%s)",
                       (id_empresa, nombre_db))
            conn.commit()
    except Exception as e:
        logger.error("aprovisionar_tenant_nuevo: no se pudo registrar tenants_db para %s: %s",
                    id_empresa, e)
        return {"ok": False, "error": "no_se_pudo_registrar_tenant"}

    logger.info("Tenant nuevo aprovisionado: empresa=%s centro=%s base=%s",
               id_empresa, id_centro, nombre_db)
    return {"ok": True, "id_empresa": id_empresa, "id_centro": id_centro, "nombre_db": nombre_db}


def generar_codigo(id_centro, id_empresa, *, creado_por=None, minutos=MINUTOS_EXPIRACION) -> dict:
    """Genera un código de un solo uso para emparejar un ordenador nuevo con `id_centro`. Devuelve
    {ok, codigo, expira} o {ok: False, error}."""
    if not id_centro or not id_empresa:
        return {"ok": False, "error": "faltan_datos"}
    expira = datetime.now() + timedelta(minutes=minutos)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            for _ in range(10):  # reintento si hay colisión de código (muy improbable, UNIQUE lo protege)
                codigo = _generar_codigo()
                try:
                    cur.execute(
                        "INSERT INTO codigos_aprovisionamiento (codigo, id_centro, id_empresa, "
                        "expira, creado_por) VALUES (%s,%s,%s,%s,%s)",
                        (codigo, id_centro, id_empresa, expira, creado_por))
                    conn.commit()
                    return {"ok": True, "codigo": codigo, "expira": expira}
                except Exception as e:
                    if "uq_codigo_aprov" in str(e) or "Duplicate" in str(e):
                        continue
                    raise
        return {"ok": False, "error": "no_se_pudo_generar"}
    except Exception as e:
        logger.error("generar_codigo(%s): %s", id_centro, e)
        return {"ok": False, "error": "error_interno"}


def resolver_codigo(codigo) -> dict:
    """Valida y CONSUME (de un solo uso) un código de aprovisionamiento. Devuelve
    {ok, id_centro, id_empresa} o {ok: False, error: 'no_encontrado'|'caducado'|'ya_usado'}."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return {"ok": False, "error": "no_encontrado"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, id_centro, id_empresa, usado, expira FROM codigos_aprovisionamiento "
                "WHERE codigo=%s", (codigo,))
            fila = cur.fetchone()
            if not fila:
                return {"ok": False, "error": "no_encontrado"}
            if isinstance(fila, dict):
                id_fila, id_centro, id_empresa, usado, expira = (
                    fila["id"], fila["id_centro"], fila["id_empresa"], fila["usado"], fila["expira"])
            else:
                id_fila, id_centro, id_empresa, usado, expira = fila
            if usado:
                return {"ok": False, "error": "ya_usado"}
            if expira and expira < datetime.now():
                return {"ok": False, "error": "caducado"}
            cur.execute(
                "UPDATE codigos_aprovisionamiento SET usado=1, usado_en=NOW() "
                "WHERE id=%s AND usado=0", (id_fila,))
            if cur.rowcount != 1:
                # Otra petición lo consumió en la misma ventana (carrera) — nunca se emparejan dos
                # equipos con el mismo código de un solo uso.
                conn.rollback()
                return {"ok": False, "error": "ya_usado"}
            conn.commit()
            return {"ok": True, "id_centro": id_centro, "id_empresa": id_empresa}
    except Exception as e:
        logger.error("resolver_codigo: %s", e)
        return {"ok": False, "error": "error_interno"}


def verificar_codigo_sin_consumir(codigo) -> dict:
    """Resuelve `id_empresa` a partir de un código de activación YA EMITIDO, SIN consumirlo
    (petición explícita, 2026-11-21 — alta del Portal Empresa B2B: una empresa que ya tiene
    suscripción contratada se identifica con el MISMO código que usó para emparejar su ordenador,
    pero ese emparejamiento es un uso COMPLETAMENTE DISTINTO de este — `resolver_codigo` es de UN
    SOLO USO y lo consumiría, dejando el código inválido para la próxima vez que un ordenador nuevo
    intente emparejarse). Por eso aquí NUNCA se marca `usado`, y se acepta el código tanto si ya
    está usado (el caso normal: la empresa ya emparejó su ordenador) como si no — solo se rechaza si
    no existe. Devuelve {ok, id_empresa} o {ok: False, error: 'no_encontrado'}."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return {"ok": False, "error": "no_encontrado"}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM codigos_aprovisionamiento WHERE codigo=%s", (codigo,))
            fila = cur.fetchone()
            if not fila:
                return {"ok": False, "error": "no_encontrado"}
            id_empresa = fila["id_empresa"] if isinstance(fila, dict) else fila[0]
            return {"ok": True, "id_empresa": id_empresa}
    except Exception as e:
        logger.error("verificar_codigo_sin_consumir: %s", e)
        return {"ok": False, "error": "error_interno"}


def crear_credencial_db(id_empresa, id_centro, *, descripcion=None, nombre_db=None) -> dict:
    """Crea un usuario de MariaDB NUEVO y EXCLUSIVO para este ordenador (nunca el compartido
    `DB_REMOTE_USER`), con privilegios SOLO sobre `nombre_db` (por defecto, `DB_NAME` — las
    empresas de ANTES del aislamiento por tenant; las nuevas pasan su PROPIA base, ver
    `aprovisionar_tenant_nuevo`/`datos_conexion`). Devuelve {ok, db_user, db_password} o
    {ok: False, error}. El `CREATE USER` usa la conexión interna del backend (`db.conexion.
    obtener_conexion`, privilegios de admin dentro de la red privada de Docker) — nunca expuesto a
    parámetros del cliente: el nombre de usuario lo genera este servidor, nunca viaja desde el
    instalador."""
    nombre_db = nombre_db or os.getenv("DB_NAME", "smart_manager_db")
    for _ in range(5):  # reintento si hay colisión de nombre de usuario (muy improbable)
        sufijo = secrets.token_hex(8)  # 16 chars hex
        db_user = f"sm_i_{sufijo}"
        db_password = secrets.token_urlsafe(24)
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                # "%%" (no "%"): pymysql aplica sustitución al-estilo-% al pasar un segundo
                # argumento de parámetros — un "%" literal sin escapar (el host comodín de
                # MariaDB) rompe esa sustitución con "unsupported format character".
                cur.execute(
                    f"CREATE USER '{db_user}'@'%%' IDENTIFIED BY %s REQUIRE SSL",
                    (db_password,))
                cur.execute(
                    f"GRANT {_PRIVILEGIOS_INSTALACION} ON `{nombre_db}`.* TO '{db_user}'@'%'")
                cur.execute("FLUSH PRIVILEGES")
                cur.execute(
                    "INSERT INTO instalaciones_db (id_empresa, id_centro, db_usuario, descripcion) "
                    "VALUES (%s,%s,%s,%s)", (id_empresa, id_centro, db_user, descripcion))
                conn.commit()
            logger.info("Credencial de instalación creada: %s (empresa=%s, centro=%s)",
                       db_user, id_empresa, id_centro)
            return {"ok": True, "db_user": db_user, "db_password": db_password}
        except Exception as e:
            if "1396" in str(e) or "already exists" in str(e) or "Duplicate" in str(e):
                continue  # colisión de nombre — reintenta con otro sufijo
            logger.error("crear_credencial_db(%s, %s): %s", id_empresa, id_centro, e)
            return {"ok": False, "error": "error_interno"}
    return {"ok": False, "error": "no_se_pudo_generar"}


def revocar_credencial_db(id_instalacion, id_empresa) -> dict:
    """Revoca (DROP USER real) la credencial de UN ordenador, sin tocar a los demás. Exige que
    `id_instalacion` pertenezca a `id_empresa` (nunca revoca la instalación de otra empresa)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT db_usuario FROM instalaciones_db WHERE id=%s AND id_empresa=%s AND revocado=0",
                (id_instalacion, id_empresa))
            fila = cur.fetchone()
            if not fila:
                return {"ok": False, "error": "no_encontrada"}
            db_user = fila["db_usuario"] if isinstance(fila, dict) else fila[0]
            cur.execute(f"DROP USER IF EXISTS '{db_user}'@'%'")
            cur.execute("FLUSH PRIVILEGES")
            cur.execute(
                "UPDATE instalaciones_db SET revocado=1, revocado_en=NOW() WHERE id=%s", (id_instalacion,))
            conn.commit()
        logger.info("Credencial de instalación revocada: id=%s empresa=%s", id_instalacion, id_empresa)
        return {"ok": True}
    except Exception as e:
        logger.error("revocar_credencial_db(%s, %s): %s", id_instalacion, id_empresa, e)
        return {"ok": False, "error": "error_interno"}


def listar_instalaciones(id_empresa) -> list:
    """Instalaciones (activas y revocadas) de una empresa, para mostrarlas en "Mi cuenta"."""
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, id_centro, descripcion, creado, ultima_conexion, revocado, revocado_en "
            "FROM instalaciones_db WHERE id_empresa=%s ORDER BY creado DESC", (id_empresa,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) if not isinstance(r, dict) else r for r in cur.fetchall()]


def datos_conexion(id_centro, id_empresa, *, host_publico=None) -> dict:
    """Construye el payload de conexión a devolver al instalador: credencial de MariaDB NUEVA Y
    EXCLUSIVA de este ordenador (`crear_credencial_db`) + código de centro + CA de TLS + URL del
    portal. `host_publico` (opcional): dominio desde el que se sirvió la petición (Flask
    `request.host`) — se reutiliza tanto para `db_host`/`portal_empleado_url` como para quedar
    coherente con el CN del certificado TLS de la base de datos, sin tener que mantener el dominio
    duplicado/hardcodeado en dos sitios. Devuelve `ok=False` si no se pudo crear la credencial —
    NUNCA cae de vuelta al usuario compartido en silencio."""
    from src.db import centros as _CTS

    # Resuelve la base física de ESTA empresa (`tenants_db`, ver `aprovisionar_tenant_nuevo`) —
    # `None` para las empresas de ANTES del aislamiento por tenant, que siguen en la compartida.
    nombre_db_tenant = _resolver_nombre_db(id_empresa)
    nombre_db = nombre_db_tenant or os.getenv("DB_NAME", "smart_manager_db")
    cfg_tenant = _config_tenant(nombre_db) if nombre_db_tenant else None

    ct = _CTS.obtener_centro(id_centro, config=cfg_tenant) or {}
    host = host_publico or os.getenv("DB_REMOTE_HOST") or "127.0.0.1"
    ca_pem = None
    # OJO: NUNCA `DB_SSL_CA` aquí — esa variable la lee también `db.conexion` para la conexión
    # INTERNA propia del backend (host="db", sin TLS hoy); si coincidiera el nombre, forzaría TLS
    # en esa conexión interna y fallaría por desajuste de hostname (el CN del certificado es el
    # dominio público, no "db"). Variable propia, exclusiva de este flujo de aprovisionamiento.
    ca_path = os.getenv("DB_REMOTE_SSL_CA")
    if ca_path and os.path.isfile(ca_path):
        try:
            with open(ca_path, encoding="utf-8") as fh:
                ca_pem = fh.read()
        except Exception as e:
            logger.warning("datos_conexion: no se pudo leer DB_SSL_CA (%s): %s", ca_path, e)

    cred = crear_credencial_db(id_empresa, id_centro, descripcion=ct.get("codigo_centro"),
                               nombre_db=nombre_db)
    if not cred.get("ok"):
        return {"ok": False, "error": cred.get("error", "error_interno")}

    return {
        "ok": True,
        "db_host": host,
        "db_port": int(os.getenv("DB_REMOTE_PORT", 3306)),
        "db_user": cred["db_user"],
        "db_password": cred["db_password"],
        "db_ssl_ca_pem": ca_pem,
        "db_name": nombre_db,
        "centro_codigo": ct.get("codigo_centro"),
        "id_empresa": id_empresa,
        "portal_empleado_url": f"https://{host}/portal/empleado" if host_publico else
                               os.getenv("PORTAL_EMPLEADO_URL", ""),
    }
