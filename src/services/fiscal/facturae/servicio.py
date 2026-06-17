"""
Servicio Facturae (C3.4.4) — orquesta generación, firma, evidencia y entrega.

Bajo demanda por factura (DF6): construye el XML desde la venta + emisor + receptor
(DIR3), lo firma (C3.4.3) y lo encola para entrega por canal (FACe). El procesado de
la cola reutiliza el patrón worker SIN tocar el worker congelado de C3.2. Evidencias
(XML firmado + acuse) por el centro documental (C3.2). Multiempresa.
"""

import datetime as _dt
import logging

from src.services.fiscal.facturae import VERSION_DEFECTO, destinatarios, envios
from src.services.fiscal.facturae import facturae_xml as FX
from src.services.fiscal.facturae import firma as _firma

logger = logging.getLogger("fiscal.facturae.servicio")

_MAX_INTENTOS = 8


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def _backoff(intentos):
    return _dt.datetime.now() + _dt.timedelta(minutes=min(2 ** max(0, intentos), 60))


# ── Construcción de datos / XML firmado ──────────────────────────────────────
def _emisor(id_empresa) -> dict:
    from src.db import empresa as emp_db
    i = emp_db.info_documento(id_empresa) or {}
    return {"nif": i.get("cif"), "razon_social": i.get("razon_social") or i.get("nombre"),
            "persona": "J", "residencia": "R", "direccion": i.get("direccion"),
            "cp": i.get("cp"), "municipio": i.get("municipio"), "provincia": i.get("provincia"),
            "cod_pais": "ESP"}


def _receptor(venta, id_empresa):
    """Receptor combinando `clientes` (base) + `facturae_destinatarios` (fiscal/DIR3)."""
    nif = venta.get("cliente_nif")
    base = {}
    try:
        from src.db.clientes import obtener_cliente
        base = obtener_cliente(venta.get("cliente_id")) or {}
    except Exception:
        pass
    nif = nif or base.get("nif")
    dest = destinatarios.obtener(nif, id_empresa) if nif else None
    if not dest:
        return None, (f"Sin datos fiscales/DIR3 del receptor (NIF {nif}); "
                      "configúralos en facturae_destinatarios")
    faltan = destinatarios.validar_para_b2g(dest)
    if faltan:
        return None, "Faltan datos obligatorios del receptor: " + ", ".join(faltan)
    rec = {"nif": nif, "razon_social": dest.get("razon_social") or base.get("nombre"),
           "persona": dest.get("tipo_persona") or "J", "residencia": dest.get("residencia") or "R",
           "direccion": dest.get("direccion"), "cp": dest.get("cp"),
           "municipio": dest.get("municipio"), "provincia": dest.get("provincia"),
           "cod_pais": dest.get("cod_pais") or "ESP"}
    if dest.get("es_aapp"):
        addr = {"direccion": dest.get("direccion"), "cp": dest.get("cp"),
                "municipio": dest.get("municipio"), "provincia": dest.get("provincia")}
        rec["centros"] = [
            {"code": dest.get("dir3_oficina_contable"), "role": "01", "name": "Oficina contable", **addr},
            {"code": dest.get("dir3_organo_gestor"), "role": "02", "name": "Órgano gestor", **addr},
            {"code": dest.get("dir3_unidad_tramitadora"), "role": "03", "name": "Unidad tramitadora", **addr},
        ]
    return rec, None


def construir_firmado(venta_id, id_empresa=None, version=VERSION_DEFECTO):
    """Devuelve (xml_firmado, datos) o (None, error)."""
    id_empresa = _empresa(id_empresa)
    from src.db.ventas_busqueda import obtener_venta_completa
    venta = obtener_venta_completa(venta_id)
    if not venta:
        return None, f"Venta {venta_id} no encontrada"
    emisor = _emisor(id_empresa)
    if not emisor.get("nif"):
        return None, "La empresa no tiene NIF/CIF configurado"
    receptor, err = _receptor(venta, id_empresa)
    if err:
        return None, err
    lineas = [{"descripcion": it.get("nombre"), "cantidad": it.get("cantidad") or 1,
               "subtotal": it.get("subtotal")} for it in venta.get("items", [])]
    if not lineas:
        return None, "La factura no tiene líneas"
    fecha = str(venta.get("fecha") or _dt.date.today())[:10]
    datos = FX.normalizar(emisor, receptor, lineas, numero=str(venta_id), fecha=fecha,
                          id_empresa=id_empresa, version=version)
    xml = FX.facturae_xml(datos)
    from src.services.fiscal import certificados as C
    firmado = _firma.firmar_facturae(xml, C.proveedor_claves(id_empresa))
    if not firmado:
        return None, "No se pudo firmar (sin certificado activo)"
    return firmado, datos


