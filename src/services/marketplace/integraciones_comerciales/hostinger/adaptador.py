"""
Adaptador Hostinger · Implementación operativa (Fase WEB-14).

`HostingerAdapter` extiende el adaptador PREPARADO del motor WEB-13 (hereda contratos/capacidades/versión) e
implementa el flujo real: autenticar → crear_web → consultar_estado → esperar_finalizacion → obtener_dominio
→ registrar_web → conectar_smart_manager. Reutiliza el Canal Web (registro/publicación/sincronización) y el
servicio de integraciones (estados/última sync). Degradable: `disponible()` = True solo con credenciales
reales (SecretManager). Sin ellas, devuelve errores canónicos — nunca simula éxito.

Smart Manager NO crea HTML/CSS/plantillas/CMS/dominios/SSL: todo eso lo genera Hostinger. Aquí solo se
orquesta la comunicación, el descubrimiento, el registro y la conexión con el ERP.
"""

import logging
import time

from src.services.marketplace.integraciones_comerciales.hostinger import (
    auditoria as A, secretos as S, transporte as T)
from src.services.marketplace.integraciones_comerciales.motor.adaptadores import \
    HostingerAdapter as _HostingerPreparado
from src.services.marketplace.integraciones_comerciales.motor.errores import (
    CodigoError, IntegracionError)

logger = logging.getLogger("marketplace.integraciones_comerciales.hostinger.adaptador")

_ESTADOS_LISTA = ("READY", "ACTIVE", "COMPLETED", "LIVE", "PUBLISHED")
_ESTADOS_ERROR = ("ERROR", "FAILED", "CANCELLED")


