"""
Fase Productividad · Campañas comerciales — objetivos EXPLÍCITAMENTE PARALELOS a los objetivos
ordinarios de `objetivos.py` (nunca los sustituyen ni se mezclan: una campaña tiene su propia
barra de progreso, acotada a sus propias fechas de inicio/fin, independiente del periodo
recurrente que esté seleccionado). Solo SUPERADMIN puede crearlas/editarlas (gate de RBAC en la
capa de llamada, vía permiso `productividad.editar`).
"""

from src.db.conexion import obtener_conexion
from src.services.productividad import facturacion as F
from src.services.productividad.objetivos import TIPOS_OBJETIVO


def crear_campana(nombre, fecha_inicio, fecha_fin, id_empresa, creado_por_id=None) -> int | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO productividad_campanas (id_empresa, nombre, fecha_inicio, fecha_fin, "
                "creado_por_id) VALUES (%s,%s,%s,%s,%s)",
                (id_empresa, nombre, fecha_inicio, fecha_fin, creado_por_id))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def listar_campanas(id_empresa) -> list[dict]:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, fecha_inicio, fecha_fin, creado_por_id FROM productividad_campanas "
                "WHERE id_empresa=%s ORDER BY fecha_inicio DESC", (id_empresa,))
            filas = cur.fetchall()
            out = []
            for f in filas:
                if isinstance(f, dict):
                    out.append(dict(f))
                else:
                    out.append({"id": f[0], "nombre": f[1], "fecha_inicio": f[2],
                                "fecha_fin": f[3], "creado_por_id": f[4]})
            return out
    except Exception:
        return []


def fijar_objetivo_campana(id_campana, tipo_objetivo, valor, id_empresa, *, centro_codigo=None,
                            usuario_id=None) -> int | None:
    """Fija (o reemplaza en sitio — una campaña no necesita versionado histórico, no se solapa con
    periodos recurrentes) el objetivo de UN centro o UN empleado dentro de la campaña."""
    if tipo_objetivo not in TIPOS_OBJETIVO:
        raise ValueError(f"tipo_objetivo inválido: {tipo_objetivo!r}")
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond = "id_campana=%s AND tipo_objetivo=%s"
            params = [id_campana, tipo_objetivo]
            if tipo_objetivo == "centro":
                cond += " AND centro_codigo=%s"; params.append(centro_codigo)
            else:
                cond += " AND usuario_id=%s"; params.append(usuario_id)
            cur.execute(f"SELECT id FROM productividad_campana_objetivos WHERE {cond}", tuple(params))
            existente = cur.fetchone()
            if existente:
                eid = existente[0] if not isinstance(existente, dict) else existente["id"]
                cur.execute("UPDATE productividad_campana_objetivos SET valor=%s WHERE id=%s",
                            (round(float(valor or 0), 2), eid))
                conn.commit()
                return eid
            cur.execute(
                "INSERT INTO productividad_campana_objetivos (id_campana, id_empresa, tipo_objetivo, "
                "centro_codigo, usuario_id, valor) VALUES (%s,%s,%s,%s,%s,%s)",
                (id_campana, id_empresa, tipo_objetivo, centro_codigo, usuario_id,
                 round(float(valor or 0), 2)))
            conn.commit()
            return cur.lastrowid
    except Exception:
        return None


def objetivo_campana(id_campana, tipo_objetivo, *, centro_codigo=None, usuario_id=None) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cond = "id_campana=%s AND tipo_objetivo=%s"
            params = [id_campana, tipo_objetivo]
            if tipo_objetivo == "centro":
                cond += " AND centro_codigo=%s"; params.append(centro_codigo)
            else:
                cond += " AND usuario_id=%s"; params.append(usuario_id)
            cur.execute(f"SELECT valor FROM productividad_campana_objetivos WHERE {cond}", tuple(params))
            r = cur.fetchone()
            if not r:
                return None
            valor = r[0] if not isinstance(r, dict) else r["valor"]
            return {"valor": float(valor)}
    except Exception:
        return None


def progreso_campana_centro(id_campana, id_tienda, centro_codigo, id_empresa) -> dict:
    camp = _obtener_campana(id_campana, id_empresa)
    if not camp:
        return {"objetivo": 0.0, "facturado": 0.0}
    obj = objetivo_campana(id_campana, "centro", centro_codigo=centro_codigo)
    facturado = F.facturado_centro(id_tienda, camp["fecha_inicio"], camp["fecha_fin"], id_empresa)
    return {"objetivo": (obj or {}).get("valor", 0.0), "facturado": facturado,
            "desde": camp["fecha_inicio"], "hasta": camp["fecha_fin"]}


def progreso_campana_empleado(id_campana, usuario_id, id_empresa) -> dict:
    camp = _obtener_campana(id_campana, id_empresa)
    if not camp:
        return {"objetivo": 0.0, "facturado": 0.0, "horas_trabajadas": 0.0}
    obj = objetivo_campana(id_campana, "empleado", usuario_id=usuario_id)
    valor_hora = (obj or {}).get("valor", 0.0)
    from src.db.usuario import horas_trabajadas_rango
    horas = horas_trabajadas_rango(usuario_id, camp["fecha_inicio"], camp["fecha_fin"],
                                    id_empresa=id_empresa)
    facturado = F.facturado_empleado(usuario_id, camp["fecha_inicio"], camp["fecha_fin"], id_empresa)
    return {"objetivo": round(valor_hora * horas, 2), "valor_hora": valor_hora,
            "horas_trabajadas": horas, "facturado": facturado,
            "desde": camp["fecha_inicio"], "hasta": camp["fecha_fin"]}


def _obtener_campana(id_campana, id_empresa) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT fecha_inicio, fecha_fin FROM productividad_campanas "
                "WHERE id=%s AND id_empresa=%s", (id_campana, id_empresa))
            r = cur.fetchone()
            if not r:
                return None
            if isinstance(r, dict):
                return {"fecha_inicio": r["fecha_inicio"], "fecha_fin": r["fecha_fin"]}
            return {"fecha_inicio": r[0], "fecha_fin": r[1]}
    except Exception:
        return None
