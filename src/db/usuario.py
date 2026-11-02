import hashlib
import logging
import os
from datetime import datetime

from src.seguridad import passwords as _pw

from .conexion import obtener_conexion

logger = logging.getLogger("usuario_db")


# ============================================================
# BLOQUE AUTENTICACIÓN Y SESIÓN
# ============================================================

def encriptar_password(password: str) -> str:
    """Hash de una contraseña (Argon2id). Mantiene el nombre por compatibilidad;
    los hashes antiguos SHA-256 se siguen validando y se migran en el login."""
    return _pw.hash_password(password)


def _hash_sha256_legado(password: str) -> str:
    """Solo para utilidades que aún comparan por igualdad (uso interno)."""
    return hashlib.sha256(password.encode()).hexdigest()


def _rehash(id_usuario, hash_nuevo):
    """Persiste un hash re-generado (migración transparente a Argon2id)."""
    if not hash_nuevo:
        return
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET password=%s WHERE id=%s", (hash_nuevo, id_usuario))
            conn.commit()
        logger.info("Contraseña migrada a Argon2id (usuario id=%s).", id_usuario)
    except Exception as e:
        logger.debug("No se pudo rehashear (id=%s): %s", id_usuario, e)


def _columnas_usuarios(cur):
    cur.execute("SHOW COLUMNS FROM usuarios")
    return [c["Field"] if isinstance(c, dict) else c[0] for c in cur.fetchall()]


# Bloqueo por intentos fallidos (C1.3): tras 5 fallos, bloqueo escalado.
_MAX_INTENTOS = 5


def legacy_profile_login_habilitado() -> bool:
    """E1.2 — El login por PERFIL con contraseña COMPARTIDA queda como modo LEGACY,
    DESACTIVADO por defecto. Solo se habilita explícitamente con la variable de
    entorno SMART_MANAGER_LEGACY_PROFILE_LOGIN. El sistema oficial es el login
    nominal por usuario (`validar_login_usuario`)."""
    return os.getenv("SMART_MANAGER_LEGACY_PROFILE_LOGIN", "").strip().lower() in (
        "1", "true", "yes", "si", "sí", "on")


def _bloqueo_minutos(intentos: int) -> int:
    if intentos < _MAX_INTENTOS:
        return 0
    return {0: 1, 1: 5}.get(intentos - _MAX_INTENTOS, 15)


def _esta_bloqueado(bloqueado_hasta) -> bool:
    return bloqueado_hasta is not None and bloqueado_hasta > datetime.now()


def _registrar_exito(uid):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL, "
                        "ultimo_login=NOW() WHERE id=%s", (uid,))
            conn.commit()
    except Exception as e:
        logger.debug("registrar_exito(%s): %s", uid, e)


def _registrar_fallo(uid, intentos_actuales):
    try:
        n = int(intentos_actuales or 0) + 1
        mins = _bloqueo_minutos(n)
        with obtener_conexion() as conn, conn.cursor() as cur:
            if mins:
                cur.execute("UPDATE usuarios SET intentos_fallidos=%s, "
                            "bloqueado_hasta=DATE_ADD(NOW(), INTERVAL %s MINUTE) WHERE id=%s",
                            (n, mins, uid))
            else:
                cur.execute("UPDATE usuarios SET intentos_fallidos=%s WHERE id=%s", (n, uid))
            conn.commit()
        if mins:
            # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
            try:
                from src.services import eventos as _EV
                _EV.publicar("USUARIO_BLOQUEADO", origen="seguridad", ref_entidad="usuario",
                             ref_id=uid, payload={"intentos_fallidos": n, "bloqueo_minutos": mins})
            except Exception:
                pass
    except Exception as e:
        logger.debug("registrar_fallo(%s): %s", uid, e)


def _autenticar(filas_cols, filas, password):
    """Lógica común: verifica candidatos saltando los bloqueados, rehashea al
    acierto, registra éxito/fallo. Devuelve (dict_usuario|None, hubo_bloqueado)."""
    candidatos = [dict(zip(filas_cols, f)) for f in filas]
    hubo_bloqueado = False
    activos = []
    for d in candidatos:
        if _esta_bloqueado(d.get("bloqueado_hasta")):
            hubo_bloqueado = True
            continue
        activos.append(d)
    for d in activos:
        ok, nuevo = _pw.verificar(password, d.get("password"))
        if ok:
            _rehash(d["id"], nuevo)
            _registrar_exito(d["id"])
            return d, hubo_bloqueado
    for d in activos:                       # contraseña incorrecta: cuenta el fallo
        _registrar_fallo(d["id"], d.get("intentos_fallidos"))
    return None, hubo_bloqueado


