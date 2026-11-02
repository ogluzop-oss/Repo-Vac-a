"""
Firma criptográfica de documentos RRHH (F4.11, ampliación — petición explícita: "firmar de forma
telemática documentos corporativos, anexos de contrato, políticas internas de seguridad o
recepción de equipos PRL"). Firma el HASH SHA-256 ya anclado por `firma_servicio` (RSA-PSS/SHA-256)
con una clave propia de RRHH generada POR EMPRESA — NUNCA el certificado fiscal de AEAT
(`services/fiscal/certificados.py`), que es un dominio legal distinto (firma tributaria, no
documental laboral). La clave privada se cifra en reposo con el MISMO motor que ya protege tokens
OAuth e IBANes (`utils.cripto`), sin ningún backend de cifrado paralelo.

Honestidad (evitar sobreprometer validez legal): esto es una firma electrónica EN LA CASA —
autenticación del firmante (login + acción explícita de aceptar), integridad del documento (hash
SHA-256 ya existente), firma criptográfica no repudiable (clave privada nunca sale del servidor) y
traza de auditoría inmutable (`rrhh_doc_auditoria`: usuario, IP, fecha). Es, como mucho, una firma
electrónica AVANZADA en el sentido de eIDAS — NO una firma CUALIFICADA (eso exige un certificado
emitido por un prestador de confianza cualificado/QTSP, que esta app no emite). No afirmar lo
contrario de cara al usuario final.
"""

import base64
import logging

from src.db.conexion import obtener_conexion, transaccion

logger = logging.getLogger("rrhh.firma_cripto")

_TAMANO_CLAVE = 2048


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _generar_par_claves():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=_TAMANO_CLAVE)


def _serializar_privada(clave) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())


def _serializar_publica(clave) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return clave.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)


def _cargar_privada(pem: bytes):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(pem, password=None)


def _cargar_publica(pem: bytes):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_public_key(pem)


def _obtener_o_crear_claves(id_empresa) -> tuple | None:
    """(clave_privada, clave_publica_pem_str) de la empresa — las genera la primera vez que se
    necesitan (lazy, como el resto de claves/certificados de la app) y las persiste cifradas. `None`
    si `cryptography` no está disponible (degradación honesta, igual que `utils.cripto`)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT clave_privada_cifrada, clave_publica FROM rrhh_firma_claves "
                        "WHERE id_empresa=%s", (id_empresa,))
            fila = cur.fetchone()
        if fila:
            from src.utils import cripto
            pem_priv = cripto.descifrar_seguro(fila[0])
            if pem_priv is None:
                logger.error("_obtener_o_crear_claves(%s): no se pudo descifrar la clave privada", id_empresa)
                return None
            return _cargar_privada(pem_priv.encode("utf-8")), fila[1]
        clave = _generar_par_claves()
        pem_priv = _serializar_privada(clave).decode("utf-8")
        pem_pub = _serializar_publica(clave).decode("utf-8")
        from src.utils import cripto
        with transaccion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO rrhh_firma_claves (id_empresa, clave_privada_cifrada, "
                        "clave_publica) VALUES (%s,%s,%s)",
                        (id_empresa, cripto.cifrar(pem_priv), pem_pub))
        return clave, pem_pub
    except Exception as e:
        logger.error("_obtener_o_crear_claves(%s): %s", id_empresa, e)
        return None


def firmar_hash(hash_hex: str, *, id_empresa=None) -> str | None:
    """Firma (RSA-PSS/SHA-256) el hash SHA-256 (hex) ya anclado del documento. Devuelve la firma
    en base64, o `None` si no hay backend de firma disponible — nunca lanza (best-effort, igual que
    el resto del sistema de firma documental)."""
    id_empresa = _emp(id_empresa)
    if not (hash_hex and id_empresa):
        return None
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        par = _obtener_o_crear_claves(id_empresa)
        if not par:
            return None
        clave_privada, _ = par
        firma = clave_privada.sign(
            bytes.fromhex(hash_hex),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
        return base64.b64encode(firma).decode("ascii")
    except Exception as e:
        logger.warning("firmar_hash: %s", e)
        return None


def verificar_firma(hash_hex: str, firma_b64: str, *, id_empresa=None) -> bool:
    """Verifica una firma ya emitida contra la clave pública de la empresa — para auditorías/
    verificación externa del documento, sin necesitar la clave privada."""
    id_empresa = _emp(id_empresa)
    if not (hash_hex and firma_b64 and id_empresa):
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        par = _obtener_o_crear_claves(id_empresa)
        if not par:
            return False
        _, pem_pub = par
        clave_publica = _cargar_publica(pem_pub.encode("utf-8"))
        clave_publica.verify(
            base64.b64decode(firma_b64), bytes.fromhex(hash_hex),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
        return True
    except InvalidSignature:
        return False
    except Exception as e:
        logger.warning("verificar_firma: %s", e)
        return False
