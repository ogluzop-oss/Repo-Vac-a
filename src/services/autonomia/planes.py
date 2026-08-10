"""
Planes de ejecucion (Paquete Enterprise 10, SUBFASE 10.2/10.3).

Convierte un escenario aprobado del Simulador (o una lista manual de acciones) en un PLAN de
ejecucion con acciones, orden, fases, impacto, riesgos, responsables y tiempo estimado. Las
variables estrategicas del escenario se traducen a acciones SEGURAS del catalogo: los cambios
criticos (precio, despidos, pedidos...) se convierten en PROPUESTAS gobernadas, nunca en ejecucion
directa (SUBFASE 10.14). No duplica el Simulador: lo reutiliza como fuente de impacto/riesgo.
"""

import json
import logging

from src.services.autonomia import catalogo, modos
from src.services.autonomia import modelo as M

logger = logging.getLogger("autonomia.planes")

# Variable de escenario → (codigo_accion, fase, titulo, rol_responsable)
_MAPA_VARIABLE = {
    "plantilla_alta":  ("crear_tarea", 1, "Iniciar proceso de contratacion", "GERENTE"),
    "plantilla_baja":  ("despedir_empleado", 3, "Revisar reduccion de plantilla", "ADMINISTRADOR"),
    "salario":         ("solicitar_aprobacion", 2, "Revision salarial", "ADMINISTRADOR"),
    "precio":          ("modificar_precio", 3, "Ajuste de precios", "ADMINISTRADOR"),
    "descuento":       ("proponer_liquidacion", 2, "Aplicar descuentos/promocion", "GERENTE"),
    "promocion":       ("proponer_liquidacion", 2, "Lanzar promocion", "GERENTE"),
    "stock_bajo":      ("crear_propuesta_compra", 2, "Reponer stock", "GERENTE"),
    "stock_alto":      ("solicitar_inventario", 1, "Revisar sobrestock", "GERENTE"),
    "proveedor":       ("solicitar_revision", 1, "Evaluar cambio de proveedor", "GERENTE"),
    "tiendas":         ("crear_tarea", 1, "Estudio de apertura de tienda", "ADMINISTRADOR"),
    "almacenes":       ("crear_tarea", 1, "Estudio de nuevo almacen", "ADMINISTRADOR"),
    "gastos":          ("solicitar_auditoria", 1, "Auditar gastos", "ADMINISTRADOR"),
    "impuestos":       ("solicitar_auditoria", 1, "Revisar impacto fiscal", "ADMINISTRADOR"),
}

# Minutos estimados por accion (heuristica para el tiempo estimado del plan).
_MINUTOS = {"crear_tarea": 5, "crear_propuesta_compra": 10, "solicitar_inventario": 15,
            "solicitar_auditoria": 20, "solicitar_revision": 15, "solicitar_aprobacion": 30,
            "proponer_liquidacion": 10, "modificar_precio": 30, "despedir_empleado": 60,
            "notificar": 2}


def _emp(id_empresa=None):
    return modos._emp(id_empresa)


def _acciones_de_variables(variables) -> list:
    """Traduce variables del escenario a acciones del catalogo (seguras o propuestas)."""
    acciones = []
    for v in variables or []:
        nombre = v.get("variable")
        valor = float(v.get("valor") or 0)
        clave = nombre
        if nombre == "plantilla":
            clave = "plantilla_alta" if valor >= 0 else "plantilla_baja"
        elif nombre == "stock":
            clave = "stock_bajo" if valor < 0 else "stock_alto"
        mapa = _MAPA_VARIABLE.get(clave)
        if not mapa:
            continue
        codigo, fase, titulo, rol = mapa
        acciones.append({"codigo": codigo, "fase": fase, "titulo": titulo, "responsable": rol,
                         "params": {"origen_variable": nombre, "valor": valor}})
    return acciones


def crear(nombre, *, descripcion=None, origen="manual", origen_ref=None, usuario=None,
          acciones=None, variables=None, riesgo="BAJO", confianza="MEDIA", id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    modo = modos.obtener(emp)
    if variables and not acciones:
        acciones = _acciones_de_variables(variables)
    acciones = acciones or []
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO exec_planes (id_empresa, usuario, origen, origen_ref, nombre, "
                        "descripcion, estado, modo, confianza, riesgo, workflow_entidad) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, usuario, origen, (str(origen_ref) if origen_ref else None), nombre[:160],
                         (descripcion or "")[:255], M.BORRADOR, modo, confianza, riesgo, "plan_ejecucion"))
            pid = cur.lastrowid
            for i, a in enumerate(sorted(acciones, key=lambda x: x.get("fase", 1)), start=1):
                m = catalogo.meta(a["codigo"])
                cur.execute("INSERT INTO exec_acciones (id_plan, id_empresa, fase, orden, "
                            "codigo_accion, titulo, params_json, reversible, critica) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                            (pid, emp, a.get("fase", 1), i, a["codigo"],
                             a.get("titulo") or m["titulo"],
                             json.dumps(a.get("params") or {}, default=str),
                             1 if m["reversible"] else 0, 1 if m["critica"] else 0))
            c.commit()
            return pid
    except Exception as e:
        logger.error("crear plan: %s", e)
        return None