def validar_login(perfil_ui, password):
    """[LEGACY/DEPRECADO] Login por PERFIL con contraseña COMPARTIDA por rol.

    E1.2: aislado como modo legacy explícito y **DESACTIVADO por defecto**. Ninguna
    ruta normal de autenticación lo usa (el flujo oficial es `validar_login_usuario`,
    nominal por usuario). Solo opera si `SMART_MANAGER_LEGACY_PROFILE_LOGIN` está
    activado; en caso contrario devuelve None sin autenticar."""
    if not legacy_profile_login_habilitado():
        logger.warning("Login por PERFIL (contraseña compartida) DESACTIVADO (modo legacy). "
                       "Use login nominal por usuario (validar_login_usuario).")
        return None
    valor_busqueda = perfil_ui.strip().upper()
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_usuario = "nombre" if "nombre" in columnas else "usuario"
                tiene_emp = "id_empresa" in columnas
                cols = ["id", col_usuario, "perfil", "centro_codigo", "password",
                        "intentos_fallidos", "bloqueado_hasta"]
                if tiene_emp:
                    cols.append("id_empresa")
                cur.execute(
                    f"SELECT {', '.join(cols)} FROM usuarios WHERE UPPER(perfil) = %s",
                    (valor_busqueda,))
                filas = cur.fetchall()
            d, bloqueado = _autenticar(cols, filas, password)
            if d:
                logger.info(f"Acceso concedido para perfil: {valor_busqueda}")
                return {"id": d["id"], "nombre": d[col_usuario], "perfil": d["perfil"],
                        "centro_codigo": d["centro_codigo"],
                        "id_empresa": d.get("id_empresa") if tiene_emp else None}
            if bloqueado:
                logger.warning(f"Acceso bloqueado temporalmente para perfil: {valor_busqueda}")
            else:
                logger.warning(f"Intento de login fallido para: {valor_busqueda}")
            return None
    except Exception as e:
        logger.error(f"Error crítico en validación: {e}")
        return None


