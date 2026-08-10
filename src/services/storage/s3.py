"""
Backend S3 de storage (Fase 10) — PREPARADO, degradable. Usa `boto3` de forma PEREZOSA: si boto3 no está
instalado o no hay credenciales/bucket, la construcción falla de forma explícita y el factory NO cae a S3.
NUNCA se declara operativo sin un bucket real. Hereda TODO el aislamiento multi-tenant de la clase base
(clave `tenant/{id_empresa}/…`); las URLs prefirmadas de S3 sólo se emiten tras la validación de la base.

Requiere (cuando exista AWS): `S3_BUCKET`, `AWS_REGION` (y credenciales vía IAM Role / Task Role, NUNCA en
Git). Cifrado en reposo: SSE-S3 o SSE-KMS (`S3_SSE`, `S3_KMS_KEY_ID`). Ver ARQUITECTURA_S3_MULTI_TENANT.md.
"""

import logging
import os

from src.services.storage.base import StorageError, StorageProvider

logger = logging.getLogger("storage.s3")


def boto3_disponible() -> bool:
    try:
        import boto3  # noqa: F401
        return True
    except Exception:
        return False


class S3StorageProvider(StorageProvider):
    nombre = "s3"

    def __init__(self, bucket=None, region=None, *, prefijo=None, endpoint_url=None):
        if not boto3_disponible():
            raise StorageError("boto3 no instalado: backend S3 no disponible (PREPARADO, no operativo)")
        self._bucket = bucket or os.getenv("S3_BUCKET")
        if not self._bucket:
            raise StorageError("S3_BUCKET no configurado")
        self._region = region or os.getenv("AWS_REGION")
        self._prefijo = (prefijo or os.getenv("S3_PREFIX") or "").strip("/")
        self._endpoint = endpoint_url or os.getenv("AWS_ENDPOINT_URL") or None
        self._sse = os.getenv("S3_SSE")                 # 'AES256' | 'aws:kms'
        self._kms = os.getenv("S3_KMS_KEY_ID")
        import boto3
        # Credenciales resueltas por la cadena estándar (IAM Role / Task Role / entorno). Sin claves en código.
        self._c = boto3.client("s3", region_name=self._region, endpoint_url=self._endpoint)

    def _key(self, clave) -> str:
        return f"{self._prefijo}/{clave}" if self._prefijo else clave

    def _extra(self, content_type=None) -> dict:
        e = {}
        if content_type:
            e["ContentType"] = content_type
        if self._sse == "aws:kms":
            e["ServerSideEncryption"] = "aws:kms"
            if self._kms:
                e["SSEKMSKeyId"] = self._kms
        elif self._sse:
            e["ServerSideEncryption"] = self._sse
        return e

    def _put_raw(self, clave, datos, *, content_type=None):
        self._c.put_object(Bucket=self._bucket, Key=self._key(clave),
                           Body=datos if isinstance(datos, (bytes, bytearray)) else str(datos).encode(),
                           **self._extra(content_type))

    def _get_raw(self, clave):
        r = self._c.get_object(Bucket=self._bucket, Key=self._key(clave))
        return r["Body"].read()

    def _exists_raw(self, clave):
        try:
            self._c.head_object(Bucket=self._bucket, Key=self._key(clave))
            return True
        except Exception:
            return False

    def _delete_raw(self, clave):
        self._c.delete_object(Bucket=self._bucket, Key=self._key(clave))
        return True

    def _meta_raw(self, clave):
        r = self._c.head_object(Bucket=self._bucket, Key=self._key(clave))
        return {"clave": clave, "tamano": r.get("ContentLength"), "modificado": str(r.get("LastModified")),
                "backend": "s3"}

    def _list_raw(self, prefijo):
        out, token = [], None
        while True:
            kw = {"Bucket": self._bucket, "Prefix": self._key(prefijo)}
            if token:
                kw["ContinuationToken"] = token
            r = self._c.list_objects_v2(**kw)
            for o in r.get("Contents", []):
                k = o["Key"]
                out.append(k[len(self._prefijo) + 1:] if self._prefijo else k)
            if not r.get("IsTruncated"):
                break
            token = r.get("NextContinuationToken")
        return out

    def _signed_url_raw(self, clave, *, segundos):
        return self._c.generate_presigned_url(
            "get_object", Params={"Bucket": self._bucket, "Key": self._key(clave)}, ExpiresIn=int(segundos))
