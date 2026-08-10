"""
Modelo canónico de la ingesta de datos (importador maestro). Define las ENTIDADES que Smart Manager sabe
ingerir, sus campos canónicos y los SINÓNIMOS de cabecera para el auto-mapeo heurístico (la sugerencia con IA
llega en la Fase 2). También los normalizadores de valores (precio/stock/texto). API-First, sin PyQt.

Fase 1: entidad PRODUCTOS (con familia y stock EN LÍNEA, el caso real más común: un Excel con código, nombre,
precio, familia y existencias). Alimenta los motores oficiales: `db/articulos`, `db/familias`, kárdex/stock.
"""

import re
import unicodedata

PRODUCTOS = "productos"
CLIENTES = "clientes"
PROVEEDORES = "proveedores"
VENTAS_HIST = "ventas_hist"        # histórico de ventas (para forecasting; NO toca `ventas`)
SALDOS = "saldos"                  # saldos de apertura contable (asiento de apertura)
TESORERIA = "tesoreria"            # cuentas bancarias + saldo inicial
ENTIDADES = (PRODUCTOS, CLIENTES, PROVEEDORES, VENTAS_HIST, SALDOS, TESORERIA)

# Campo canónico → (requerido, sinónimos de cabecera). El auto-mapeo compara cabeceras normalizadas.
CAMPOS = {
    PRODUCTOS: {
        "codigo": (True, ("codigo", "cod", "code", "sku", "ean", "ean13", "gtin", "gtin13", "barcode",
                          "codigobarras", "referencia", "ref", "articulo", "idarticulo", "item")),
        "nombre": (False, ("nombre", "name", "producto", "descripcioncorta", "titulo", "denominacion",
                          "descripcion", "description", "desc")),
        "descripcion": (False, ("descripcionlarga", "detalle", "observaciones", "notas", "longdescription")),
        "precio": (False, ("precio", "price", "pvp", "precioventa", "importe", "preciovta", "pv", "preciopvp")),
        "familia": (False, ("familia", "family", "categoria", "category", "grupo", "seccion", "rubro",
                           "gama", "linea", "gpc", "unspsc", "eclass", "clasificacion", "classification",
                           "grupomercancia")),
        "stock": (False, ("stock", "existencias", "cantidad", "qty", "quantity", "unidades", "stockactual",
                         "inventario", "onhand", "disponible", "saldo")),
        "imagen": (False, ("imagen", "image", "foto", "photo", "img", "imageurl", "urlimagen", "imagenurl",
                          "urlfoto", "fotourl", "picture", "rutaimagen", "imagenprincipal", "fotoprincipal",
                          "imagen1", "foto1", "thumbnail", "miniatura", "imagenes")),
    },
    CLIENTES: {
        "nombre": (True, ("nombre", "name", "cliente", "razonsocial", "razon_social", "denominacion",
                         "contacto", "empresa")),
        "nif": (False, ("nif", "cif", "dni", "nifcif", "cifnif", "vat", "taxid", "documento", "identificacion")),
        "email": (False, ("email", "correo", "mail", "emailcliente", "correoelectronico")),
        "telefono": (False, ("telefono", "tel", "phone", "movil", "celular", "telefono1")),
        "direccion": (False, ("direccion", "address", "domicilio", "calle", "direccionfiscal")),
    },
    PROVEEDORES: {
        "nombre": (True, ("nombre", "razonsocial", "razon_social", "proveedor", "name", "denominacion",
                         "nombrecomercial", "empresa")),
        "nif": (False, ("nif", "cif", "cifnif", "cif_nif", "vat", "taxid", "documento")),
        "email": (False, ("email", "correo", "mail")),
        "telefono": (False, ("telefono", "tel", "phone", "movil")),
        "direccion": (False, ("direccion", "direccionfiscal", "address", "domicilio", "calle")),
    },
    VENTAS_HIST: {
        "fecha": (True, ("fecha", "date", "dia", "day", "fechaventa", "periodo", "fechadocumento")),
        "codigo": (True, ("codigo", "sku", "ean", "gtin", "referencia", "ref", "articulo", "producto", "item")),
        "cantidad": (False, ("cantidad", "unidades", "uds", "qty", "quantity", "vendidas", "cant")),
        "importe": (False, ("importe", "total", "ventas", "amount", "euros", "importeventa", "importetotal")),
    },
    SALDOS: {
        "cuenta": (True, ("cuenta", "codigocuenta", "account", "cuentacontable", "pgc", "codigo", "cta")),
        "debe": (False, ("debe", "debit", "cargo")),
        "haber": (False, ("haber", "credit", "abono")),
        "saldo": (False, ("saldo", "balance", "importe", "total", "saldofinal")),
        "descripcion": (False, ("descripcion", "concepto", "denominacion", "nombre", "description")),
    },
    TESORERIA: {
        "nombre": (True, ("nombre", "cuenta", "nombrecuenta", "descripcion", "account", "alias")),
        "iban": (True, ("iban", "numerocuenta", "ccc", "cuentabancaria", "numerodecuenta")),
        "saldo": (False, ("saldo", "saldoinicial", "balance", "importe", "saldoactual")),
        "titular": (False, ("titular", "holder", "propietario")),
        "bic": (False, ("bic", "swift", "codigobic")),
        "banco": (False, ("banco", "entidad", "bank", "entidadbancaria")),
    },
}


def parse_fecha(valor):
    """Normaliza una fecha a 'YYYY-MM-DD' tolerando formatos habituales; None si no es reconocible."""
    if valor is None:
        return None
    import datetime as _dt
    if isinstance(valor, (_dt.datetime, _dt.date)):
        return valor.strftime("%Y-%m-%d")
    s = str(valor).strip().split(" ")[0].split("T")[0]
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y", "%d.%m.%Y", "%Y%m%d"):
        try:
            return _dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _norm(texto) -> str:
    """Normaliza una cabecera para comparar: minúsculas, sin acentos, sin separadores/espacios."""
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_precio(valor):
    """Convierte a float tolerando símbolos de moneda y coma decimal ('1.234,56 €' → 1234.56). None si vacío."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return round(float(valor), 4)
    s = str(valor).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)                 # fuera moneda/espacios
    if "," in s and "." in s:                        # 1.234,56 → 1234.56  |  1,234.56 → 1234.56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def parse_stock(valor):
    """Convierte a entero (redondea) tolerando decimales/coma. None si vacío/no numérico."""
    p = parse_precio(valor)
    return int(round(p)) if p is not None else None


def limpiar_texto(valor):
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None