def validar_login_empleado(nombre: str, password: str) -> dict | None:
    """Valida credenciales por nombre individual de empleado (para TPV). Soporte
    dual Argon2id/SHA-256 con rehash en el primer acierto.

    Aislamiento por tenant: si la tabla tiene `id_empresa`, la búsqueda se restringe a la
    empresa ACTIVA (`empresa_actual_id()`) — antes buscaba por nombre en TODA la tabla sin
    filtrar empresa, permitiendo que un empleado de otra compañía con el mismo nombre
    autenticara (y quedara atribuido) en el TPV de una empresa distinta."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_name = "nombre" if "nombre" in columnas else "usuario"
                tiene_emp = "id_empresa" in columnas
                cols = ["id", col_name, "perfil", "centro_codigo", "password",
                        "intentos_fallidos", "bloqueado_hasta"]
                if tiene_emp:
                    cols.append("id_empresa")
                condicion = f"UPPER({col_name}) = UPPER(%s)"
                params = [nombre.strip()]
                if tiene_emp:
                    try:
                        from src.db.empresa import empresa_actual_id
                        _id_emp = empresa_actual_id()
                    except Exception:
                        _id_emp = None
                    if _id_emp is not None:
                        condicion += " AND id_empresa = %s"
                        params.append(_id_emp)
                cur.execute(
                    f"SELECT {', '.join(cols)} FROM usuarios WHERE {condicion}",
                    tuple(params))
                filas = cur.fetchall()
            d, _bloq = _autenticar(cols, filas, password)
            if d:
                return {"id": d["id"], "nombre": d[col_name], "perfil": d["perfil"],
                        "centro_codigo": d["centro_codigo"],
                        "id_empresa": d.get("id_empresa") if tiene_emp else None}
    except Exception as e:
        logger.error(f"Error en validación TPV por nombre: {e}")
    return None


def validar_login_usuario(identificador: str, password: str, id_empresa=None) -> dict | None:
    """Login por IDENTIDAD individual (nombre o email), único por empresa (C1.4).

    Modelo objetivo para API/SaaS/móvil. Mantiene soporte dual de hash, rehash y
    bloqueo por intentos. Si `id_empresa` se indica, restringe a esa empresa."""
    ident = (identificador or "").strip()
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_name = "nombre" if "nombre" in columnas else "usuario"
                tiene_emp = "id_empresa" in columnas
                tiene_email = "email" in columnas
                cols = ["id", col_name, "perfil", "centro_codigo", "password",
                        "intentos_fallidos", "bloqueado_hasta"]
                if tiene_emp:
                    cols.append("id_empresa")
                if tiene_email:
                    cols.append("email")
                cond = f"UPPER({col_name}) = UPPER(%s)"
                params = [ident]
                if tiene_email:
                    cond = f"({cond} OR UPPER(email) = UPPER(%s))"
                    params.append(ident)
                if id_empresa and tiene_emp:
                    cond += " AND id_empresa = %s"
                    params.append(id_empresa)
                cur.execute(f"SELECT {', '.join(cols)} FROM usuarios WHERE {cond}", tuple(params))
                filas = cur.fetchall()
            d, _bloq = _autenticar(cols, filas, password)
            if d:
                _audit_seguridad("LOGIN", d["id"], f"identidad={ident}")
                return {"id": d["id"], "nombre": d[col_name], "perfil": d["perfil"],
                        "centro_codigo": d["centro_codigo"],
                        "id_empresa": d.get("id_empresa") if tiene_emp else None,
                        "email": d.get("email") if tiene_email else None}
            _audit_seguridad("LOGIN_FALLIDO", None, f"identidad={ident}")
    except Exception as e:
        logger.error(f"Error en validación por identidad: {e}")
    return None


def _audit_seguridad(accion, id_usuario, detalles):
    """Traza un evento de seguridad (FASE 10). Best-effort."""
    try:
        from src.services.seguridad import auditoria as _aud
        _aud.registrar(accion, usuario=id_usuario, detalles=detalles)
    except Exception:
        pass


def puede_iniciar_sesion(id_usuario: int, perfil: str) -> bool:
    """Sesión única de escritorio (salvo SUPERADMIN): rechaza un nuevo login si el
    usuario ya tiene una sesión viva en otro equipo. SUPERADMIN queda exento a
    propósito, para poder conectarse a varias tiendas a la vez de forma remota."""
    if str(perfil or "").upper() == "SUPERADMIN":
        return True
    try:
        from src.db import sesiones_desktop
        return not sesiones_desktop.hay_sesion_activa_otro_equipo(id_usuario)
    except Exception as e:
        logger.error("puede_iniciar_sesion(%s): %s", id_usuario, e)
        return True


class SesionUsuario:
    """Clase Singleton para gestionar la sesión activa del usuario."""

    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super(SesionUsuario, cls).__new__(cls)
            cls._instancia.usuario_actual = None
            cls._instancia.hora_inicio = None
            cls._instancia.id_sesion_desktop = None
            # "Centro en foco" (Sistema de Centros, Parte E): puramente INFORMATIVO, para
            # pantallas de administración/identidad — NUNCA toca el TenantContext operativo real
            # (empresa/tienda de `db/empresa.py`). Se fija al elegir, en "Cambiar de Centro"
            # (`gui/selector_tienda.py`), un centro que NO es de tipo 'tienda' (esos sí cambian el
            # TenantContext real, como siempre). No persiste entre sesiones.
            cls._instancia.centro_en_foco = None
        return cls._instancia

    def iniciar_sesion(self, datos_usuario: dict):
        """Almacena los datos del usuario, marca la hora de entrada y FIJA el
        contexto de tenant (empresa/tienda) del usuario para el aislamiento de
        datos multiempresa."""
        self.usuario_actual = datos_usuario
        self.hora_inicio = datetime.now()
        try:
            from src.db import sesiones_desktop
            self.id_sesion_desktop = sesiones_desktop.registrar_sesion(
                datos_usuario.get("id"), self.obtener_nombre(), datos_usuario.get("perfil"),
            )
        except Exception as e:
            logger.debug("No se pudo registrar la sesión de escritorio: %s", e)
            self.id_sesion_desktop = None
        try:
            from src.db.empresa import (
                EMPRESA_DEFAULT_ID, set_empresa_actual, set_tienda_actual,
            )
            set_empresa_actual(datos_usuario.get("id_empresa") or EMPRESA_DEFAULT_ID)
            set_tienda_actual(datos_usuario.get("centro_codigo"))
            # Stock de trabajo = el de la tienda del usuario (aislamiento 3b.1-2c).
            try:
                from src.db import stock as _stock
                _stock.cargar_stock(datos_usuario.get("centro_codigo"))
            except Exception:
                pass
        except Exception as e:
            logger.debug("No se pudo fijar el contexto de empresa: %s", e)
        logger.info(
            f"Sesión iniciada: {self.obtener_nombre()} ({datos_usuario.get('perfil')})"
        )

    def cerrar_sesion(self):
        """Limpia la sesión y restablece el contexto de tenant a la empresa por
        defecto. Crucial para que main.py detecte el logout."""
        nombre = self.obtener_nombre()
        # Persistir el stock de trabajo en la tienda activa antes de salir (3b.1-2c).
        try:
            from src.db import stock as _stock
            _stock.flush_stock()
        except Exception:
            pass
        try:
            from src.db import sesiones_desktop
            sesiones_desktop.cerrar_sesion(self.id_sesion_desktop)
        except Exception:
            pass
        self.usuario_actual = None
        self.hora_inicio = None
        self.id_sesion_desktop = None
        self.centro_en_foco = None
        try:
            from src.db.empresa import (
                EMPRESA_DEFAULT_ID, set_empresa_actual, set_tienda_actual,
            )
            set_empresa_actual(EMPRESA_DEFAULT_ID)
            set_tienda_actual(None)
        except Exception:
            pass
        logger.info(f"Sesión destruida para: {nombre}")

    def set_centro_en_foco(self, centro: dict | None):
        """Fija el "centro en foco" (informativo, ver comentario en `__new__`) — usado por
        "Cambiar de Centro" al elegir un centro no-operativo (almacén/fábrica/oficina/otro)."""
        self.centro_en_foco = centro

    def centro_en_foco_actual(self) -> dict | None:
        return getattr(self, "centro_en_foco", None)

    def obtener_nombre(self):
        """Devuelve el nombre legible del usuario actual."""
        if not self.usuario_actual:
            return "Invitado"
        return (
            self.usuario_actual.get("nombre")
            or self.usuario_actual.get("usuario")
            or "Desconocido"
        )

    def es_admin(self):
        """Verifica si el perfil actual tiene permisos elevados."""
        if not self.usuario_actual:
            return False
        perfil = str(self.usuario_actual.get("perfil", "")).upper()
        return perfil in ["SUPERADMIN", "ADMINISTRADOR"]

    def es_superadmin(self):
        """SUPERADMIN: rol por encima de la empresa (visión de todas las empresas
        en un futuro modelo SaaS). Hoy, en escritorio mono-empresa, equivale a un
        administrador global."""
        if not self.usuario_actual:
            return False
        return str(self.usuario_actual.get("perfil", "")).upper() == "SUPERADMIN"

    def empresa_id(self):
        """ID de empresa del usuario activo (o la empresa por defecto)."""
        if self.usuario_actual and self.usuario_actual.get("id_empresa"):
            return self.usuario_actual["id_empresa"]
        try:
            from src.db.empresa import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


# Instancia única exportada
sesion_global = SesionUsuario()


# ============================================================
# BLOQUE CONSULTA DE USUARIOS
# ============================================================

def obtener_usuario(id_usuario):
    """Datos de un usuario por id (para refrescar claims del token con el estado
    ACTUAL: rol/tienda/empresa pueden haber cambiado). None si no existe/activo."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            columnas = _columnas_usuarios(cur)
            col_name = "nombre" if "nombre" in columnas else "usuario"
            tiene_emp = "id_empresa" in columnas
            tiene_centro = "id_centro_trabajo" in columnas
            tiene_email = "email" in columnas
            cols = (["id", col_name, "perfil", "centro_codigo"] + (["id_empresa"] if tiene_emp else [])
                    + (["id_centro_trabajo"] if tiene_centro else []) + (["email"] if tiene_email else []))
            cond = " AND COALESCE(activo,1)=1" if "activo" in columnas else ""
            cur.execute(f"SELECT {', '.join(cols)} FROM usuarios WHERE id=%s{cond}", (id_usuario,))
            fila = cur.fetchone()
            if not fila:
                return None
            d = dict(zip(cols, fila))
            return {"id": d["id"], "nombre": d[col_name], "perfil": d["perfil"],
                    "centro_codigo": d["centro_codigo"],
                    "id_empresa": d.get("id_empresa") if tiene_emp else None,
                    "id_centro_trabajo": d.get("id_centro_trabajo") if tiene_centro else None,
                    "email": d.get("email") if tiene_email else None}
    except Exception as e:
        logger.error("obtener_usuario(%s): %s", id_usuario, e)
        return None


