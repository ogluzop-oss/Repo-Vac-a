"""
Identidad Operativa de Centros (IOC) — punto único de verdad para identificar cualquier entidad
operativa del ERP (empresa → centro → instalación → unidad → terminal → usuario).

Capa de servicios de dominio REUTILIZABLE. Ninguna GUI debe acceder directamente a las tablas:
todo pasa por estos servicios. Construido sobre las entidades existentes (`empresas`,
`centros_trabajo`, `tiendas`, `almacen`) sin duplicarlas y conservando la feature legada
`configuraciones.ref_tienda/ref_almacen` (patrón Strangler).
"""