def crear_desde_escenario(id_escenario, *, usuario=None, id_empresa=None) -> int | None:
    """SUBFASE 10.2: convierte un escenario simulado en un plan de ejecucion (acciones propuestas)."""
    emp = _emp(id_empresa)
    try:
        from src.services import simulador
        esc = simulador.servicio().escenario(id_escenario, emp)
        if not esc:
            return None
        vs = simulador.servicio().variables(id_escenario, emp)
        r = simulador.servicio().simular(id_escenario, emp)
        riesgo = (r.get("riesgo") or {}).get("nivel", "BAJO")
        conf = r.get("confianza", "MEDIA")
        return crear(f"Plan: {esc.get('nombre')}", descripcion="Derivado del escenario simulado",
                     origen="escenario", origen_ref=id_escenario, usuario=usuario, variables=vs,
                     riesgo=riesgo, confianza=conf, id_empresa=emp)
    except Exception as e:
        logger.error("crear_desde_escenario: %s", e)
        return None


def obtener(id_plan, id_empresa=None) -> dict | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM exec_planes WHERE id=%s AND id_empresa=%s", (id_plan, emp))
            p = _filas_a_dicts(cur, cur.fetchall())
            if not p:
                return None
            plan = p[0]
            cur.execute("SELECT * FROM exec_acciones WHERE id_plan=%s AND id_empresa=%s "
                        "ORDER BY fase, orden", (id_plan, emp))
            plan["acciones"] = _filas_a_dicts(cur, cur.fetchall())
            return plan
    except Exception as e:
        logger.error("obtener plan: %s", e)
        return None


def listar(id_empresa=None, *, estado=None, limite=100) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        q = "SELECT id, nombre, estado, modo, riesgo, confianza, origen, usuario, creado FROM exec_planes WHERE id_empresa=%s"
        p = [emp]
        if estado:
            q += " AND estado=%s"; p.append(estado)
        q += " ORDER BY creado DESC LIMIT %s"; p.append(int(limite))
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar planes: %s", e)
        return []


def marcar(id_plan, estado, *, aprobado_por=None, workflow_ref=None, id_empresa=None) -> bool:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE exec_planes SET estado=%s, aprobado_por=COALESCE(%s, aprobado_por), "
                        "workflow_ref=COALESCE(%s, workflow_ref) WHERE id=%s AND id_empresa=%s",
                        (estado, aprobado_por, workflow_ref, id_plan, emp))
            c.commit()
            return True
    except Exception as e:
        logger.debug("marcar plan: %s", e)
        return False


def detalle(id_plan, id_empresa=None) -> dict:
    """SUBFASE 10.3: plan legible con fases, impacto, riesgos, responsables y tiempo estimado."""
    plan = obtener(id_plan, id_empresa)
    if not plan:
        return {"error": "plan no encontrado"}
    acciones = plan.get("acciones", [])
    fases = {}
    minutos = 0
    responsables = set()
    for a in acciones:
        cod = a.get("codigo_accion")
        fase = int(a.get("fase", 1))
        fases.setdefault(fase, []).append({"codigo": cod, "titulo": a.get("titulo"),
                                           "critica": bool(a.get("critica")),
                                           "reversible": bool(a.get("reversible"))})
        minutos += _MINUTOS.get(cod, 10)
        try:
            a["params"] = json.loads(a.get("params_json") or "{}")
        except Exception:
            a["params"] = {}
        rol = next((v[3] for k, v in _MAPA_VARIABLE.items() if v[0] == cod), "GERENTE")
        responsables.add(rol)
    criticas = [a["titulo"] for a in acciones if a.get("critica")]
    return {
        "id_plan": id_plan, "nombre": plan.get("nombre"), "estado": plan.get("estado"),
        "modo": plan.get("modo"), "riesgo": plan.get("riesgo"), "confianza": plan.get("confianza"),
        "fases": {f: fases[f] for f in sorted(fases)},
        "num_acciones": len(acciones), "num_fases": len(fases),
        "acciones_criticas": criticas,
        "responsables": sorted(r for r in responsables if r),
        "tiempo_estimado_min": minutos,
        "impacto": ("Cambios propuestos de forma gobernada; las acciones criticas requieren "
                    "aprobacion explicita." if criticas else "Acciones seguras y reversibles."),
    }
