"""
Router /replenishment — Reposición (Ajuste post-lanzamiento · Módulo 7): réplica EXACTA de la tabla
"ESTADO REPOSICIÓN" de escritorio (`gui/informe_reposicion.py::_EstadoReposicionPage`), a petición
explícita del usuario ("comparta exactamente los mismos datos... la misma tabla").

Consume `services.ia.adaptadores.articulos_bajo_umbral` directamente — YA aplica el mismo criterio que
esa pestaña (`Stock_tienda < Stock_esperado * 0.7 AND Stock_total > 0`, vía `db.articulos.
listar_para_reposicion`), ya tenant-safe, sin límite de filas (igual que escritorio). Los campos se
renombran a los nombres de columna de escritorio (`stock_almacen`/`stock_lineal`/`stock_esperado`).

`services.prediccion.recomendaciones.recomendaciones_reposicion` (usada por este endpoint hasta esta
fase) añadía una capa de riesgo/tendencia/recomendación derivada de un forecast agregado — datos que NO
existen en la tabla de escritorio. Se deja de usar aquí (sin ningún otro llamador en el proyecto, se
confirmó por grep) pero no se borra.

Sin permiso RBAC dedicado todavía (igual que `/losses`/`/location`/`/articles`/`/labels`): exige solo
autenticación.
"""

from src.api.security import requiere_auth


def registrar(bp):
    @bp.get("/replenishment")
    @requiere_auth()
    def replenishment_listar():
        from flask import g, jsonify
        from src.services.ia import adaptadores
        filas = adaptadores.articulos_bajo_umbral(g.ctx["id_empresa"])
        items = [{"codigo": f.get("codigo"), "nombre": f.get("nombre"),
                  "stock_almacen": f.get("stock_almacen"), "stock_lineal": f.get("stock_tienda"),
                  "stock_esperado": f.get("objetivo")} for f in filas]
        return jsonify(items)
