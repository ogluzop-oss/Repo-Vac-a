"""
Fuentes (adaptadores registrables) del Servicio de Resolución de Destinatarios (Partes C/P).

REGLA (restricción arquitectónica 2): toda fuente se incorpora como un adaptador REGISTRABLE. Añadir
una entidad nueva con correo = registrar un adaptador (config o subclase), con cambios mínimos y SIN
tocar el núcleo. No se crean agendas: cada adaptador LEE la tabla/módulo original del ERP.

REGLA (restricción 4, multiempresa CRÍTICO): TODO adaptador exige `id_empresa` y filtra por él en la
consulta. Es imposible obtener candidatos de otra empresa. El adaptador devuelve candidatos
(objetos `Destinatario`) SIN puntuar; la puntuación/orden la centraliza el servicio.

Núcleo agnóstico de framework (sin PyQt, sin importar el módulo Correo).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
from src.services.destinatarios.modelo import (
    Destinatario, TIPO_CENTRO, TIPO_CLIENTE, TIPO_CONTACTO, TIPO_EMPLEADO, TIPO_LEAD,
    TIPO_PROVEEDOR, TIPO_USUARIO,
)

logger = logging.getLogger("destinatarios.fuentes")

# Tope de candidatos que cada adaptador trae por consulta (acotación de coste; el servicio ordena
# y recorta al límite final). Dos vías: prefiltro LIKE (exacto/subcadena a cualquier escala) +
# muestra reciente (habilita la búsqueda difusa por tipografía).
_TOPE_LIKE = 200
_TOPE_MUESTRA = 400


class FuenteBase:
    """Contrato de una fuente de destinatarios. `buscar` DEBE filtrar por `id_empresa`."""
    clave = ""
    tipo = ""
    contextos = ()   # módulos donde esta fuente se prioriza (Parte H)

    def buscar(self, id_empresa, texto, limite=50) -> list:
        raise NotImplementedError


def _existe_columna(cur, tabla, columna) -> bool:
    cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND COLUMN_NAME=%s", (tabla, columna))
    r = cur.fetchone()
    return int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 0) > 0


class FuenteTabla(FuenteBase):
    """Adaptador GENÉRICO configurable sobre una tabla del ERP con `id_empresa` + correo.

    Registrar una entidad nueva = instanciar y registrar esta clase con su config. Siempre
    tenant-safe (WHERE id_empresa). No duplica datos: lee la tabla original."""

    def __init__(self, clave, tabla, tipo, *, col_correo="email", cols_nombre=("nombre",),
                 cols_busqueda=(), col_id="id", col_estado=None, col_bloqueado=None,
                 col_activo=None, col_archivado=None, contextos=(), join_empresa=None):
        self.clave = clave
        self.tabla = tabla
        self.tipo = tipo
        self.col_correo = col_correo
        self.cols_nombre = tuple(cols_nombre or ())
        self.cols_busqueda = tuple(cols_busqueda or ())
        self.col_id = col_id
        self.col_estado = col_estado
        self.col_bloqueado = col_bloqueado
        self.col_activo = col_activo
        self.col_archivado = col_archivado
        self.contextos = tuple(contextos or ())
        # Filtro multiempresa por JOIN para tablas hijas SIN id_empresa propio:
        # (tabla_padre, col_local_fk, col_padre_pk). Ej.: proveedores_contactos → proveedores.
        self.join_empresa = join_empresa

    def _cols(self):
        cols = {self.col_id, self.col_correo}
        cols.update(self.cols_nombre)
        cols.update(self.cols_busqueda)
        for c in (self.col_estado, self.col_bloqueado, self.col_activo, self.col_archivado):
            if c:
                cols.add(c)
        return [c for c in cols if c]

    def _estado(self, row) -> str | None:
        if self.col_bloqueado and row.get(self.col_bloqueado):
            return "bloqueado"
        if self.col_archivado and row.get(self.col_archivado):
            return "archivado"
        if self.col_activo is not None and not row.get(self.col_activo, 1):
            return "deshabilitado"
        if self.col_estado:
            return row.get(self.col_estado)
        return None

    def _a_destinatario(self, row, id_empresa) -> Destinatario:
        nombre = " ".join(str(row.get(c) or "").strip() for c in self.cols_nombre).strip()
        busqueda = [nombre] + [str(row.get(c) or "") for c in self.cols_busqueda]
        busqueda.append(str(row.get(self.col_correo) or ""))
        return Destinatario(
            correo=row.get(self.col_correo) or "",
            nombre_mostrado=nombre or (row.get(self.col_correo) or ""),
            tipo=self.tipo,
            id_empresa=id_empresa,
            modulo_origen=self.clave,
            id_origen=row.get(self.col_id),
            estado=self._estado(row),
            extra={"_busqueda": [b for b in busqueda if b]},
        )

    def buscar(self, id_empresa, texto, limite=50) -> list:
        if not id_empresa:
            return []   # multiempresa estricto: sin empresa, no se resuelve nada
        texto = (texto or "").strip()
        try:
            ensure_schema()
            with obtener_conexion() as conn, conn.cursor() as cur:
                # Validación defensiva de columnas (evita SQL roto si el esquema difiere).
                if not _existe_columna(cur, self.tabla, self.col_correo):
                    return []
                if not self.join_empresa and not _existe_columna(cur, self.tabla, "id_empresa"):
                    return []
                cols = [c for c in self._cols() if _existe_columna(cur, self.tabla, c)]
                if self.col_correo not in cols:
                    return []
                sel = ", ".join(f"`{c}`" for c in cols)
                # Predicado multiempresa (siempre 1 parámetro id_empresa): directo o por JOIN.
                if self.join_empresa:
                    padre, fk_local, pk_padre = self.join_empresa
                    where_emp = (f"EXISTS (SELECT 1 FROM `{padre}` p WHERE "
                                 f"p.`{pk_padre}`=`{self.tabla}`.`{fk_local}` AND p.id_empresa=%s)")
                else:
                    where_emp = "id_empresa=%s"
                base = (f"SELECT {sel} FROM `{self.tabla}` WHERE {where_emp} "
                        f"AND `{self.col_correo}` IS NOT NULL AND `{self.col_correo}`<>'' ")
                filas = {}
                busq_cols = [c for c in (self.cols_nombre + self.cols_busqueda + (self.col_correo,))
                            if c in cols]
                # 1) Prefiltro LIKE por tokens (exacto/subcadena a cualquier escala).
                if texto and busq_cols:
                    tokens = texto.split()
                    ors, params = [], [id_empresa]
                    for tok in tokens:
                        sub = [f"`{c}` LIKE %s" for c in busq_cols]
                        ors.append("(" + " OR ".join(sub) + ")")
                        params.extend([f"%{tok}%"] * len(busq_cols))
                    q = base + " AND (" + " OR ".join(ors) + f") LIMIT {_TOPE_LIKE}"
                    cur.execute(q, params)
                    for r in _filas_a_dicts(cur, cur.fetchall()):
                        filas[r.get(self.col_id)] = r
                # 2) Muestra reciente (habilita la difusa por tipografía y el "sin texto").
                cur.execute(base + f" ORDER BY `{self.col_id}` DESC LIMIT {_TOPE_MUESTRA}", (id_empresa,))
                for r in _filas_a_dicts(cur, cur.fetchall()):
                    filas.setdefault(r.get(self.col_id), r)
                return [self._a_destinatario(r, id_empresa) for r in filas.values()]
        except Exception as e:
            logger.debug("Fuente %s: %s", self.clave, e)
            return []


# ── Registro de fuentes ───────────────────────────────────────────────────────
_REGISTRO: dict = {}


def registrar_fuente(fuente: FuenteBase):
    """Registra (o reemplaza) una fuente por su clave. Punto de extensión oficial."""
    if not getattr(fuente, "clave", None):
        raise ValueError("La fuente debe tener 'clave'.")
    _REGISTRO[fuente.clave] = fuente
    return fuente


def fuentes() -> list:
    return list(_REGISTRO.values())


def fuente(clave) -> FuenteBase | None:
    return _REGISTRO.get(clave)


# ── Fuentes base del ERP (todas tenant-safe). Ampliables registrando más. ─────
def _registrar_base():
    registrar_fuente(FuenteTabla(
        "clientes", "clientes", TIPO_CLIENTE,
        cols_nombre=("nombre",), cols_busqueda=("nif", "telefono"),
        col_estado="estado", contextos=("crm", "ventas", "clientes", "facturacion")))
    registrar_fuente(FuenteTabla(
        "proveedores", "proveedores", TIPO_PROVEEDOR, col_id="id_proveedor",
        cols_nombre=("razon_social",), cols_busqueda=("nombre_comercial", "cif_nif", "telefono"),
        col_estado="estado", col_bloqueado="bloqueado",
        contextos=("compras", "proveedores", "aprovisionamiento")))
    registrar_fuente(FuenteTabla(
        "empleados", "rrhh_empleados", TIPO_EMPLEADO,
        cols_nombre=("nombre", "apellidos"), cols_busqueda=("nif", "telefono"),
        col_estado="estado", contextos=("rrhh", "laboral", "portal_empleado")))
    registrar_fuente(FuenteTabla(
        "usuarios", "usuarios", TIPO_USUARIO,
        cols_nombre=("nombre",), cols_busqueda=(), col_activo="activo",
        contextos=("seguridad", "usuarios", "administracion")))
    # Contactos de cliente (persona de contacto dentro de un cliente).
    registrar_fuente(FuenteTabla(
        "clientes_contactos", "clientes_contactos", TIPO_CONTACTO,
        cols_nombre=("nombre",), cols_busqueda=("cargo", "telefono"),
        contextos=("crm", "ventas", "clientes", "facturacion")))
    # Contactos de proveedor: la tabla NO tiene id_empresa → filtro por JOIN a proveedores.
    registrar_fuente(FuenteTabla(
        "proveedores_contactos", "proveedores_contactos", TIPO_CONTACTO,
        cols_nombre=("nombre",), cols_busqueda=("cargo", "telefono"),
        join_empresa=("proveedores", "id_proveedor", "id_proveedor"),
        contextos=("compras", "proveedores", "aprovisionamiento")))
    # Centros de trabajo (con correo propio).
    registrar_fuente(FuenteTabla(
        "centros_trabajo", "centros_trabajo", TIPO_CENTRO, col_id="id_centro",
        cols_nombre=("nombre_centro",), cols_busqueda=("nombre_corto", "telefono"),
        col_estado="estado", col_archivado="archivado",
        contextos=("logistica", "almacenes", "administracion")))
    # Leads / candidatos comerciales (CRM).
    registrar_fuente(FuenteTabla(
        "crm_leads", "crm_leads", TIPO_LEAD,
        cols_nombre=("nombre",), cols_busqueda=("telefono",), col_estado="estado",
        contextos=("crm", "ventas", "comercial")))


_registrar_base()
