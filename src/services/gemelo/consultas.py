"""
Consultas instantaneas del Gemelo Digital (Paquete Enterprise 8, SUBFASE 8.10).

Responde de inmediato, desde el estado vivo del gemelo, a preguntas como:
  ¿Que estado tiene la empresa?  ¿Que ocurre en la tienda X?  ¿Que procesos estan abiertos?
  ¿Que recursos estan bloqueados?  ¿Que contratos vencen?  ¿Que pedidos estan pendientes?
  ¿Que almacenes presentan incidencias?

Nunca recorre todas las tablas: reutiliza los estados de dominio ya materializados por el motor
(cacheados y refrescados por eventos) y consultas puntuales de solo lectura.
"""

from src.services.gemelo import fuentes as F


def _svc():
    from src.services.gemelo import motor
    return motor.servicio()


def estado_empresa(id_empresa=None) -> dict:
    """¿Que estado tiene la empresa? — resumen ejecutivo agregado de todos los dominios."""
    return _svc().estado_global(id_empresa)


def estado_tienda(nombre_o_id, id_empresa=None) -> dict:
    """¿Que ocurre en la tienda X? — localiza la tienda en el organigrama y agrega su estado."""
    emp = F.emp(id_empresa)
    org = F.organigrama(emp)
    clave = str(nombre_o_id).strip().lower()
    tienda = next((n for n in org if n.get("tipo") == "tienda"
                   and (clave in str(n.get("nombre", "")).lower() or str(n.get("id")) == clave)), None)
    if not tienda:
        return {"encontrada": False, "texto": f"No encuentro la tienda «{nombre_o_id}»."}
    sync = next((t for t in F.sync_panel(emp)
                 if str(t.get("nombre", "")).lower() == str(tienda.get("nombre", "")).lower()), {})
    incidencias = F.contar("SELECT COUNT(*) FROM tickets WHERE id_empresa=%s "
                           "AND estado NOT IN ('cerrado','resuelto','anulado')", (emp,))
    return {
        "encontrada": True,
        "tienda": {"id": tienda.get("id"), "nombre": tienda.get("nombre"),
                   "estado_org": tienda.get("estado")},
        "sincronizacion": sync.get("estado", "DESCONOCIDO"),
        "incidencias_abiertas": incidencias,
        "texto": (f"Tienda {tienda.get('nombre')}: sincronizacion "
                  f"{str(sync.get('estado', 'desconocida')).lower()}, {incidencias} incidencias abiertas."),
    }


def procesos_abiertos(id_empresa=None) -> dict:
    """¿Que procesos estan abiertos? — workflows y automatizaciones pendientes."""
    emp = F.emp(id_empresa)
    wf = F.filas("SELECT id, estado FROM wf_instancias WHERE id_empresa=%s "
                 "AND estado IN ('EN_CURSO','PENDIENTE') ORDER BY id DESC LIMIT 50", (emp,))
    autos = F.pendientes_automatizacion(emp)
    return {"workflows_abiertos": len(wf), "workflows": wf, "automatizaciones_pendientes": autos,
            "texto": f"{len(wf)} workflows abiertos y {autos} automatizaciones pendientes."}


def recursos_bloqueados(id_empresa=None) -> dict:
    """¿Que recursos estan bloqueados? — terminales offline, usuarios bloqueados, tiendas sin sync."""
    emp = F.emp(id_empresa)
    infra = F.infraestructura(emp)
    term_off = [t for t in (infra.get("terminales", []) or [])
                if str(t.get("estado")).upper() == "OFFLINE"]
    tiendas_off = [t for t in F.sync_panel(emp) if str(t.get("estado")).upper() == "OFFLINE"]
    usuarios_bloq = F.contar("SELECT COUNT(*) FROM usuarios WHERE activo=0 "
                             "OR (bloqueado_hasta IS NOT NULL AND bloqueado_hasta > NOW())", ())
    return {"terminales_offline": len(term_off), "tiendas_offline": len(tiendas_off),
            "usuarios_bloqueados": usuarios_bloq,
            "texto": (f"{len(term_off)} terminales offline, {len(tiendas_off)} tiendas sin "
                      f"sincronizar, {usuarios_bloq} usuarios bloqueados.")}


def contratos_por_vencer(id_empresa=None, *, dias=30) -> dict:
    emp = F.emp(id_empresa)
    filas = F.filas("SELECT id, id_empleado, fecha_fin FROM rrhh_contratos WHERE id_empresa=%s "
                    "AND fecha_fin IS NOT NULL AND fecha_fin BETWEEN CURDATE() "
                    "AND (CURDATE() + INTERVAL %s DAY) ORDER BY fecha_fin", (emp, int(dias)))
    return {"total": len(filas), "contratos": filas,
            "texto": f"{len(filas)} contratos vencen en los proximos {dias} dias."}


def pedidos_pendientes(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)
    filas = F.filas("SELECT id, id_proveedor, estado, fecha FROM compras_pedidos WHERE id_empresa=%s "
                    "AND estado IN ('BORRADOR','ENVIADO','PENDIENTE','PARCIAL') "
                    "ORDER BY fecha DESC LIMIT 100", (emp,))
    return {"total": len(filas), "pedidos": filas,
            "texto": f"{len(filas)} pedidos de compra pendientes."}


def almacenes_con_incidencias(id_empresa=None) -> dict:
    """¿Que almacenes presentan incidencias? — cruza sincronizacion e incidencias por almacen/tienda."""
    emp = F.emp(id_empresa)
    problemas = [t for t in F.sync_panel(emp)
                 if str(t.get("estado")).upper() in ("OFFLINE", "ERROR")]
    return {"total": len(problemas), "almacenes": problemas,
            "texto": (f"{len(problemas)} almacenes/terminales con incidencias de sincronizacion."
                      if problemas else "Ningun almacen presenta incidencias de sincronizacion.")}
