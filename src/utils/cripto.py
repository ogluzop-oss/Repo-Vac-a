"""
Cifrado simétrico para secretos en reposo (tokens OAuth del correo corporativo).

NUNCA se almacenan contraseñas. Solo tokens OAuth 2.0, y SIEMPRE cifrados con
Fernet (AES-128 CBC + HMAC). La clave se guarda fuera del control de versiones
(documentos/.correo_key) o en la variable de entorno SMART_MANAGER_SECRET_KEY.

Si `cryptography` no estuviera disponible, degrada con un marcador claro y NO
cifra (se registra un aviso); así el resto del sistema sigue funcionando.
"""

import base64
import logging
import os

logger = logging.getLogger("cripto")

_PLANO_PREFIX = "plain:"  # marcador para valores no cifrados (degradación)
_fernet = None
_intentado = False


def _ruta_clave() -> str:
    try:
        from src.utils import recursos
        base = recursos.ruta_documentos() if hasattr(recursos, "ruta_documentos") else None
    except Exception:
        base = None
    if not base:
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "documentos",
        )
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, ".correo_key")


def _cargar_o_crear_clave() -> bytes | None:
    # 1) Variable de entorno (recomendado para despliegues controlados).
    env = os.getenv("SMART_MANAGER_SECRET_KEY")
    if env:
        try:
            return env.encode() if len(env) >= 44 else base64.urlsafe_b64encode(env.ljust(32)[:32].encode())
        except Exception:
            pass
    # 2) Archivo local (gitignored).
    ruta = _ruta_clave()
    try:
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                return f.read().strip()
        from cryptography.fernet import Fernet
        clave = Fernet.generate_key()
        with open(ruta, "wb") as f:
            f.write(clave)
        logger.info("Clave de cifrado de correo generada en %s", ruta)
        return clave
    except Exception as e:
        logger.error("No se pudo cargar/crear la clave de cifrado: %s", e)
        return None


def _claves_rotacion() -> list[bytes]:
    """Claves para ROTACIÓN sin downtime (MultiFernet): la primera cifra; todas
    descifran. Se toman de `SMART_MANAGER_SECRET_KEYS` (coma-separadas, la nueva
    primero). Si no está, se usa la clave única habitual."""
    env = os.getenv("SMART_MANAGER_SECRET_KEYS")
    if env:
        return [k.strip().encode() for k in env.split(",") if k.strip()]
    clave = _cargar_o_crear_clave()
    return [clave] if clave else []


def _get_fernet():
    global _fernet, _intentado
    if _fernet is not None or _intentado:
        return _fernet
    _intentado = True
    try:
        from cryptography.fernet import Fernet, MultiFernet
        claves = _claves_rotacion()
        if not claves:
            return None
        fernets = [Fernet(k) for k in claves]
        # MultiFernet permite rotar: cifra con la primera, descifra con cualquiera.
        _fernet = MultiFernet(fernets) if len(fernets) > 1 else fernets[0]
    except Exception as e:
        logger.warning("Cifrado no disponible (cryptography): %s. Los tokens NO se cifrarán.", e)
        _fernet = None
    return _fernet


def rotar(token: str | None) -> str | None:
    """Re-cifra un token con la clave activa (para migrar a una clave nueva tras
    una rotación). Si no parece cifrado o no hay backend, lo devuelve igual."""
    if not parece_cifrado(token):
        return token
    plano = descifrar(token)
    return cifrar(plano) if plano is not None else token


def cifrar(texto: str | None) -> str | None:
    """Cifra un secreto. Devuelve un token cifrado, o uno marcado 'plain:' si no
    hay backend de cifrado (degradación elegante con aviso ya registrado)."""
    if texto is None or texto == "":
        return texto
    f = _get_fernet()
    if f is None:
        return _PLANO_PREFIX + texto
    try:
        return f.encrypt(texto.encode("utf-8")).decode("ascii")
    except Exception as e:
        logger.error("Error cifrando: %s", e)
        return _PLANO_PREFIX + texto


def descifrar(token: str | None) -> str | None:
    """Descifra un token producido por cifrar()."""
    if token is None or token == "":
        return token
    if token.startswith(_PLANO_PREFIX):
        return token[len(_PLANO_PREFIX):]
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(token.encode("ascii")).decode("utf-8")
    except Exception as e:
        logger.error("Error descifrando: %s", e)
        return None


def parece_cifrado(token: str | None) -> bool:
    """True si el valor parece un token producido por `cifrar` (Fernet o 'plain:')."""
    return isinstance(token, str) and (token.startswith("gAAAA") or token.startswith(_PLANO_PREFIX))


def descifrar_seguro(token: str | None) -> str | None:
    """Descifra de forma retrocompatible: si el valor NO parece cifrado, se asume
    que es un secreto legado en claro y se devuelve tal cual (permite migrar sin
    romper lecturas)."""
    if token is None or token == "":
        return token
    if not parece_cifrado(token):
        return token            # secreto legado en claro
    return descifrar(token)


def cifrar_bytes(datos: bytes | None) -> bytes | None:
    """Cifra bytes binarios (p. ej. un PDF completo) con el MISMO backend/clave que `cifrar()` —
    sin esto, forzar un `.encode('utf-8')` sobre contenido binario arbitrario (como hace `cifrar`,
    pensado para secretos de texto) rompería/corrompería el archivo. `None` si no hay backend de
    cifrado disponible (degradación honesta: el llamador decide si guarda el original sin cifrar)."""
    if not datos:
        return datos
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.encrypt(datos)
    except Exception as e:
        logger.error("Error cifrando bytes: %s", e)
        return None


