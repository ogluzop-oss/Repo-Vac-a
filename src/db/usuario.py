import logging
import hashlib
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

                sql = f"""
                    SELECT id, {col_usuario}, perfil, tienda_id 
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
                    }
                    logger.info(f"Acceso concedido para perfil: {valor_busqueda}")
                    return usuario

                logger.warning(f"Intento de login fallido para: {valor_busqueda}")
                return None
    except Exception as e:
        logger.error(f"Error crítico en validación: {e}")
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
        """Almacena los datos del usuario y marca la hora de entrada."""
        self.usuario_actual = datos_usuario
        self.hora_inicio = datetime.now()
        logger.info(
            f"Sesión iniciada: {self.obtener_nombre()} ({datos_usuario.get('perfil')})"
        )

    def cerrar_sesion(self):
        """Limpia la sesión. Crucial para que main.py detecte el logout."""
        nombre = self.obtener_nombre()
        self.usuario_actual = None
        self.hora_inicio = None
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
        return perfil in ["ADMINISTRADOR", "GERENTE"]


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
