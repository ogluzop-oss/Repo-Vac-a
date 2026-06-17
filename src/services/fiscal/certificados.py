"""
Custodia de certificados fiscales (C3.5.1).

Importa, valida y CUSTODIA certificados PKCS#12 por empresa. El material va SIEMPRE
cifrado (decisión D2/D4: blob cifrado en BD, clave derivada por tenant), nunca en
disco ni en claro (D3). Expone un `ProveedorClaves` (ClavesLocales) para TLS/firma.

Multiempresa: todo cuelga de `id_empresa` (TenantContext). Soporta historial,
activación/sustitución, revocación, caducidad y re-cifrado (rotación de clave).
NO toca el núcleo C3.2 ni el resto de tablas fiscales.
"""

import datetime as _dt
import hashlib
import json
import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
from src.services.fiscal import cripto_tenant

logger = logging.getLogger("fiscal.certificados")

ESTADOS = ("activo", "inactivo", "revocado", "caducado")
TIPOS = ("sello", "representante")          # D5: sello de empresa es el principal


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _auditar(id_empresa, id_cert, accion, detalle=None):
    """Registra un evento del ciclo de vida del certificado (trazabilidad SaaS)."""
    id_usuario, usuario = None, None
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        id_usuario = u.get("id")
        usuario = u.get("nombre") or u.get("usuario")
    except Exception:
        pass
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fiscal_certificados_auditoria "
                "(id_empresa, id_certificado, accion, detalle, id_usuario, usuario) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_cert, accion, (detalle or "")[:255], id_usuario, usuario))
            conn.commit()
    except Exception as e:
        logger.debug("No se pudo auditar (%s/%s): %s", accion, id_cert, e)


def listar_auditoria(id_empresa=None, limite=200) -> list:
    """Rastro de auditoría de certificados de la empresa (más reciente primero)."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_certificados_auditoria WHERE id_empresa=%s "
                        "ORDER BY id DESC LIMIT %s", (id_empresa, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_auditoria: %s", e)
        return []


# ── Validación / extracción de metadatos del PKCS#12 ─────────────────────────
def _nif_de_cert(cert) -> str | None:
    """Extrae el NIF del titular del certificado (serialNumber del subject, sin
    prefijos tipo 'IDCES-'/'VATES-'). Best-effort. ⚠️[afinar con certs reales]."""
    try:
        from cryptography.x509.oid import NameOID
        for attr in cert.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER):
            v = attr.value
            for pref in ("IDCES-", "VATES-", "ES-", "ES"):
                if v.upper().startswith(pref):
                    v = v[len(pref):]
                    break
            return v
    except Exception:
        pass
    return None


def inspeccionar_pkcs12(p12_bytes: bytes, password: str) -> dict:
    """Carga y valida el PKCS#12 (en memoria) → metadatos. Lanza si es inválido."""
    from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
    pw = password.encode("utf-8") if password else None
    key, cert, _extra = pkcs12.load_key_and_certificates(p12_bytes, pw)
    if key is None or cert is None:
        raise ValueError("PKCS#12 sin clave privada o sin certificado")
    huella = hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()
    return {
        "titular_nif": _nif_de_cert(cert),
        "ca_emisora": cert.issuer.rfc4514_string()[:255],
        "num_serie": format(cert.serial_number, "x")[:80],
        "valido_desde": cert.not_valid_before_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "valido_hasta": cert.not_valid_after_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "huella_cert": huella,
    }


