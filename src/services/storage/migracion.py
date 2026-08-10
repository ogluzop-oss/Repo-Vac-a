"""
Migración SEGURA de storage LOCAL → S3 (Fase 10, Fase 3 del plan). Progresiva y NO destructiva: copia,
verifica por checksum y NUNCA borra los ficheros locales automáticamente. Reutiliza los proveedores existentes
(no accede a AWS por su cuenta). Si S3 no está disponible, informa y no hace nada (no simula).
"""

import hashlib
import logging

logger = logging.getLogger("storage.migracion")


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def migrar_local_a_s3(id_empresa, *, tipo=None, dry_run=True) -> dict:
    """Migra los objetos de un tenant del backend local a S3, verificando integridad. `dry_run=True` sólo
    reporta. Devuelve un informe con conteos, checksums verificados, duplicados y errores. NO borra local."""
    from src.services.storage.local import LocalStorageProvider
    origen = LocalStorageProvider()
    informe = {"id_empresa": str(id_empresa), "dry_run": dry_run, "copiados": 0, "verificados": 0,
               "ya_existian": 0, "errores": [], "total": 0}
    try:
        from src.services.storage.s3 import S3StorageProvider, boto3_disponible
        if not boto3_disponible():
            informe["errores"].append("boto3/S3 no disponible: migración PREPARADA, no ejecutable aquí")
            return informe
        destino = None if dry_run else S3StorageProvider()
    except Exception as e:
        informe["errores"].append(f"S3 no disponible: {e}")
        return informe

    claves = origen.listar(id_empresa, tipo)
    informe["total"] = len(claves)
    for clave in claves:
        try:
            datos = origen.leer(id_empresa, clave)
            h_local = _sha(datos)
            if dry_run:
                informe["copiados"] += 1
                continue
            if destino.existe(id_empresa, clave):
                # Verifica que el objeto remoto coincide (idempotencia); si difiere, es un error, no se pisa.
                if _sha(destino.leer(id_empresa, clave)) == h_local:
                    informe["ya_existian"] += 1
                    continue
                informe["errores"].append(f"{clave}: checksum distinto en destino (no sobrescrito)")
                continue
            tipo_c, nombre_c = clave.split("/")[-2], clave.split("/")[-1]
            destino.guardar(id_empresa, tipo_c, nombre_c, datos)
            if _sha(destino.leer(id_empresa, clave)) == h_local:
                informe["copiados"] += 1
                informe["verificados"] += 1
            else:
                informe["errores"].append(f"{clave}: checksum NO verificado tras copiar")
        except Exception as e:
            informe["errores"].append(f"{clave}: {e}")
    logger.info("migracion tenant=%s copiados=%s errores=%s", id_empresa, informe["copiados"],
                len(informe["errores"]))
    return informe