def listar_usuarios():
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas = [
                    col["Field"] if isinstance(col, dict) else col[0]
                    for col in cur.fetchall()
                ]
                col_name = "nombre" if "nombre" in columnas else "usuario"

                cur.execute(f"SELECT id, {col_name}, perfil, centro_codigo FROM usuarios")
                filas = cur.fetchall()
                return [
                    {"id": f[0], "nombre": f[1], "perfil": f[2], "centro_codigo": f[3]}
                    for f in filas
                ]
    except Exception as e:
        logger.error(f"Error al listar usuarios: {e}")
        return []


def listar_usuarios_empresa(id_empresa=None, centro_codigo=None):
    """Lista los perfiles/empleados de UNA empresa, con AISLAMIENTO ESTRICTO por `id_empresa`
    (privacidad entre empresas: NUNCA devuelve empleados de otra). Si la tabla no tiene columna
    id_empresa (instalación mono-empresa), devuelve todos — al haber una sola empresa no hay cruce
    posible. Solo activos si existe la columna `activo`. Usado por el selector de perfil del login.

    `centro_codigo` (Fase Productividad): si se indica, filtra solo los empleados vinculados a ESE
    centro (`usuarios.centro_codigo`) — el desplegable de empleado de Productividad necesita el id
    REAL de `usuarios` (el mismo que puebla `ventas.id_usuario`/`fichajes.usuario_id`), por eso
    reutiliza esta función en vez de `rrhh.db.empleados.listar_empleados` (esa lista empleados de
    RRHH, con su propio id, un espacio de identidad DISTINTO al de login/TPV/fichajes).

    Devuelve [{id, nombre, perfil, id_empresa}] ordenado por nombre."""
    try:
        if id_empresa is None:
            try:
                from src.db.empresa import empresa_actual_id
                id_empresa = empresa_actual_id()
            except Exception:
                id_empresa = None
        with obtener_conexion() as conn, conn.cursor() as cur:
            columnas = _columnas_usuarios(cur)
            col_name = "nombre" if "nombre" in columnas else "usuario"
            tiene_emp = "id_empresa" in columnas
            tiene_act = "activo" in columnas
            tiene_centro = "centro_codigo" in columnas
            cols = ["id", col_name, "perfil"] + (["id_empresa"] if tiene_emp else [])
            cond, params = [], []
            if tiene_emp and id_empresa:
                cond.append("id_empresa = %s"); params.append(id_empresa)
            if tiene_act:
                cond.append("activo = 1")
            if centro_codigo is not None and tiene_centro:
                cond.append("centro_codigo = %s"); params.append(centro_codigo)
            where = (" WHERE " + " AND ".join(cond)) if cond else ""
            cur.execute(
                f"SELECT {', '.join(cols)} FROM usuarios{where} ORDER BY {col_name} ASC",
                tuple(params))
            salida = []
            for f in cur.fetchall():
                d = f if isinstance(f, dict) else dict(zip(cols, f))
                salida.append({"id": d.get("id"), "nombre": d.get(col_name),
                               "perfil": d.get("perfil"),
                               "id_empresa": d.get("id_empresa") if tiene_emp else None})
            return salida
    except Exception as e:
        logger.error("listar_usuarios_empresa: %s", e)
        return []