# ── Custodia (alta, listado, activación, revocación, rotación) ────────────────
def importar(p12_bytes: bytes, password: str, id_empresa=None, alias=None,
             tipo="sello", activar=True) -> dict | None:
    """Importa un PKCS#12: valida, extrae metadatos, CIFRA el material por tenant y
    lo guarda. Si `activar`, deja este como único activo. Devuelve metadatos+id."""
    id_empresa = _empresa(id_empresa)
    if tipo not in TIPOS:
        tipo = "sello"
    try:
        meta = inspeccionar_pkcs12(p12_bytes, password)
    except Exception as e:
        logger.error("PKCS#12 inválido: %s", e)
        return None
    material = cripto_tenant.cifrar(
        json.dumps({"p12": _b64(p12_bytes), "password": password or ""}).encode("utf-8"),
        id_empresa)
    if material is None:
        logger.error("No se pudo cifrar el material del certificado")
        return None
    caducado = _caducado(meta["valido_hasta"])
    estado = ("caducado" if caducado else ("activo" if activar else "inactivo"))
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if activar and not caducado:
                cur.execute("UPDATE fiscal_certificados SET estado='inactivo' "
                            "WHERE id_empresa=%s AND estado='activo'", (id_empresa,))
            cur.execute(
                "INSERT INTO fiscal_certificados (id_empresa, alias, tipo, titular_nif, "
                "ca_emisora, num_serie, valido_desde, valido_hasta, huella_cert, "
                "material_cifrado, estado) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, alias, tipo, meta["titular_nif"], meta["ca_emisora"],
                 meta["num_serie"], meta["valido_desde"], meta["valido_hasta"],
                 meta["huella_cert"], material, estado))
            cid = cur.lastrowid
            conn.commit()
        meta.update({"id": cid, "id_empresa": id_empresa, "alias": alias, "tipo": tipo,
                     "estado": estado})
        _auditar(id_empresa, cid, "importar", f"alias={alias} nif={meta.get('titular_nif')}")
        logger.info("Certificado importado (empresa=%s, id=%s, estado=%s)", id_empresa, cid, estado)
        return meta
    except Exception as e:
        logger.error("Error importando certificado: %s", e)
        return None


def listar(id_empresa=None, incluir_revocados=True) -> list:
    """Historial de certificados de la empresa (metadatos, SIN material)."""
    id_empresa = _empresa(id_empresa)
    sql = ("SELECT id, id_empresa, alias, tipo, titular_nif, ca_emisora, num_serie, "
           "valido_desde, valido_hasta, huella_cert, estado, fecha "
           "FROM fiscal_certificados WHERE id_empresa=%s")
    params = [id_empresa]
    if not incluir_revocados:
        sql += " AND estado<>'revocado'"
    sql += " ORDER BY id DESC"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar certificados: %s", e)
        return []


def _fila(id_cert, id_empresa, con_material=False):
    cols = "*" if con_material else ("id, id_empresa, alias, tipo, titular_nif, estado, "
                                     "valido_hasta, huella_cert")
    with obtener_conexion() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT {cols} FROM fiscal_certificados WHERE id=%s AND id_empresa=%s",
                    (id_cert, id_empresa))
        r = cur.fetchone()
        return _filas_a_dicts(cur, [r])[0] if r else None


