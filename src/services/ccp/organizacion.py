"""
Smart Organization Resolver (Parte C) — resuelve ORGANIZACIONES completas, no solo personas.

Ej.: "Mercadona" → la organización + sus departamentos/contactos con correo (compras@, facturas@…).
Reutiliza el Servicio de Resolución de Destinatarios para localizar la organización y consulta sus
contactos (datos vivos, sin duplicar). Jerarquía Empresa→Delegación→Centro→Departamento→Persona
modelada como `niveles`, extensible; la resolución puede detenerse en cualquier nivel.

Multiempresa estricto (id_empresa en toda consulta).
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("ccp.organizacion")


@dataclass
class Departamento:
    nombre: str
    correo: str
    cargo: str | None = None


@dataclass
class Organizacion:
    nombre: str
    tipo: str
    id_empresa: str | None = None
    id_origen: object | None = None
    modulo_origen: str | None = None
    correo_principal: str | None = None
    departamentos: list = field(default_factory=list)   # List[Departamento]

    def correos(self) -> list:
        out = [self.correo_principal] if self.correo_principal else []
        out += [d.correo for d in self.departamentos if d.correo]
        # dedup conservando orden
        vistos, res = set(), []
        for c in out:
            k = (c or "").strip().lower()
            if k and k not in vistos:
                vistos.add(k); res.append(c)
        return res

    def to_dict(self) -> dict:
        return {"nombre": self.nombre, "tipo": self.tipo, "id_empresa": self.id_empresa,
                "id_origen": self.id_origen, "modulo_origen": self.modulo_origen,
                "correo_principal": self.correo_principal,
                "departamentos": [d.__dict__ for d in self.departamentos]}


# Cómo obtener los contactos (departamentos/personas) de cada tipo de organización.
# (modulo_origen del destinatario) → (tabla_contactos, fk, join_empresa_directo)
_CONTACTOS = {
    "clientes": ("clientes_contactos", "id_cliente", True),
    "proveedores": ("proveedores_contactos", "id_proveedor", False),
}


def _departamentos(modulo_origen, id_origen, id_empresa) -> list:
    cfg = _CONTACTOS.get(modulo_origen)
    if not cfg or id_origen is None:
        return []
    tabla, fk, emp_directo = cfg
    try:
        from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            if emp_directo:
                cur.execute(f"SELECT nombre, cargo, email FROM {tabla} WHERE {fk}=%s AND id_empresa=%s "
                            "AND email IS NOT NULL AND email<>''", (id_origen, id_empresa))
            else:
                # tabla hija sin id_empresa: filtra por el padre (proveedores) de la empresa.
                cur.execute(f"SELECT c.nombre, c.cargo, c.email FROM {tabla} c "
                            f"JOIN proveedores p ON p.{fk}=c.{fk} "
                            f"WHERE c.{fk}=%s AND p.id_empresa=%s AND c.email IS NOT NULL "
                            "AND c.email<>''", (id_origen, id_empresa))
            filas = _filas_a_dicts(cur, cur.fetchall())
        return [Departamento(nombre=f.get("nombre") or (f.get("cargo") or "Contacto"),
                             correo=f.get("email"), cargo=f.get("cargo")) for f in filas]
    except Exception as e:
        logger.debug("_departamentos(%s): %s", modulo_origen, e)
        return []


def resolver_organizacion(id_empresa, texto="", *, tipo=None, nif=None, id_origen=None):
    """Localiza una organización (cliente/proveedor…) y sus departamentos/contactos con correo.
    Devuelve `Organizacion` o None. Multiempresa estricto."""
    if not id_empresa:
        return None
    from src.services import destinatarios as _dest
    # Localiza la entidad organizativa por el Servicio de Resolución (personas/organizaciones).
    consulta = (nif or texto or "").strip()
    candidatos = _dest.buscar_destinatarios(id_empresa, consulta, limite=15) if consulta else \
        _dest.buscar_destinatarios(id_empresa, "", limite=50)
    org_tipos = {tipo} if tipo else {"cliente", "proveedor"}
    entidad = None
    for d in candidatos:
        if d.tipo in org_tipos and (id_origen is None or str(d.id_origen) == str(id_origen)):
            entidad = d
            break
    if entidad is None:
        return None
    deps = _departamentos(entidad.modulo_origen, entidad.id_origen, id_empresa)
    return Organizacion(nombre=entidad.nombre_mostrado, tipo=entidad.tipo, id_empresa=id_empresa,
                        id_origen=entidad.id_origen, modulo_origen=entidad.modulo_origen,
                        correo_principal=entidad.correo, departamentos=deps)