# ============================================================
# BLOQUE CREACIÓN Y MODIFICACIÓN DE USUARIOS
# ============================================================

def crear_perfil(nombre, password, perfil_tipo="OPERARIO", centro_codigo=None, email=None):
    try:
        if not sesion_global.es_admin():
            # Excepción de ARRANQUE (alta del primer perfil de una instalación nueva, ver
            # `gui/primer_superadmin_wizard.py`): por definición no puede existir todavía una
            # sesión de administrador que la autorice. Solo se permite si la tabla `usuarios`
            # está realmente vacía — dejar de aplicar en cuanto exista el primer perfil.
            try:
                with obtener_conexion() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM usuarios")
                        row = cur.fetchone()
                        total = row[0] if not isinstance(row, dict) else row.get("COUNT(*)", 0)
                if int(total or 0) > 0:
                    return False
            except Exception:
                return False
        from src.seguridad import politica
        ok_pol, motivo = politica.validar_pin(password)
        if not ok_pol:
            logger.warning("PIN rechazado por política: %s", motivo)
            return False
        password_segura = encriptar_password(password)
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas = [
                    col["Field"] if isinstance(col, dict) else col[0]
                    for col in cur.fetchall()
                ]
                col_name = "nombre" if "nombre" in columnas else "usuario"

                cols = [col_name, "password", "perfil", "centro_codigo"]
                vals = [nombre.strip().upper(), password_segura, perfil_tipo, centro_codigo]
                email_limpio = (email or "").strip() or None
                if email_limpio and "email" in columnas:
                    cols.append("email")
                    vals.append(email_limpio)
                marcadores = ", ".join(["%s"] * len(cols))
                sql = f"INSERT INTO usuarios ({', '.join(cols)}) VALUES ({marcadores})"
                cur.execute(sql, tuple(vals))
                nuevo_id = cur.lastrowid
            conn.commit()
        # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
        try:
            from src.services import eventos as _EV
            _EV.publicar("USUARIO_CREADO", origen="seguridad", ref_entidad="usuario",
                         ref_id=nuevo_id, payload={"nombre": nombre.strip().upper(),
                                                   "perfil": perfil_tipo})
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"Error al crear perfil: {e}")
        return False


def cambiar_password_usuario(id_usuario: int, nueva_password: str) -> bool:
    try:
        from src.seguridad import politica
        ok_pol, motivo = politica.validar_pin(nueva_password)
        if not ok_pol:
            logger.warning("PIN rechazado por política: %s", motivo)
            return False
        password_hash = encriptar_password(nueva_password)
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE usuarios SET password=%s WHERE id=%s", (password_hash, id_usuario))
            conn.commit()
            _audit_seguridad("CAMBIO_PASSWORD", id_usuario, f"usuario={id_usuario}")
            return True
    except Exception as e:
        logger.error(f"Error al cambiar contraseña: {e}")
        return False