def descifrar_bytes(token: bytes | None) -> bytes | None:
    """Descifra bytes producidos por `cifrar_bytes()`."""
    if not token:
        return token
    f = _get_fernet()
    if f is None:
        return None
    try:
        return f.decrypt(token)
    except Exception as e:
        logger.error("Error descifrando bytes: %s", e)
        return None


_MAGIC_FERNET = b"gAAAAA"  # todo token Fernet (texto o bytes) empieza así — versión 0x80 en base64url


def parece_cifrado_bytes(datos: bytes | None) -> bool:
    """True si `datos` tiene pinta de ser un token Fernet (el mismo prefijo que `parece_cifrado`,
    a nivel de bytes) — permite a un lector genérico (abrir/imprimir/descargar/adjuntar un fichero)
    detectar SOLO los ficheros realmente cifrados por esta app y dejar cualquier otro intacto."""
    return isinstance(datos, (bytes, bytearray)) and bytes(datos[:6]) == _MAGIC_FERNET


def descifrar_bytes_si_cifrado(datos: bytes | None) -> bytes | None:
    """Descifra `datos` SOLO si parecen un token Fernet; si no, los devuelve tal cual (fichero
    legado o nunca cifrado — nunca intenta "descifrar" contenido que no lo está)."""
    if not parece_cifrado_bytes(datos):
        return datos
    descifrado = descifrar_bytes(datos)
    return descifrado if descifrado is not None else datos


def cifrar_archivo_en_disco(ruta: str) -> bool:
    """Cifra EN SITIO el fichero de `ruta` (lee el contenido en claro, lo sustituye por el token
    Fernet) — pensado para "repositorio cifrado" de documentos generados (nóminas/certificados):
    se llama justo después de generar el PDF, antes de registrarlo/subirlo a almacenamiento, así
    tanto la copia local como la réplica en `StorageProvider` (que lee el fichero local tal cual)
    quedan cifradas sin tocar ese segundo chokepoint. Devuelve `True` si quedó cifrado; `False` si
    no hay backend de cifrado disponible o el fichero no existe — en ambos casos el fichero
    original queda intacto (degradación honesta, nunca se pierde el documento)."""
    try:
        if not (ruta and os.path.exists(ruta)):
            return False
        with open(ruta, "rb") as f:
            datos = f.read()
        if parece_cifrado_bytes(datos):
            return True  # ya estaba cifrado (reintento/regeneración) — idempotente
        cifrado = cifrar_bytes(datos)
        if cifrado is None:
            return False
        with open(ruta, "wb") as f:
            f.write(cifrado)
        return True
    except Exception as e:
        logger.error("cifrar_archivo_en_disco(%s): %s", ruta, e)
        return False


def resolver_ruta_legible(ruta: str) -> str:
    """Punto único de lectura para CUALQUIER consumidor de un fichero potencialmente cifrado
    (abrir con la app del sistema, imprimir, descargar, adjuntar a un correo, calcular su hash...):
    si el contenido de `ruta` es un token Fernet, lo descifra a un fichero temporal (mismo nombre/
    extensión, para que el visor del SO lo reconozca) y devuelve esa ruta temporal; si no, devuelve
    `ruta` sin tocar. Quien use el resultado es responsable de que sea una ruta transitoria cuando
    difiere de la original (no se borra aquí para no interrumpir al programa que la vaya a abrir)."""
    try:
        if not (ruta and os.path.isfile(ruta)):
            return ruta
        with open(ruta, "rb") as f:
            datos = f.read()
        if not parece_cifrado_bytes(datos):
            return ruta
        plano = descifrar_bytes(datos)
        if plano is None:
            logger.error("resolver_ruta_legible(%s): no se pudo descifrar", ruta)
            return ruta
        import tempfile
        base = os.path.basename(ruta)
        fd, tmp = tempfile.mkstemp(prefix="sm_dec_", suffix=f"_{base}")
        with os.fdopen(fd, "wb") as f:
            f.write(plano)
        return tmp
    except Exception as e:
        logger.error("resolver_ruta_legible(%s): %s", ruta, e)
        return ruta


def hash_sha256_archivo(ruta: str) -> str | None:
    """SHA-256 del contenido EN CLARO de `ruta` (si el fichero está cifrado en disco, lo descifra
    primero a un temporal) — punto único reutilizado por `db.documentos`/`rrhh.firma_servicio`
    (antes dos implementaciones idénticas) para que el hash ancla SIEMPRE el documento que el
    usuario realmente ve/firma, nunca el blob cifrado."""
    import hashlib
    try:
        legible = resolver_ruta_legible(ruta)
        h = hashlib.sha256()
        with open(legible, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        if legible != ruta:
            try:
                os.remove(legible)
            except OSError:
                pass
        return h.hexdigest()
    except Exception as e:
        logger.warning("hash_sha256_archivo(%s): %s", ruta, e)
        return None


def cifrado_disponible() -> bool:
    """True si hay backend de cifrado real (cryptography + clave)."""
    return _get_fernet() is not None


def claves_raiz() -> list[bytes]:
    """Claves maestras raíz (rotación incluida). Punto de reutilización para
    DERIVAR claves por tenant (HKDF) sin exponer la lógica interna. La primera es
    la activa; el resto sirven para descifrar durante una rotación. Lista vacía si
    no hay backend de cifrado disponible."""
    return _claves_rotacion()
