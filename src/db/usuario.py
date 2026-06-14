import hashlib
import logging
from datetime import datetime

from .conexion import obtener_conexion

logger = logging.getLogger("usuario_db")


# ============================================================
# BLOQUE AUTENTICACIÓN Y SESIÓN
# ============================================================

def encriptar_password(password: str) -> str:
    """Convierte una contraseña en texto plano a un hash SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def validar_login(perfil_ui, password):
    """Valida las credenciales realizando un mapeo dinámico de columnas."""
    valor_busqueda = perfil_ui.strip().upper()
    password_hash = encriptar_password(password)

    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas_info = cur.fetchall()
                columnas = [
                    col["Field"] if isinstance(col, dict) else col[0]
                    for col in columnas_info
                ]
                col_usuario = "nombre" if "nombre" in columnas else "usuario"

                col_emp = ", id_empresa" if "id_empresa" in columnas else ""
                sql = f"""
                    SELECT id, {col_usuario}, perfil, tienda_id{col_emp}
                    FROM usuarios
                    WHERE UPPER(perfil) = %s AND password = %s
                """
                cur.execute(sql, (valor_busqueda, password_hash))
                fila = cur.fetchone()

                if fila:
                    usuario = {
                        "id": fila[0],
                        "nombre": fila[1],
                        "perfil": fila[2],
                        "tienda_id": fila[3],
                        "id_empresa": fila[4] if col_emp else None,
                    }
                    logger.info(f"Acceso concedido para perfil: {valor_busqueda}")
                    return usuario

                logger.warning(f"Intento de login fallido para: {valor_busqueda}")
                return None
    except Exception as e:
        logger.error(f"Error crítico en validación: {e}")
        return None


def validar_login_empleado(nombre: str, password: str) -> dict | None:
    """Valida credenciales buscando por nombre individual de empleado (para TPV)."""
    password_hash = encriptar_password(password)
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas = [
                    col["Field"] if isinstance(col, dict) else col[0]
                    for col in cur.fetchall()
                ]
                col_name = "nombre" if "nombre" in columnas else "usuario"
                col_emp = ", id_empresa" if "id_empresa" in columnas else ""
                sql = f"""
                    SELECT id, {col_name}, perfil, tienda_id{col_emp}
                    FROM usuarios
                    WHERE UPPER({col_name}) = UPPER(%s) AND password = %s
                """
                cur.execute(sql, (nombre.strip(), password_hash))
                fila = cur.fetchone()
                if fila:
                    return {"id": fila[0], "nombre": fila[1], "perfil": fila[2],
                            "tienda_id": fila[3], "id_empresa": fila[4] if col_emp else None}
    except Exception as e:
        logger.error(f"Error en validación TPV por nombre: {e}")
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
    """Busca el empleado cuyo password SHA-256 coincide con el PIN de 4 dígitos."""
    pin_hash = encriptar_password(pin.strip())
    try:
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute("SHOW COLUMNS FROM usuarios")
                columnas = [col["Field"] if isinstance(col, dict) else col[0] for col in cur.fetchall()]
                col_name = "nombre" if "nombre" in columnas else "usuario"
                cur.execute(
                    f"SELECT id, {col_name} FROM usuarios WHERE password = %s LIMIT 1",
                    (pin_hash,)
                )
                fila = cur.fetchone()
                if fila:
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
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO fichajes (usuario_id, nombre_empleado, entrada) VALUES (%s, %s, NOW())",
                    (usuario_id, nombre)
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
        with obtener_conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, usuario_id, nombre_empleado, entrada, salida, duracion_segundos "
                    "FROM fichajes ORDER BY entrada DESC"
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