def actualizar_usuario(id_usuario, nombre, perfil, centro_codigo, email=None):
    """`email` es OPCIONAL y, a diferencia de `nombre`/`perfil`/`centro_codigo` (que esta función
    siempre reescribe juntos, ver `gui/gestion_usuarios.py::ejecutar_editar_perfil`/
    `ejecutar_vincular_centro`), un `email=None` significa "no tocar" (no clobberea el email ya
    guardado en los llamadores existentes que no lo pasan); pasa una cadena (incluida "") para
    fijarlo/borrarlo explícitamente."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas = [
                    col["Field"] if isinstance(col, dict) else col[0]
                    for col in cur.fetchall()
                ]
                col_name = "nombre" if "nombre" in columnas else "usuario"

                sets = [f"{col_name}=%s", "perfil=%s", "centro_codigo=%s"]
                vals = [nombre, perfil, centro_codigo]
                if email is not None and "email" in columnas:
                    sets.append("email=%s")
                    vals.append(email.strip() or None)
                vals.append(id_usuario)
                sql = f"UPDATE usuarios SET {', '.join(sets)} WHERE id=%s"
                cur.execute(sql, tuple(vals))
            conn.commit()
            _audit_seguridad("CAMBIO_ROL", id_usuario, f"usuario={id_usuario} perfil={perfil}")
            # Fase 1 (motor de eventos): publicacion OBSERVACIONAL, aditiva y bulletproof.
            try:
                from src.services import eventos as _EV
                _EV.publicar("ROL_MODIFICADO", origen="seguridad", ref_entidad="usuario",
                             ref_id=id_usuario, payload={"perfil": perfil})
            except Exception:
                pass
            return True
    except Exception as e:
        logger.error(f"Error al actualizar usuario: {e}")
        return False


def vincular_centro_trabajo(id_usuario, id_centro_trabajo) -> bool:
    """Vincula un usuario a un centro (`centros_trabajo.id_centro`, CHAR(36) — "Centros de
    empresa" unificados, migración 0257; antes `centros_perfil.id`, tabla retirada) — SOLO fija
    `usuarios.id_centro_trabajo` (antes `id_centro_perfil`, INT: se retiró y sustituyó por esta
    columna VARCHAR(36) porque el nuevo destino es un UUID, no un entero — ver migración 0257).
    `centro_codigo` es un campo aparte (se sincroniza en el mismo flujo de llamada, ver
    `gui/gestion_usuarios.py::ejecutar_vincular_centro`, que combina esto con `actualizar_usuario`
    siguiendo el mismo patrón de re-lectura que `ejecutar_editar_perfil`, para no romper ningún
    consumidor existente de `centro_codigo`: kárdex, logística, sesión)."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE usuarios SET id_centro_trabajo=%s WHERE id=%s",
                            (id_centro_trabajo, id_usuario))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al vincular centro_trabajo: {e}")
        return False


# ============================================================
# BLOQUE ELIMINACIÓN DE USUARIOS
# ============================================================

def eliminar_usuario(id_usuario):
    try:
        if not sesion_global.es_admin():
            return False
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM usuarios WHERE id = %s", (id_usuario,))
            conn.commit()
            _audit_seguridad("BAJA_USUARIO", id_usuario, f"usuario={id_usuario}")
            return True
    except Exception as e:
        logger.error(f"Error al eliminar usuario: {e}")
        return False


# ============================================================
# BLOQUE FICHAJES (control de asistencia)
# ============================================================

def validar_pin_fichaje(pin: str) -> dict | None:
    """Busca el empleado cuyo password coincide con el PIN. Verifica fila a fila
    (Argon2id no admite comparación por igualdad en SQL) con soporte dual y rehash."""
    pin = pin.strip()
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_name = "nombre" if "nombre" in columnas else "usuario"
                cond_activo = " WHERE COALESCE(activo,1)=1" if "activo" in columnas else ""
                cur.execute(f"SELECT id, {col_name}, password FROM usuarios{cond_activo}")
                filas = cur.fetchall()
            for fila in filas:
                ok, nuevo = _pw.verificar(pin, fila[2])
                if ok:
                    _rehash(fila[0], nuevo)
                    return {"id": fila[0], "nombre": fila[1]}
    except Exception as e:
        logger.error(f"Error validando PIN fichaje: {e}")
    return None


def validar_pin_por_rol(pin: str, roles) -> dict | None:
    """Valida un PIN/contraseña exigiendo un perfil dentro de `roles` (lista de perfiles
    permitidos, p. ej. ['ADMINISTRADOR','SUPERADMIN']). Verifica FILA A FILA con
    soporte dual Argon2id/SHA-256 + rehash transparente (Argon2id no admite comparación por
    igualdad en SQL). Devuelve {id, nombre, perfil} del autorizador o None."""
    pin = (pin or "").strip()
    roles = [r for r in (roles or []) if r]
    if not pin or not roles:
        return None
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_name = "nombre" if "nombre" in columnas else "usuario"
                cond_activo = " AND COALESCE(activo,1)=1" if "activo" in columnas else ""
                ph = ",".join(["%s"] * len(roles))
                cur.execute(
                    f"SELECT id, {col_name}, password, perfil FROM usuarios "
                    f"WHERE perfil IN ({ph}){cond_activo}", tuple(roles))
                filas = cur.fetchall()
            for fila in filas:
                _id = fila["id"] if isinstance(fila, dict) else fila[0]
                _nombre = fila[col_name] if isinstance(fila, dict) else fila[1]
                _hash = fila["password"] if isinstance(fila, dict) else fila[2]
                _perfil = fila["perfil"] if isinstance(fila, dict) else fila[3]
                ok, nuevo = _pw.verificar(pin, _hash)
                if ok:
                    _rehash(_id, nuevo)
                    return {"id": _id, "nombre": _nombre, "perfil": _perfil}
    except Exception as e:
        logger.error("Error validando PIN por rol: %s", e)
    return None


