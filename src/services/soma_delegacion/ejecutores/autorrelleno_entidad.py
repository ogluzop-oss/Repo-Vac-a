"""
Ejecutor de delegación — Autorrelleno GENÉRICO de entidades (Clientes/Proveedores, y cualquier
otra que se registre aquí en el futuro): a diferencia de `ejecutores.centros` (copia determinista
1:1 desde los datos corporativos de la empresa, sin IA — tiene sentido porque un Centro es
infraestructura de la PROPIA empresa), un Cliente o un Proveedor no tiene un "espejo" tan directo
del que copiar — lo que se repite entre altas es más bien una POLÍTICA POR DEFECTO (plazo de
pago, régimen fiscal, divisa…) que el SUPERADMIN describe en las instrucciones. Por eso aquí SÍ se
llama a SOMA: se le pasan los campos que están vacíos y los que ya se conocen del registro, y
decide qué rellenar según la política descrita — nunca toca un campo que ya tenga valor.

Reutiliza el CRUD real de cada dominio (`db.clientes.actualizar_cliente`,
`db.proveedores.actualizar_proveedor`); nunca escribe a las tablas directamente.
"""

import logging

logger = logging.getLogger("soma_delegacion.ejecutores.autorrelleno_entidad")

# Campos candidatos a autorrelleno por entidad — deliberadamente solo los de "política por
# defecto", nunca identificadores/nombres/NIF (esos SIEMPRE los decide la persona que da de alta).
_CAMPOS_CLIENTE = ("pais", "provincia", "poblacion", "condiciones_pago", "regimen_fiscal")
_CAMPOS_PROVEEDOR = ("divisa", "forma_pago", "plazo_pago", "pedido_minimo")


def _vacio(valor) -> bool:
    return valor is None or str(valor).strip() in ("", "0", "0.0", "0.00")


def _autorrellenar_generico(regla, *, id_empresa, usuario, entidad_nombre, campos_candidatos,
                            registro, actualizar_fn, id_registro) -> dict:
    from src.services.soma_delegacion.motor import MOTIVOS_LEGIBLES, preguntar_soma

    vacios = [c for c in campos_candidatos if _vacio(registro.get(c))]
    if not vacios:
        return {"ok": True, "estado": "descartado", "decision": None,
               "detalle": f"El {entidad_nombre} ya tenía todos sus datos completos "
                         "(nada que autorrellenar)."}
    conocidos = {k: registro.get(k) for k in campos_candidatos if not _vacio(registro.get(k))}
    conocidos_txt = ", ".join(f"{k}={v}" for k, v in conocidos.items()) or "(ninguno todavía)"

    prompt = (
        f"Eres SOMA, el asistente de IA de un ERP, autorrellenando los datos de un {entidad_nombre} "
        "RECIÉN CREADO, según la política por defecto que describe el administrador. SOLO puedes "
        "proponer valores para los campos VACÍOS listados abajo — nunca toques ni sugieras cambiar "
        "un campo que ya tiene valor. Si para algún campo vacío no tienes base suficiente en las "
        "instrucciones para decidir con seguridad, omítelo (mejor dejarlo vacío que inventar).\n\n"
        f"Política del administrador:\n\"\"\"\n{regla.get('instrucciones', '')}\n\"\"\"\n\n"
        f"Campos VACÍOS a rellenar (si procede): {', '.join(vacios)}\n"
        f"Campos que YA tienen valor (contexto, no los toques): {conocidos_txt}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON cuyas claves sean un subconjunto de los campos "
        "vacíos listados arriba, con el valor propuesto para cada uno que sí puedas decidir. Si "
        "ninguno procede, responde {}."
    )
    r = preguntar_soma(prompt, id_empresa=id_empresa, usuario=usuario,
                       tarea="soma_delegacion_autorrelleno")
    if not r.get("ok"):
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": MOTIVOS_LEGIBLES.get(r.get("motivo"), "No se pudo evaluar el autorrelleno.")}

    datos = r["datos"]
    cambios = {k: v for k, v in datos.items() if k in vacios and not _vacio(v)}
    if not cambios:
        return {"ok": True, "estado": "descartado", "decision": datos,
               "detalle": "SOMA no encontró ningún valor seguro que proponer."}

    ok = actualizar_fn(id_registro, id_empresa=id_empresa, **cambios)
    return {"ok": ok, "estado": "aplicado" if ok else "error", "decision": {"cambios": cambios},
           "detalle": (f"Autorrellenados: {', '.join(cambios)}." if ok
                      else "No se pudo guardar el autorrelleno.")}


# ── Cliente ───────────────────────────────────────────────────────────────────
def contexto_desde_evento_cliente(ev: dict) -> dict | None:
    id_cliente = ev.get("ref_id")
    return {"id_cliente": id_cliente} if id_cliente else None


def ejecutar_autorrelleno_cliente(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    id_cliente = contexto.get("id_cliente")
    if not id_cliente:
        return {"ok": False, "estado": "error", "decision": None, "detalle": "Falta el cliente."}
    from src.db import clientes as cli_db
    registro = cli_db.obtener_cliente(id_cliente)
    if not registro or str(registro.get("id_empresa")) != str(id_empresa):
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": "El cliente no existe o no pertenece a esta empresa."}
    return _autorrellenar_generico(regla, id_empresa=id_empresa, usuario=usuario,
                                   entidad_nombre="cliente", campos_candidatos=_CAMPOS_CLIENTE,
                                   registro=registro, actualizar_fn=cli_db.actualizar_cliente,
                                   id_registro=id_cliente)


# ── Proveedor ─────────────────────────────────────────────────────────────────
def contexto_desde_evento_proveedor(ev: dict) -> dict | None:
    id_proveedor = ev.get("ref_id")
    return {"id_proveedor": id_proveedor} if id_proveedor else None


def ejecutar_autorrelleno_proveedor(regla: dict, contexto: dict, *, id_empresa, usuario=None) -> dict:
    id_proveedor = contexto.get("id_proveedor")
    if not id_proveedor:
        return {"ok": False, "estado": "error", "decision": None, "detalle": "Falta el proveedor."}
    from src.db import proveedores as prov_db
    registro = prov_db.obtener_proveedor(id_proveedor, id_empresa=id_empresa)
    if not registro:
        return {"ok": False, "estado": "error", "decision": None,
               "detalle": "El proveedor no existe o no pertenece a esta empresa."}
    return _autorrellenar_generico(regla, id_empresa=id_empresa, usuario=usuario,
                                   entidad_nombre="proveedor", campos_candidatos=_CAMPOS_PROVEEDOR,
                                   registro=registro, actualizar_fn=prov_db.actualizar_proveedor,
                                   id_registro=id_proveedor)
