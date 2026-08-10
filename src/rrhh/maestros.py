"""
Datos MAESTROS de RRHH — fachada única de entidades reutilizables (F4.x).

En lugar de que cada documento (nómina, finiquito, carta de despido, certificado…) pida los
datos por separado, esta capa consolida las entidades maestras que YA existen en la base de datos
y las ofrece como una única fuente coherente:

    Empresa · Trabajador · Contrato · Nómina · Incidencias · Extinción

Reutiliza los módulos existentes (no duplica tablas ni lógica):
    - Empresa:      `src.db.empresa.datos_corporativos`
    - Trabajador:   `src.rrhh.db.empleados` (rrhh_empleados)
    - Contrato:     `src.rrhh.db.contratos` (rrhh_contratos, último vigente)
    - Nómina:       `src.rrhh.db.nominas` (rrhh_nominas, última)
    - Incidencias:  `src.rrhh.db.vacaciones` + `src.rrhh.db.ausencias`
    - Extinción:    derivada del expediente (fecha_baja / estado)
    - Centro:       `src.db.centros`

`consolidado(emp)` devuelve las 6 entidades normalizadas; `campos_documento(emp)` las proyecta a un
diccionario plano con las CLAVES CANÓNICAS que usan las plantillas (con alias: `nombre`/
`nombre_completo`, `domicilio`/`direccion`, `salario`/`salario_base`…), listo para autorrellenar
cualquier formulario. Solo lectura: no escribe en la base de datos.
"""

import logging

logger = logging.getLogger("rrhh.maestros")


def _num(v):
    """Suma robusta: convierte a float admitiendo coma decimal; devuelve 0.0 si no procede."""
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v)
    except (TypeError, ValueError):
        return 0.0


def _id_empresa(id_empresa):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


# ── Entidades maestras ────────────────────────────────────────────────────────
def entidad_empresa(id_empresa=None) -> dict:
    """Datos fiscales/laborales/de cotización de la empresa (normalizados).

    Fuente ÚNICA = `empresa.info_documento` (vista PLANA de `datos_corporativos`, con claves
    estables). Es la misma fuente que usan la generación de contratos y el resto de documentos, de
    modo que los datos de DATOS DE EMPRESA (Configuración) quedan integrados aquí."""
    id_empresa = _id_empresa(id_empresa)
    try:
        from src.db.empresa import info_documento
        info = info_documento(id_empresa=id_empresa) or {}
    except Exception as e:
        logger.debug("entidad_empresa: %s", e)
        info = {}
    return {
        "razon_social": info.get("razon_social") or info.get("nombre"),
        "nombre_comercial": info.get("nombre_comercial"),
        "cif": info.get("cif"),
        "domicilio": info.get("direccion") or info.get("direccion_completa"),
        "cp": info.get("cp"),
        "municipio": info.get("municipio"),
        "provincia": info.get("provincia"),
        "telefono": info.get("telefono"),
        "email": info.get("email"),
        "ccc": info.get("ccc"),
        "cnae": info.get("cnae"),
        "convenio": info.get("convenio"),
        "actividad": info.get("actividad"),
        "regimen": info.get("regimen"),
    }


def entidad_trabajador(emp, id_empresa=None) -> dict:
    """Ficha del trabajador. Acepta la fila (dict) o el id de empleado."""
    if isinstance(emp, dict):
        return dict(emp)
    id_empresa = _id_empresa(id_empresa)
    try:
        from src.rrhh.db import empleados
        return empleados.obtener_empleado(emp, id_empresa) or {}
    except Exception as e:
        logger.debug("entidad_trabajador(%s): %s", emp, e)
        return {}


def entidad_contrato(id_empleado, id_empresa=None) -> dict:
    """Contrato vigente (el más reciente) del trabajador. {} si no hay ninguno."""
    if not id_empleado:
        return {}
    id_empresa = _id_empresa(id_empresa)
    try:
        from src.rrhh.db import contratos
        lst = contratos.listar_contratos(id_empleado, id_empresa) or []
        return lst[0] if lst else {}
    except Exception as e:
        logger.debug("entidad_contrato(%s): %s", id_empleado, e)
        return {}


def entidad_nomina(id_empleado, id_empresa=None) -> dict:
    """Última nómina registrada (bases/IRPF/importe). {} si no hay ninguna."""
    if not id_empleado:
        return {}
    id_empresa = _id_empresa(id_empresa)
    try:
        from src.rrhh.db import nominas
        lst = nominas.listar_nominas(id_empleado, id_empresa) or []
        return lst[0] if lst else {}
    except Exception as e:
        logger.debug("entidad_nomina(%s): %s", id_empleado, e)
        return {}


def entidad_incidencias(id_empleado, id_empresa=None) -> dict:
    """Vacaciones y ausencias del trabajador + un resumen agregado (días reales sumados)."""
    if not id_empleado:
        return {"vacaciones": [], "ausencias": [], "dias_vacaciones": 0.0, "dias_ausencias": 0.0}
    id_empresa = _id_empresa(id_empresa)
    vac, aus = [], []
    try:
        from src.rrhh.db import vacaciones
        vac = vacaciones.listar_vacaciones(id_empleado, id_empresa) or []
    except Exception as e:
        logger.debug("incidencias/vac(%s): %s", id_empleado, e)
    try:
        from src.rrhh.db import ausencias
        aus = ausencias.listar_ausencias(id_empleado, id_empresa) or []
    except Exception as e:
        logger.debug("incidencias/aus(%s): %s", id_empleado, e)
    return {
        "vacaciones": vac,
        "ausencias": aus,
        "dias_vacaciones": round(sum(_num(v.get("dias")) for v in vac), 2),
        "dias_ausencias": round(sum(_num(a.get("dias")) for a in aus), 2),
    }