def validar_pin_de_usuario(id_usuario, pin: str) -> dict | None:
    """Valida el PIN/contraseña de un usuario CONCRETO (por id). Verificación Argon2id (dual
    SHA-256 legado + rehash). Devuelve {id, nombre} si coincide y el usuario está activo, o None."""
    pin = (pin or "").strip()
    if id_usuario is None or not pin:
        return None
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_name = "nombre" if "nombre" in columnas else "usuario"
                cond_activo = " AND COALESCE(activo,1)=1" if "activo" in columnas else ""
                cur.execute(f"SELECT id, {col_name}, password FROM usuarios WHERE id=%s{cond_activo}",
                            (id_usuario,))
                fila = cur.fetchone()
            if not fila:
                return None
            _id = fila["id"] if isinstance(fila, dict) else fila[0]
            _nombre = fila[col_name] if isinstance(fila, dict) else fila[1]
            _hash = fila["password"] if isinstance(fila, dict) else fila[2]
            ok, nuevo = _pw.verificar(pin, _hash)
            if ok:
                _rehash(_id, nuevo)
                return {"id": _id, "nombre": _nombre}
    except Exception as e:
        logger.error("Error validando PIN de usuario %s: %s", id_usuario, e)
    return None


def obtener_fichaje_abierto(usuario_id: int) -> dict | None:
    """Devuelve el fichaje sin salida del empleado, si existe."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, entrada FROM fichajes WHERE usuario_id = %s AND salida IS NULL "
                    "ORDER BY entrada DESC LIMIT 1",
                    (usuario_id,)
                )
                fila = cur.fetchone()
                if fila:
                    return {"id": fila[0], "entrada": fila[1]}
    except Exception as e:
        logger.error(f"Error obteniendo fichaje abierto: {e}")
    return None


def registrar_entrada(usuario_id: int, nombre: str) -> int | None:
    """Crea un registro de fichaje y devuelve su ID."""
    try:
        # id_tienda es INT: se coacciona el contexto (que puede ser alfanumérico, p. ej. 'ALMC' = almacén
        # central) a entero con el helper oficial; si no es numérico → 0. Evita el DataError 1366 al insertar.
        from src.db.empresa import empresa_actual_id, tienda_actual_id_int
        _emp, _tnd = empresa_actual_id(), tienda_actual_id_int()
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO fichajes (usuario_id, nombre_empleado, entrada, id_empresa, id_tienda) "
                    "VALUES (%s, %s, NOW(), %s, %s)",
                    (usuario_id, nombre, _emp, _tnd)
                )
                fichaje_id = cur.lastrowid
            conn.commit()
            return fichaje_id
    except Exception as e:
        logger.error(f"Error registrando entrada: {e}")
    return None


def registrar_salida(fichaje_id: int) -> int | None:
    """Registra la salida y devuelve la duración en segundos."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE fichajes SET salida = NOW(), "
                    "duracion_segundos = TIMESTAMPDIFF(SECOND, entrada, NOW()) "
                    "WHERE id = %s",
                    (fichaje_id,)
                )
            conn.commit()
            with conn.cursor() as cur:
                cur.execute("SELECT duracion_segundos FROM fichajes WHERE id = %s", (fichaje_id,))
                fila = cur.fetchone()
                if fila:
                    return fila[0]
    except Exception as e:
        logger.error(f"Error registrando salida: {e}")
    return None


def listar_fichajes() -> list:
    """Devuelve todos los fichajes ordenados por entrada descendente."""
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        _emp, _tnd = empresa_actual_id(), tienda_actual_id()
        _filtros, _params = ["id_empresa=%s"], [_emp]
        if _tnd is not None:
            _filtros.append("id_tienda=%s"); _params.append(_tnd)
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, usuario_id, nombre_empleado, entrada, salida, duracion_segundos "
                    "FROM fichajes WHERE " + " AND ".join(_filtros) + " ORDER BY entrada DESC",
                    tuple(_params)
                )
                filas = cur.fetchall()
                return [
                    {
                        "id": f[0],
                        "usuario_id": f[1],
                        "nombre": f[2],
                        "entrada": f[3],
                        "salida": f[4],
                        "segundos": f[5],
                    }
                    for f in filas
                ]
    except Exception as e:
        logger.error(f"Error listando fichajes: {e}")
    return []


def _tenant_filtros():
    """(filtros, params) con id_empresa (+id_tienda si aplica) para las consultas de fichajes."""
    from src.db.empresa import empresa_actual_id, tienda_actual_id
    emp, tnd = empresa_actual_id(), tienda_actual_id()
    filtros, params = ["id_empresa=%s"], [emp]
    if tnd is not None:
        filtros.append("id_tienda=%s"); params.append(tnd)
    return filtros, params


