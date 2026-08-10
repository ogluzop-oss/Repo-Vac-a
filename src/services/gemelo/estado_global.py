"""
Estado global empresarial del Gemelo Digital (Paquete Enterprise 8, SUBFASE 8.2).

Mantiene la foto viva de la organizacion: empresa, tiendas, almacenes, delegaciones, sucursales,
filiales, departamentos, usuarios, terminales/TPV, contratos, pedidos, facturas, incidencias,
tareas, workflows, sincronizacion y automatizaciones. Todo se DERIVA de fuentes existentes
(organigrama de Gobierno, Centro de Actividad/Sincronizacion, automatizacion, BD operativa). No
duplica datos: cuenta y agrega bajo demanda.
"""

from src.services.gemelo import fuentes as F
from src.services.gemelo import modelo as M


def _por_tipo(mapa) -> dict:
    d = {}
    for n in mapa:
        d[n.get("tipo")] = d.get(n.get("tipo"), 0) + 1
    return d


def estado(id_empresa=None) -> dict:
    emp = F.emp(id_empresa)
    org = F.organigrama(emp)
    por_tipo = _por_tipo(org)

    infra = F.infraestructura(emp)
    terminales = infra.get("terminales", []) or []
    glob = infra.get("global", {}) or {}
    tiendas_offline = len([t for t in F.sync_panel(emp)
                           if str(t.get("estado")).upper() == "OFFLINE"])

    # Entidades operativas (best-effort; conteos, nunca copia de datos).
    pedidos_pend = F.contar("SELECT COUNT(*) FROM compras_pedidos WHERE id_empresa=%s "
                            "AND estado IN ('BORRADOR','ENVIADO','PENDIENTE','PARCIAL')", (emp,))
    facturas_pend = F.contar("SELECT COUNT(*) FROM facturas_cliente WHERE id_empresa=%s "
                             "AND estado IN ('pendiente','emitida','impagada')", (emp,))
    contratos_venc = F.contar("SELECT COUNT(*) FROM rrhh_contratos WHERE id_empresa=%s "
                              "AND fecha_fin IS NOT NULL AND fecha_fin BETWEEN CURDATE() "
                              "AND (CURDATE() + INTERVAL 30 DAY)", (emp,))
    workflows_abiertos = F.contar("SELECT COUNT(*) FROM wf_instancias WHERE id_empresa=%s "
                                  "AND estado IN ('EN_CURSO','PENDIENTE')", (emp,))
    incidencias = F.contar("SELECT COUNT(*) FROM tickets WHERE id_empresa=%s "
                           "AND estado NOT IN ('cerrado','resuelto','anulado')", (emp,))
    autos_pend = F.pendientes_automatizacion(emp)

    ind = {
        "grupos": por_tipo.get("grupo", 0),
        "empresas": por_tipo.get("empresa", 0),
        "zonas": por_tipo.get("zona", 0),
        "delegaciones": por_tipo.get("delegacion", 0),
        "tiendas": por_tipo.get("tienda", 0),
        "almacenes": por_tipo.get("almacen", 0),
        "departamentos": por_tipo.get("departamento", 0),
        "usuarios": por_tipo.get("empleado", 0),
        "nodos_total": sum(por_tipo.values()),
        "terminales": len(terminales),
        "tiendas_offline": tiendas_offline,
        "pedidos_pendientes": pedidos_pend,
        "facturas_pendientes": facturas_pend,
        "contratos_por_vencer": contratos_venc,
        "workflows_abiertos": workflows_abiertos,
        "incidencias_abiertas": incidencias,
        "automatizaciones_pendientes": autos_pend,
        "sincronizacion": glob,
    }

    alertas = []
    riesgo = M.RIESGO_BAJO
    if tiendas_offline:
        alertas.append(f"{tiendas_offline} tienda(s) sin sincronizar (offline)")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_ALTO)
    if incidencias:
        alertas.append(f"{incidencias} incidencia(s) abiertas")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)
    if contratos_venc:
        alertas.append(f"{contratos_venc} contrato(s) por vencer (30 dias)")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)
    if autos_pend:
        alertas.append(f"{autos_pend} automatizacion(es) pendientes de decision")
        riesgo = M.peor_riesgo(riesgo, M.RIESGO_MEDIO)

    resumen = (f"{ind['tiendas']} tiendas, {ind['almacenes']} almacenes, {ind['usuarios']} usuarios; "
               f"{pedidos_pend} pedidos y {facturas_pend} facturas pendientes.")
    return M.estado_dominio("empresa", resumen=resumen, riesgo=riesgo, indicadores=ind,
                            alertas=alertas, detalle={"organigrama": org})