def entidad_extincion(id_empleado, id_empresa=None, trab=None) -> dict:
    """Datos de extinción derivados del expediente (fecha de baja / estado). El motivo y los
    importes concretos los aporta cada documento; aquí solo lo que consta en el maestro."""
    trab = trab if trab is not None else entidad_trabajador(id_empleado, id_empresa)
    return {
        "fecha_baja": (trab or {}).get("fecha_baja"),
        "estado": (trab or {}).get("estado"),
    }


def _nombre_centro(id_centro, id_empresa=None) -> str | None:
    if not id_centro:
        return None
    id_empresa = _id_empresa(id_empresa)
    try:
        from src.db import centros
        c = centros.obtener_centro(id_centro, id_empresa) or {}
        return c.get("nombre_centro") or c.get("nombre")
    except Exception as e:
        logger.debug("_nombre_centro(%s): %s", id_centro, e)
        return None


# ── Consolidado + proyección a claves de plantilla ────────────────────────────
def consolidado(emp, id_empresa=None) -> dict:
    """Las 6 entidades maestras normalizadas para un trabajador. `emp` = fila (dict) o id."""
    id_empresa = _id_empresa(id_empresa)
    trab = entidad_trabajador(emp, id_empresa)
    id_empleado = trab.get("id") if isinstance(trab, dict) else emp
    return {
        "empresa": entidad_empresa(id_empresa),
        "trabajador": trab,
        "contrato": entidad_contrato(id_empleado, id_empresa),
        "nomina": entidad_nomina(id_empleado, id_empresa),
        "incidencias": entidad_incidencias(id_empleado, id_empresa),
        "extincion": entidad_extincion(id_empleado, id_empresa, trab),
        "id_empleado": id_empleado,
    }


def campos_documento(emp, id_empresa=None) -> dict:
    """Proyección PLANA de los maestros a las claves canónicas de las plantillas (con alias).

    Devuelve SOLO valores no vacíos, de modo que autorrellenar nunca borra un campo. Todas las
    plantillas comparten estas claves: cada formulario recoge únicamente las que tiene y descarta
    el resto (el `setter` ignora las claves sin widget)."""
    c = consolidado(emp, id_empresa)
    E, T, K = c["empresa"], c["trabajador"], c["contrato"]
    I, X = c["incidencias"], c["extincion"]

    nombre = f"{T.get('nombre','')} {T.get('apellidos','')}".strip()
    centro = _nombre_centro(T.get("id_centro") or K.get("id_centro"), _id_empresa(id_empresa))
    fecha_alta = T.get("fecha_alta") or K.get("fecha_inicio")
    tipo_contrato = K.get("modalidad") or K.get("tipo_registro")
    jornada = K.get("jornada") or T.get("jornada")
    salario = K.get("salario") or T.get("salario_base")

    plano = {
        # Empresa
        "razon_social": E.get("razon_social"), "nombre_comercial": E.get("nombre_comercial"),
        "cif": E.get("cif"), "ccc": E.get("ccc"), "cnae": E.get("cnae"),
        "domicilio": E.get("domicilio"),
        # Trabajador (alias nombre / nombre_completo; direccion / trab_*)
        "nombre": nombre, "nombre_completo": nombre,
        "trab_nombre": T.get("nombre"),
        "nif": T.get("nif"), "num_ss": T.get("num_ss"),
        "fecha_nacimiento": T.get("fecha_nacimiento"), "sexo": T.get("sexo"),
        "nacionalidad": T.get("nacionalidad"),
        "direccion": T.get("direccion"), "trab_direccion": T.get("direccion"),
        "municipio": T.get("municipio"), "trab_municipio": T.get("municipio"),
        "provincia": T.get("provincia"), "trab_provincia": T.get("provincia"),
        "cp": T.get("cp"), "trab_cp": T.get("cp"),
        "telefono": T.get("telefono"), "email": T.get("email"),
        "categoria": T.get("categoria"), "grupo_prof": T.get("grupo_prof"),
        "puesto": T.get("puesto"),
        "lugar": T.get("municipio"),  # sugerencia de lugar de expedición/firma
        # Contrato (el maestro de contrato prevalece; con alias de salario)
        "fecha_alta": fecha_alta, "antiguedad": fecha_alta,
        "fecha_inicio": K.get("fecha_inicio"), "fecha_fin": K.get("fecha_fin"),
        "tipo_contrato": tipo_contrato, "modalidad": K.get("modalidad"),
        "jornada": jornada,
        "salario": salario, "salario_base": T.get("salario_base") or K.get("salario"),
        "salario_mensual": salario,
        "convenio": T.get("convenio") or E.get("convenio"),
        "centro_trabajo": centro,
        # Incidencias (días reales sumados del histórico)
        "vac_disfrutadas": I.get("dias_vacaciones") or None,
        # Extinción (lo que consta en el maestro; el resto lo aporta el documento)
        "fecha_baja": X.get("fecha_baja"),
    }
    return {k: v for k, v in plano.items() if v not in (None, "", 0, 0.0)}