def meses_con_fichajes_empleado(usuario_id) -> list:
    """Lista de (anio, mes) con fichajes de un empleado, más reciente primero. Aislado por empresa/tienda."""
    try:
        filtros, params = _tenant_filtros()
        filtros.append("usuario_id=%s"); params.append(usuario_id)
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT YEAR(entrada) AS y, MONTH(entrada) AS m FROM fichajes "
                "WHERE " + " AND ".join(filtros) + " ORDER BY y DESC, m DESC", tuple(params))
            return [(int(f[0]), int(f[1])) for f in cur.fetchall()]
    except Exception as e:
        logger.error(f"meses_con_fichajes_empleado: {e}")
        return []


def listar_fichajes_empleado(usuario_id, anio=None, mes=None) -> list:
    """Fichajes de UN empleado en un mes (por defecto el actual), más recientes primero, con la duración
    por fichaje (incluida la sesión abierta hasta ahora). Aislado por empresa/tienda."""
    import datetime
    hoy = datetime.date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month
    try:
        filtros, params = _tenant_filtros()
        filtros += ["usuario_id=%s", "YEAR(entrada)=%s", "MONTH(entrada)=%s"]
        params += [usuario_id, anio, mes]
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, entrada, salida, "
                "  COALESCE(duracion_segundos, TIMESTAMPDIFF(SECOND, entrada, NOW())) AS seg "
                "FROM fichajes WHERE " + " AND ".join(filtros) + " ORDER BY entrada DESC, id DESC",
                tuple(params))
            return [{"id": f[0], "entrada": f[1], "salida": f[2], "segundos": int(f[3] or 0)}
                    for f in cur.fetchall()]
    except Exception as e:
        logger.error(f"listar_fichajes_empleado: {e}")
        return []


def horas_mes_por_empleado(anio=None, mes=None) -> list:
    """Horas trabajadas por empleado en un mes (por defecto el mes EN CURSO), sumando la duración de
    los fichajes cerrados + la sesión abierta hasta ahora. Aislado por empresa/tienda.
    Devuelve [{usuario_id, nombre, segundos, horas, fichajes}] ordenado por nombre."""
    import datetime
    hoy = datetime.date.today()
    anio = anio or hoy.year
    mes = mes or hoy.month
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        emp, tnd = empresa_actual_id(), tienda_actual_id()
        filtros, params = ["id_empresa=%s"], [emp]
        if tnd is not None:
            filtros.append("id_tienda=%s"); params.append(tnd)
        filtros += ["YEAR(entrada)=%s", "MONTH(entrada)=%s"]
        params += [anio, mes]
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT usuario_id, nombre_empleado, "
                "  SUM(COALESCE(duracion_segundos, TIMESTAMPDIFF(SECOND, entrada, NOW()))) AS seg, "
                "  COUNT(*) AS n "
                "FROM fichajes WHERE " + " AND ".join(filtros) +
                " GROUP BY usuario_id, nombre_empleado ORDER BY nombre_empleado ASC",
                tuple(params))
            out = []
            for f in cur.fetchall():
                seg = int(f[2] or 0)
                out.append({"usuario_id": f[0], "nombre": f[1], "segundos": seg,
                            "horas": round(seg / 3600.0, 2), "fichajes": int(f[3] or 0)})
            return out
    except Exception as e:
        logger.error(f"Error horas_mes_por_empleado: {e}")
        return []


def horas_trabajadas_rango(usuario_id, fecha_desde, fecha_hasta, id_empresa=None) -> float:
    """Horas trabajadas por UN empleado entre dos fechas (inclusive), sumando fichajes cerrados +
    la sesión abierta hasta ahora (mismo criterio que `horas_mes_por_empleado`/
    `listar_fichajes_empleado`, pero por RANGO arbitrario — necesario para Productividad, cuyos
    periodos (semanal/bimensual/bimestral/trimestral/semestral) no siempre coinciden con límites
    de mes). Aislado por `id_empresa` explícito (no depende del contexto de tienda ambiente: el
    dashboard de Productividad consulta centros que el superadministrador gestiona, no
    necesariamente el centro conectado en este momento)."""
    try:
        from src.db.empresa import empresa_actual_id
        emp = id_empresa if id_empresa is not None else empresa_actual_id()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT SUM(COALESCE(duracion_segundos, TIMESTAMPDIFF(SECOND, entrada, NOW()))) "
                "FROM fichajes WHERE id_empresa=%s AND usuario_id=%s "
                "AND DATE(entrada) BETWEEN %s AND %s",
                (emp, usuario_id, fecha_desde, fecha_hasta))
            r = cur.fetchone()
            seg = r[0] if not isinstance(r, dict) else list(r.values())[0]
            return round(int(seg or 0) / 3600.0, 2)
    except Exception as e:
        logger.error(f"Error horas_trabajadas_rango: {e}")
        return 0.0