def obtener_activo(id_empresa=None) -> dict | None:
    """Metadatos del certificado ACTIVO vigente de la empresa (sin material).
    Marca como 'caducado' si pasó la validez."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, id_empresa, alias, tipo, titular_nif, valido_hasta, "
                        "huella_cert, estado FROM fiscal_certificados "
                        "WHERE id_empresa=%s AND estado='activo' ORDER BY id DESC LIMIT 1",
                        (id_empresa,))
            r = cur.fetchone()
            meta = _filas_a_dicts(cur, [r])[0] if r else None
        if meta and _caducado(meta.get("valido_hasta")):
            actualizar_estado(meta["id"], "caducado", id_empresa)
            return None
        return meta
    except Exception as e:
        logger.error("obtener_activo: %s", e)
        return None


def actualizar_estado(id_cert, estado, id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    if estado not in ESTADOS:
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_certificados SET estado=%s WHERE id=%s AND id_empresa=%s",
                        (estado, id_cert, id_empresa))
            afectadas = cur.rowcount
            conn.commit()
        return afectadas > 0          # False si el cert no es de esta empresa (frontera tenant)
    except Exception as e:
        logger.error("actualizar_estado cert(%s): %s", id_cert, e)
        return False


def activar(id_cert, id_empresa=None) -> bool:
    """Activa un certificado (sustitución): desactiva el anterior activo."""
    id_empresa = _empresa(id_empresa)
    meta = _fila(id_cert, id_empresa)
    if not meta or meta["estado"] == "revocado":
        return False
    if _caducado(meta.get("valido_hasta")):
        actualizar_estado(id_cert, "caducado", id_empresa)
        return False
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_certificados SET estado='inactivo' "
                        "WHERE id_empresa=%s AND estado='activo'", (id_empresa,))
            cur.execute("UPDATE fiscal_certificados SET estado='activo' "
                        "WHERE id=%s AND id_empresa=%s", (id_cert, id_empresa))
            conn.commit()
        _auditar(id_empresa, id_cert, "activar")
        return True
    except Exception as e:
        logger.error("activar cert(%s): %s", id_cert, e)
        return False


def revocar(id_cert, id_empresa=None) -> bool:
    """Revoca (sustitución/baja). Irreversible a 'activo' sin reimportar."""
    id_empresa = _empresa(id_empresa)
    ok = actualizar_estado(id_cert, "revocado", id_empresa)
    if ok:
        _auditar(id_empresa, id_cert, "revocar")
    return ok


def rotar_cifrado(id_empresa=None) -> int:
    """Re-cifra el material de todos los certificados de la empresa con la clave
    derivada activa (tras una rotación de la clave maestra). Devuelve nº re-cifrados."""
    id_empresa = _empresa(id_empresa)
    n = 0
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, material_cifrado FROM fiscal_certificados WHERE id_empresa=%s",
                        (id_empresa,))
            filas = _filas_a_dicts(cur, cur.fetchall())
            for f in filas:
                nuevo = cripto_tenant.recifrar(f["material_cifrado"], id_empresa)
                if nuevo and nuevo != f["material_cifrado"]:
                    cur.execute("UPDATE fiscal_certificados SET material_cifrado=%s WHERE id=%s",
                                (nuevo, f["id"]))
                    n += 1
            conn.commit()
        if n:
            _auditar(id_empresa, None, "rotar", f"recifrados={n}")
    except Exception as e:
        logger.error("rotar_cifrado: %s", e)
    return n


def proveedor_claves(id_empresa=None):
    """`ClavesLocales` del certificado ACTIVO de la empresa (material descifrado en
    memoria). None si no hay certificado activo/vigente o falla el descifrado."""
    from src.services.fiscal.claves import ClavesLocales
    id_empresa = _empresa(id_empresa)
    meta = obtener_activo(id_empresa)
    if not meta:
        return None
    fila = _fila(meta["id"], id_empresa, con_material=True)
    datos = cripto_tenant.descifrar(fila["material_cifrado"], id_empresa)
    if not datos:
        return None
    try:
        j = json.loads(datos.decode("utf-8"))
        return ClavesLocales(_b64d(j["p12"]), j.get("password") or "", metadatos=meta)
    except Exception as e:
        logger.error("proveedor_claves: %s", e)
        return None


# ── Caducidad / alertas ──────────────────────────────────────────────────────
def _caducado(valido_hasta) -> bool:
    d = _a_fecha(valido_hasta)
    return bool(d and d < _dt.datetime.now())


def dias_para_caducar(id_empresa=None) -> int | None:
    meta = obtener_activo(id_empresa)
    d = _a_fecha(meta.get("valido_hasta")) if meta else None
    return (d - _dt.datetime.now()).days if d else None


def _a_fecha(v):
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return _dt.datetime.strptime(v[:19], fmt)
            except ValueError:
                continue
    return None


def _b64(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    import base64
    return base64.b64decode(s)
