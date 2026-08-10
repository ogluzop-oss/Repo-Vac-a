"""
Comprension de lenguaje natural del Copiloto (Paquete Enterprise 5, SUBFASE 5.2). Detecta
intencion, dominio, periodo, si es una accion y si es un seguimiento (memoria). Deterministico
(sin SQL escrito por el usuario, sin invencion). Reutiliza el ruteo de IA/Prediccion aguas abajo.
"""

_DOM_KW = {
    "ventas": ("venta", "vend", "factur", "ingres", "margen"),
    "stock": ("stock", "inventario", "rotura", "reposicion", "reponer", "almacen", "caduc"),
    "compras": ("compra", "proveedor", "pedido", "aprovision"),
    "tesoreria": ("tesoreria", "tesorería", "impago", "cobro", "liquidez", "moroso"),
    "rrhh": ("empleado", "contrato", "nomina", "nómina", "rrhh", "personal", "vacacion", "formacion"),
    "crm": ("cliente", "crm"),
    "fiscal": ("iva", "irpf", "verifactu", "aeat", "fiscal", "recargo", "intracomunitaria",
               "declaracion", "declaración", "303", "modelo"),
    "logistica": ("almacen", "almacén", "ruta", "recepcion", "recepción", "expedicion",
                  "expedición", "transportista", "logistic", "traspaso"),
    "tpv": ("tpv", "caja", "cajero", "ticket", "cierre", "arqueo", "devolucion", "devolución"),
    "auditoria": ("auditoria", "auditoría", "log", "hash", "integridad", "aprobacion",
                  "aprobación", "historial"),
    "riesgos": ("riesgo", "problema", "peor", "fallo", "fallan", "falla", "atencion", "atención"),
    "actividad": ("actividad", "ocurrido", "ocurrio", "ocurrió", "paso", "pasado", "resumen",
                  "incidencia", "tarea", "hoy", "ayer"),
}
_ACC_KW = ("crea", "crear", "genera", "generar", "solicita", "solicitar", "programa", "programar",
           "envia", "enviar", "envía", "abre", "abrir", "prepara", "preparar", "haz")
_SEG_KW = ("respecto", "y la semana", "y el mes", "y ayer", "y hoy", "y ese", "y eso", "y esa",
           "anterior", "pasada", "pasado", "tambien", "también", "comparado", "y que hay")
_PERIODO_KW = {"hoy": "dia", "ayer": "dia", "semana": "semana", "mes": "mes",
               "trimestre": "trimestre", "año": "anio", "anio": "anio"}


def _dominio(t):
    for dom, kws in _DOM_KW.items():
        if any(k in t for k in kws):
            return dom
    return None


def _periodo(t):
    for k, v in _PERIODO_KW.items():
        if k in t:
            return v
    return None


def clasificar(texto, mem=None) -> dict:
    mem = mem or {}
    t = (texto or "").lower().strip()
    es_accion = any(t.startswith(k) or f" {k} " in f" {t} " for k in _ACC_KW)
    es_seg = any(k in t for k in _SEG_KW)
    dom = _dominio(t)
    if not dom and es_seg:
        dom = mem.get("dominio")
    dom = dom or "general"
    per = _periodo(t) or (mem.get("periodo") if es_seg else None)
    return {"intent": dom, "dominio": dom, "periodo": per, "es_accion": es_accion,
            "es_seguimiento": es_seg, "texto": texto}
