import hashlib
import logging
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
    """Valida credenciales por perfil. Verifica con soporte dual (Argon2id +
    SHA-256 legado) fila a fila y rehashea al primer acierto."""
    valor_busqueda = perfil_ui.strip().upper()
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_usuario = "nombre" if "nombre" in columnas else "usuario"
                tiene_emp = "id_empresa" in columnas
                cols = ["id", col_usuario, "perfil", "tienda_id", "password",
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
                        "tienda_id": d["tienda_id"],
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
    dual Argon2id/SHA-256 con rehash en el primer acierto."""
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                columnas = _columnas_usuarios(cur)
                col_name = "nombre" if "nombre" in columnas else "usuario"
                tiene_emp = "id_empresa" in columnas
                cols = ["id", col_name, "perfil", "tienda_id", "password",
                        "intentos_fallidos", "bloqueado_hasta"]
                if tiene_emp:
                    cols.append("id_empresa")
                cur.execute(
                    f"SELECT {', '.join(cols)} FROM usuarios WHERE UPPER({col_name}) = UPPER(%s)",
                    (nombre.strip(),))
                filas = cur.fetchall()
            d, _bloq = _autenticar(cols, filas, password)
            if d:
                return {"id": d["id"], "nombre": d[col_name], "perfil": d["perfil"],
                        "tienda_id": d["tienda_id"],
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
                cols = ["id", col_name, "perfil", "tienda_id", "password",
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
                return {"id": d["id"], "nombre": d[col_name], "perfil": d["perfil"],
                        "tienda_id": d["tienda_id"],
                        "id_empresa": d.get("id_empresa") if tiene_emp else None,
                        "email": d.get("email") if tiene_email else None}
    except Exception as e:
        logger.error(f"Error en validación por identidad: {e}")
    return None


class SesionUsuario:
    """Clase Singleton para gestionar la sesión activa del usuario."""

    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super(SesionUsuario, cls).__new__(cls)
            cls._instancia.usuario_actual = None
            cls._instancia.hora_inicio = None
        return cls._instancia

    def iniciar_sesion(self, datos_usuario: dict):
        """Almacena los datos del usuario, marca la hora de entrada y FIJA el
        contexto de tenant (empresa/tienda) del usuario para el aislamiento de
        datos multiempresa."""
        self.usuario_actual = datos_usuario
        self.hora_inicio = datetime.now()
        try:
            from src.db.empresa import (
                EMPRESA_DEFAULT_ID, set_empresa_actual, set_tienda_actual,
            )
            set_empresa_actual(datos_usuario.get("id_empresa") or EMPRESA_DEFAULT_ID)
            set_tienda_actual(datos_usuario.get("tienda_id"))
            # Stock de trabajo = el de la tienda del usuario (aislamiento 3b.1-2c).
            try:
                from src.db import stock as _stock
                _stock.cargar_stock(datos_usuario.get("tienda_id"))
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
        self.usuario_actual = None
        self.hora_inicio = None
        try:
            from src.db.empresa import (
                EMPRESA_DEFAULT_ID, set_empresa_actual, set_tienda_actual,
            )
            set_empresa_actual(EMPRESA_DEFAULT_ID)
            set_tienda_actual(None)
        except Exception:
            pass
        logger.info(f"Sesión destruida para: {nombre}")

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
        return perfil in ["SUPERADMIN", "ADMINISTRADOR", "GERENTE"]

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
            cols = ["id", col_name, "perfil", "tienda_id"] + (["id_empresa"] if tiene_emp else [])
            cond = " AND COALESCE(activo,1)=1" if "activo" in columnas else ""
            cur.execute(f"SELECT {', '.join(cols)} FROM usuarios WHERE id=%s{cond}", (id_usuario,))
            fila = cur.fetchone()
            if not fila:
                return None
            d = dict(zip(cols, fila))
            return {"id": d["id"], "nombre": d[col_name], "perfil": d["perfil"],
                    "tienda_id": d["tienda_id"],
                    "id_empresa": d.get("id_empresa") if tiene_emp else None}
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

                cur.execute(f"SELECT id, {col_name}, perfil, tienda_id FROM usuarios")
                filas = cur.fetchall()
                return [
                    {"id": f[0], "nombre": f[1], "perfil": f[2], "tienda_id": f[3]}
                    for f in filas
                ]
    except Exception as e:
        logger.error(f"Error al listar usuarios: {e}")
        return []


# ============================================================
# BLOQUE CREACIÓN Y MODIFICACIÓN DE USUARIOS
# ============================================================

def crear_perfil(nombre, password, perfil_tipo="OPERARIO", tienda_id=None):
    try:
        if not sesion_global.es_admin():
            return False
        from src.seguridad import politica
        ok_pol, motivo = politica.validar(password)
        if not ok_pol:
            logger.warning("Contraseña rechazada por política: %s", motivo)
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

                sql = f"INSERT INTO usuarios ({col_name}, password, perfil, tienda_id) VALUES (%s, %s, %s, %s)"
                cur.execute(
                    sql,
                    (nombre.strip().upper(), password_segura, perfil_tipo, tienda_id),
                )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error al crear perfil: {e}")
        return False


def cambiar_password_usuario(id_usuario: int, nueva_password: str) -> bool:
    try:
        from src.seguridad import politica
        ok_pol, motivo = politica.validar(nueva_password)
        if not ok_pol:
            logger.warning("Contraseña rechazada por política: %s", motivo)
            return False
        password_hash = encriptar_password(nueva_password)
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE usuarios SET password=%s WHERE id=%s", (password_hash, id_usuario))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error al cambiar contraseña: {e}")
        return False


def actualizar_usuario(id_usuario, nombre, perfil, tienda_id):
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas = [
                    col["Field"] if isinstance(col, dict) else col[0]
                    for col in cur.fetchall()
                ]
                col_name = "nombre" if "nombre" in columnas else "usuario"

                sql = f"UPDATE usuarios SET {col_name}=%s, perfil=%s, tienda_id=%s WHERE id=%s"
                cur.execute(sql, (nombre, perfil, tienda_id, id_usuario))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error al actualizar usuario: {e}")
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
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        _emp, _tnd = empresa_actual_id(), tienda_actual_id()
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
