"""
Catalogo de TIPOS de evento (Fase 1).

Es un catalogo SEMILLA, no una lista cerrada: `publicar()` admite cualquier codigo de
tipo (el sistema esta preparado para miles de tipos futuros). Los tipos aqui declarados
se siembran en `eventos_tipo` (idempotente) para documentacion, prioridad por defecto y
futuras reglas. Formato: codigo -> (categoria, descripcion, prioridad_defecto).
"""

from src.services.eventos import prioridades as P

CATALOGO = {
    # ── Catalogo / articulos / precios ──
    "ARTICULO_CREADO":        ("catalogo", "Alta de articulo", P.MEDIA),
    "ARTICULO_MODIFICADO":    ("catalogo", "Modificacion de articulo", P.MEDIA),
    "ARTICULO_ELIMINADO":     ("catalogo", "Baja de articulo", P.ALTA),
    "PRECIO_ACTUALIZADO":     ("catalogo", "Actualizacion de precio", P.ALTA),
    "PROMOCION_PUBLICADA":    ("catalogo", "Promocion/oferta publicada", P.ALTA),
    "PROMOCION_FINALIZADA":   ("catalogo", "Promocion/oferta finalizada", P.MEDIA),
    # ── CRM / terceros ──
    "CLIENTE_CREADO":         ("crm", "Alta de cliente", P.MEDIA),
    "CLIENTE_MODIFICADO":     ("crm", "Modificacion de cliente", P.BAJA),
    "PROVEEDOR_ACTUALIZADO":  ("compras", "Modificacion de proveedor", P.BAJA),
    # ── Facturacion / cobros ──
    "FACTURA_GENERADA":       ("facturacion", "Factura emitida", P.ALTA),
    "FACTURA_ANULADA":        ("facturacion", "Factura anulada", P.ALTA),
    "FACTURA_RECTIFICADA":    ("facturacion", "Factura rectificada", P.ALTA),
    "COBRO_REGISTRADO":       ("tesoreria", "Cobro registrado", P.MEDIA),
    # ── Compras / recepcion ──
    "PEDIDO_RECIBIDO":        ("compras", "Pedido/recepcion registrada", P.MEDIA),
    # ── Documentos ──
    "DOCUMENTO_PUBLICADO":    ("documentos", "Documento registrado/publicado", P.MEDIA),
    # ── Seguridad / usuarios ──
    "USUARIO_CREADO":         ("seguridad", "Alta de usuario", P.MEDIA),
    "USUARIO_BLOQUEADO":      ("seguridad", "Usuario bloqueado", P.ALTA),
    "ROL_MODIFICADO":         ("seguridad", "Rol/permiso modificado", P.ALTA),
    # ── RRHH ──
    "CONTRATO_GENERADO":      ("rrhh", "Contrato generado", P.MEDIA),
    "NOMINA_GENERADA":        ("rrhh", "Nomina generada", P.MEDIA),
    # ── Inventario / stock / logistica ──
    "INVENTARIO_CORREGIDO":   ("inventario", "Ajuste de inventario", P.ALTA),
    "MERMA_REGISTRADA":       ("inventario", "Merma registrada", P.MEDIA),
    "REPOSICION_GENERADA":    ("reposicion", "Propuesta de reposicion generada", P.MEDIA),
    "KARDEX_MOVIMIENTO":      ("kardex", "Movimiento de kardex", P.BAJA),
    # ── Correo / comunicaciones ──
    "CORREO_RECIBIDO":        ("correo", "Correo recibido", P.MEDIA),
    "CORREO_ENVIADO":         ("correo", "Correo enviado", P.BAJA),
    # ── Sistema / operacion ──
    "BACKUP_FINALIZADO":      ("sistema", "Copia de seguridad finalizada", P.INFORMATIVA),
    "SINCRONIZACION_COMPLETADA": ("sistema", "Sincronizacion completada", P.INFORMATIVA),
    # ── Integracion Fase 2 (modulos restantes) ──
    "VENTA_REGISTRADA":       ("ventas", "Venta/ticket registrado", P.MEDIA),
    "UBICACION_ASIGNADA":     ("ubicaciones", "Ubicacion asignada a articulo", P.BAJA),
    "ASIENTO_CONTABILIZADO":  ("contabilidad", "Asiento contable creado", P.BAJA),
    "WORKFLOW_INICIADO":      ("workflow", "Instancia de workflow iniciada", P.MEDIA),
    "BI_SNAPSHOT_GENERADO":   ("bi", "Snapshot de BI generado", P.INFORMATIVA),
}


def categoria(codigo) -> str | None:
    v = CATALOGO.get(codigo)
    return v[0] if v else None


def prioridad_defecto(codigo) -> str:
    v = CATALOGO.get(codigo)
    return v[2] if v else P.MEDIA


def sembrar(cur) -> int:
    """Inserta (idempotente) el catalogo semilla en eventos_tipo. Devuelve nº de tipos."""
    n = 0
    for codigo, (cat, desc, prio) in CATALOGO.items():
        cur.execute(
            "INSERT INTO eventos_tipo (codigo, categoria, descripcion, prioridad_defecto) "
            "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE categoria=VALUES(categoria), "
            "descripcion=VALUES(descripcion)",
            (codigo, cat, desc, prio))
        n += 1
    return n