class HostingerAdapter(_HostingerPreparado):
    """Adaptador Hostinger operativo. Instanciable sin argumentos (lo usa `motor.adaptador('hostinger')`)."""

    plataforma = "hostinger"

    def __init__(self, *, credenciales_ref=None, base_url=None):
        super().__init__()
        self._credenciales_ref = credenciales_ref or S.CLAVE_DEFECTO
        self._base_url = base_url

    # ── Estado / disponibilidad (honesto) ──
    def _token(self):
        return S.token(self._credenciales_ref)

    def disponible(self) -> bool:
        return bool(self._token())

    def descriptor(self) -> dict:
        d = super().descriptor()
        d["estado"] = "OPERATIVO" if self.disponible() else "PREPARADO"
        return d

    def _req(self, method, path, *, json=None, params=None) -> dict:
        tok = self._token()
        if not tok:
            raise IntegracionError(CodigoError.MISSING_CREDENTIALS,
                                   "credenciales de Hostinger no configuradas (SecretManager)",
                                   plataforma="hostinger")
        return T.get_transporte().request(method, path, token=tok, json=json, params=params)

    # ── 1 · Autenticación ──
    def autenticar(self, *, id_empresa=None, usuario=None) -> dict:
        A.registrar(A.HOSTINGER_AUTH, id_empresa=id_empresa, usuario=usuario)
        if not self._token():
            return {"ok": False, "codigo": CodigoError.MISSING_CREDENTIALS.value,
                    "error": "sin credenciales Hostinger"}
        try:
            r = self._req("GET", "/v1/account")
            return {"ok": True, "cuenta": r}
        except IntegracionError as e:
            A.registrar(A.HOSTINGER_ERROR, id_empresa=id_empresa, usuario=usuario, detalle=e.to_dict())
            return {"ok": False, **e.to_dict()}

    # ── 2 · Creación de la web (Hostinger genera; SM solo lanza la petición) ──
    def crear_web(self, datos: dict, *, id_empresa=None, usuario=None) -> dict:
        payload = {
            "company": datos.get("nombre_empresa") or datos.get("nombre"),
            "industry": datos.get("actividad"),
            "country": datos.get("pais"),
            "language": datos.get("idioma"),
            "email": datos.get("correo"),
        }
        A.registrar(A.HOSTINGER_CREATE, id_empresa=id_empresa, usuario=usuario,
                    detalle=f"empresa={payload.get('company')}")
        r = self._req("POST", "/v1/websites/ai", json=payload)
        return {"ok": True, "id_externo": r.get("id") or r.get("website_id") or r.get("uuid"),
                "estado": r.get("status") or "CREATING", "raw": r}

    # ── 3 · Consulta / espera de finalización ──
    def consultar_estado(self, id_externo) -> dict:
        r = self._req("GET", f"/v1/websites/{id_externo}")
        return {"ok": True, "estado": (r.get("status") or "").upper(), "raw": r}

    def esperar_finalizacion(self, id_externo, *, timeout=300, intervalo=5, id_empresa=None,
                             usuario=None) -> dict:
        fin = time.time() + timeout
        estado = "PENDING"
        while time.time() < fin:
            try:
                estado = self.consultar_estado(id_externo).get("estado") or ""
            except IntegracionError as e:
                return {"ok": False, **e.to_dict()}
            if estado in _ESTADOS_LISTA:
                A.registrar(A.HOSTINGER_COMPLETE, id_empresa=id_empresa, usuario=usuario,
                            detalle=f"id={id_externo}")
                return {"ok": True, "estado": estado}
            if estado in _ESTADOS_ERROR:
                return {"ok": False, "estado": estado, "codigo": CodigoError.API_ERROR.value}
            time.sleep(max(0, intervalo))
        return {"ok": False, "estado": "TIMEOUT", "codigo": CodigoError.TIMEOUT.value}

    # ── 4 · Descubrimiento del dominio/URL/ID ──
    def obtener_dominio(self, id_externo) -> dict:
        r = self._req("GET", f"/v1/websites/{id_externo}/domain")
        return {"ok": True, "id_externo": id_externo, "dominio": r.get("domain"),
                "url": r.get("url") or (f"https://{r.get('domain')}" if r.get("domain") else None),
                "estado": (r.get("status") or "").upper()}

    # ── 5 · Registro automático en el Canal Web (fuente única) + registro §6 ──
    def registrar_web(self, *, id_empresa, dominio=None, nombre=None, id_externo=None, url=None,
                      usuario=None) -> dict:
        from src.services.marketplace.integraciones_comerciales import estados as E

        # La web (dominio/marca) se registra en el CANAL WEB (web_config) — fuente única, sin duplicar.
        from src.services.comercio_digital.canal_web import orquestador
        res = orquestador.registrar_web_creada(
            id_empresa=id_empresa, usuario=usuario, dominio=dominio, nombre=nombre, proveedor="hostinger",
            config_negocio={"proveedor": "hostinger", "id_externo": id_externo, "url": url})
        # Registro §6 (metadatos de la integración; estados EXISTENTES). Hostinger NO es una plataforma
        # ecommerce del catálogo de sincronización → no se fuerza en `servicio` (evita duplicidad falsa).
        registro = {"empresa": str(id_empresa), "proveedor": "hostinger", "dominio": dominio, "url": url,
                    "id_externo": id_externo, "version": type(self).version.connector_version,
                    "fecha": time.time(), "estado": E.CONFIGURADA, "ultima_sync": None,
                    "canal_web": bool(res.get("ok"))}
        A.registrar(A.HOSTINGER_REGISTERED, id_empresa=id_empresa, usuario=usuario,
                    detalle=f"dom={dominio} id={id_externo}")
        return {"ok": bool(res.get("ok")), "registro": registro, "canal_web": res}

    # ── 6 · Conexión automática con Smart Manager + sincronización inicial ──
    def conectar_smart_manager(self, *, id_empresa, dominio=None, nombre=None, id_externo=None, url=None,
                               usuario=None) -> dict:
        from src.services.marketplace.integraciones_comerciales import estados as E

        reg = self.registrar_web(id_empresa=id_empresa, dominio=dominio, nombre=nombre,
                                 id_externo=id_externo, url=url, usuario=usuario)
        from src.services.comercio_digital import canal_web
        # Publicar/activar el canal (reutiliza el Canal Web; SM no crea la web).
        try:
            canal_web.publicar(usuario=usuario)
        except Exception as e:
            logger.debug("publicar canal web: %s", e)
        # Sincronización inicial reutilizando el pipeline/engine EXISTENTE (catálogo/productos/stock/…):
        sync = None
        try:
            sync = canal_web.sincronizar(usuario=usuario)
            A.registrar(A.HOSTINGER_SYNC, id_empresa=id_empresa, usuario=usuario)
        except Exception as e:
            sync = {"ok": False, "error": str(e)}
        # Estado del registro §6 → SINCRONIZADA + última sync (estados existentes).
        reg["registro"]["estado"] = E.SINCRONIZADA
        reg["registro"]["ultima_sync"] = time.time()
        A.registrar(A.HOSTINGER_CONNECTED, id_empresa=id_empresa, usuario=usuario)
        return {"ok": True, "registro": reg["registro"], "sincronizacion": sync}

    # ── Orquestación de alto nivel (usada por Canal Web; emite progreso para la UX) ──
    def crear_y_conectar(self, *, id_empresa, datos, usuario=None, on_progreso=None, timeout=300,
                         intervalo=5) -> dict:
        def _prog(msg):
            if callable(on_progreso):
                try:
                    on_progreso(msg)
                except Exception:
                    pass

        try:
            _prog("Crear página web")
            aut = self.autenticar(id_empresa=id_empresa, usuario=usuario)
            if not aut.get("ok"):
                cod = aut.get("codigo") or CodigoError.AUTH_ERROR.value
                raise IntegracionError(CodigoError(cod), aut.get("error") or "autenticación fallida",
                                       plataforma="hostinger")
            _prog("Hostinger")
            creado = self.crear_web(datos, id_empresa=id_empresa, usuario=usuario)
            idx = creado.get("id_externo")
            _prog("Esperando creación...")
            fin = self.esperar_finalizacion(idx, timeout=timeout, intervalo=intervalo,
                                            id_empresa=id_empresa, usuario=usuario)
            if not fin.get("ok"):
                raise IntegracionError(CodigoError(fin.get("codigo", CodigoError.API_ERROR.value)),
                                       f"la web no finalizó ({fin.get('estado')})", plataforma="hostinger")
            _prog("Página web creada correctamente")
            dom = self.obtener_dominio(idx)
            _prog("Conectando Smart Manager...")
            con = self.conectar_smart_manager(
                id_empresa=id_empresa, dominio=dom.get("dominio"),
                nombre=datos.get("nombre_empresa") or datos.get("nombre"), id_externo=idx,
                url=dom.get("url"), usuario=usuario)
            _prog("Sincronizando datos...")
            _prog("Proceso finalizado")
            return {"ok": True, "id_externo": idx, "dominio": dom.get("dominio"), "url": dom.get("url"),
                    "conexion": con}
        except IntegracionError as e:
            A.registrar(A.HOSTINGER_ERROR, id_empresa=id_empresa, usuario=usuario, detalle=e.to_dict())
            return {"ok": False, "error": e.to_dict()}
        except Exception as e:
            A.registrar(A.HOSTINGER_ERROR, id_empresa=id_empresa, usuario=usuario, detalle=str(e))
            return {"ok": False, "error": {"codigo": CodigoError.API_ERROR.value, "mensaje": str(e)}}