def _evidencia(id_empresa, venta_id, numero, total, clase, contenido):
    try:
        from src.services.fiscal.evidencias import guardar_evidencia
        reg = {"id_empresa": id_empresa, "serie": "FACTURAE", "numero": venta_id,
               "total": total, "referencia": str(numero)}
        return guardar_evidencia(reg, clase, contenido, id_empresa=id_empresa)
    except Exception as e:
        logger.debug("evidencia facturae: %s", e)
        return None


# ── API pública ──────────────────────────────────────────────────────────────
def generar_facturae(venta_id, canal="face", id_empresa=None, version=VERSION_DEFECTO) -> dict:
    """Genera, firma, guarda evidencia y ENCOLA la factura. No envía (eso es la cola)."""
    id_empresa = _empresa(id_empresa)
    firmado, datos = construir_firmado(venta_id, id_empresa, version)
    if not firmado:
        return {"ok": False, "error": datos}        # `datos` es el mensaje de error
    total = datos["totales"]["total"]
    _evidencia(id_empresa, venta_id, datos["numero"], total, "xml", firmado.decode("utf-8"))
    eid = envios.crear(venta_id, datos["numero"], canal=canal, version=version, id_empresa=id_empresa)
    return {"ok": True, "envio_id": eid, "numero": datos["numero"], "total": total}


def canal_para(config: dict):
    """Canal según `config['canal']` (face|faceb2b) con transporte mTLS real si hay
    certificado activo; si no, el canal queda `disponible()=False`."""
    from src.services.fiscal.facturae.emisores.face import CanalFACe
    from src.services.fiscal.facturae.emisores.faceb2b import CanalFACeB2B
    clases = {"face": CanalFACe, "faceb2b": CanalFACeB2B}
    clase = clases.get((config or {}).get("canal", "face"), CanalFACe)
    transporte = None
    try:
        from src.services.fiscal import certificados as C
        from src.services.fiscal.emisores.tls import transporte_mtls
        prov = C.proveedor_claves((config or {}).get("id_empresa"))
        if prov is not None:
            transporte = transporte_mtls(prov)
    except Exception as e:
        logger.debug("canal_para transporte: %s", e)
    return clase(transporte=transporte, config=config)


def procesar_envios_facturae(id_empresa=None, canal=None, limite=50) -> dict:
    """Procesa envíos pendientes listos (rebuild+firma+entrega). Idempotente + backoff.
    No toca el worker congelado. Devuelve {enviados, en_espera, errores, vistos}."""
    from src.db import fiscal as _f  # solo para config/entorno
    id_empresa = _empresa(id_empresa)
    res = {"enviados": 0, "en_espera": 0, "errores": 0, "vistos": 0}
    entorno = _f.obtener_config(id_empresa).get("entorno", "preproduccion")
    cfg = {"id_empresa": id_empresa, "entorno": entorno}
    for env in envios.listar("pendiente", id_empresa=id_empresa, listos=True, limite=limite):
        res["vistos"] += 1
        eid, intentos = env["id"], int(env.get("intentos") or 0)
        # Canal: el inyectado (tests) o el resuelto por el canal de cada envío.
        canal_env = canal if canal is not None else canal_para({**cfg, "canal": env.get("canal", "face")})
        try:
            if not canal_env.disponible():
                envios.actualizar(eid, "pendiente", error="canal no disponible (sin certificado)",
                                  proximo_intento=_backoff(intentos))
                res["en_espera"] += 1
                continue
            firmado, datos = construir_firmado(env["venta_id"], id_empresa, env.get("version") or VERSION_DEFECTO)
            if not firmado:
                envios.actualizar(eid, "error" if intentos + 1 >= _MAX_INTENTOS else "pendiente",
                                  error=datos, proximo_intento=_backoff(intentos))
                res["errores" if intentos + 1 >= _MAX_INTENTOS else "en_espera"] += 1
                continue
            r = canal_env.enviar(firmado, datos, cfg)
            self_total = datos["totales"]["total"]
            if r.get("ok"):
                envios.actualizar(eid, "enviado", numero_registro=r.get("numero_registro"), csv=r.get("csv"))
                _evidencia(id_empresa, env["venta_id"], datos["numero"], self_total, "acuse",
                           f"numeroRegistro={r.get('numero_registro')} csv={r.get('csv')}")
                res["enviados"] += 1
            elif intentos + 1 >= _MAX_INTENTOS:
                envios.actualizar(eid, "error", error=r.get("mensaje"))
                res["errores"] += 1
            else:
                envios.actualizar(eid, "pendiente", error=r.get("mensaje"), proximo_intento=_backoff(intentos))
                res["en_espera"] += 1
        except Exception as e:
            logger.warning("procesar_envios_facturae(env=%s): %s", eid, e)
            envios.actualizar(eid, "pendiente", error=str(e), proximo_intento=_backoff(intentos))
            res["en_espera"] += 1
    return res
