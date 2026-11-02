"""
Vínculo real empleado <-> fila de horario (RRHH Fase A, punto 6 del plan de "bolsa de horas").

Contexto: `documentos/horarios.json` (leído/escrito por `src/gui/horarios_gui.py::_h_cargar_horarios`/
`_h_guardar_horarios`, delegando la rejilla en `src/rrhh/gui/horarios.py::_HorarioGrid.get_state`/
`set_state`) guarda cada fila de la rejilla semanal como texto libre en `grid["names"][i]`
(`QLineEdit` editable, ver `_HorarioGrid.employee_names`/`_name_edits`). No hay ningún `id_empleado`
real detrás de esa fila: es puramente cosmético.

Este módulo NO toca `horarios_gui.py` ni `rrhh/gui/horarios.py` (su lectura/escritura/render quedan
intactos — esa migración de UI es responsabilidad de la Fase E, un agente posterior). Lo que sí hace
es preparar el terreno para que la Fase E pueda depender de un `id_empleado` real por fila:

- `resolver_ids_por_nombres`: intenta casar cada nombre libre con un `rrhh_empleados` real
  (comparación normalizada de "nombre" y "nombre apellidos"), best-effort, sin garantías — nombres
  que no casen con ningún empleado devuelven `None` en esa posición.
- `nombre_para_id`: resuelve un `id_empleado` real a su nombre para mostrar (uso en Fase E al pintar
  la rejilla).
- `normalizar_grid`: dado UN `grid` (el dict `{"names":[...], "colors":[...], "schedule":{...},
  "absences":{...}}` tal como lo guarda `_HorarioGrid.get_state`), devuelve una COPIA con una clave
  nueva `"ids"` añadida (lista alineada 1:1 con `"names"`, mismo orden/longitud) con el mejor id
  resuelto por fila (o `None`). No modifica ni borra `"names"` — se mantiene como fallback de
  visualización para filas sin id resuelto. `"ids"` es el nuevo campo que la Fase E debe tratar como
  la fuente de verdad para saber "qué empleado real es esta fila"; `"names"` pasa a ser derivado
  (texto de respaldo) en vez de la fuente de verdad.
- `migrar_horarios_json`: conversor de un solo uso (opcional, no se ejecuta automáticamente en ningún
  arranque de la app) que lee TODO `documentos/horarios.json`, añade `"ids"` a cada semana/grid y
  reescribe el fichero. Es seguro ejecutarlo más de una vez (idempotente: si `"ids"` ya existe con el
  mismo tamaño que `"names"`, no lo vuelve a resolver, solo rellena huecos `None`).
- `cargar_horarios_json_normalizado`: variante de solo lectura (no escribe en disco) que devuelve los
  datos ya normalizados en memoria — pensada para que la Fase E la use directamente al pintar la
  rejilla sin tener que ejecutar antes el conversor de fichero.

Qué NO hace esta pieza (deliberado, a cargo de la Fase E):
- No cambia `_HorarioGrid`/`_HorarioSemana`/`_h_cargar_horarios`/`_h_guardar_horarios` para que dejen
  de escribir el `"names"` de texto libre o empiecen a escribir `"ids"` al guardar.
- No añade el desplegable de empleados (`QComboBox`) ni la exclusión mutua entre filas.
- No decide qué pasa si dos filas resuelven al mismo empleado (deduplicación) — al ser solo lectura/
  preparación de datos, dos filas pueden apuntar al mismo id si sus nombres eran ambiguos; la Fase E,
  que sí conoce la regla de "exclusión mutua" del desplegable, deberá decidir cómo tratarlo.
"""

import datetime as _dt
import json
import logging
import os
import re

logger = logging.getLogger("rrhh.horarios_vinculo_empleado")

RUTA_HORARIOS_JSON = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "documentos", "horarios.json")
)

_RE_LUNES_TITULO = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _normalizar_texto(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _mapa_empleados(id_empresa=None) -> dict:
    """{nombre_normalizado -> id, "nombre apellidos"_normalizado -> id} de empleados activos+inactivos
    de la empresa (para no perder el vínculo si un empleado ya causó baja)."""
    from src.rrhh.db.empleados import listar_empleados

    empleados = listar_empleados(id_empresa=id_empresa) or []
    mapa = {}
    for e in empleados:
        eid = e.get("id")
        nombre = (e.get("nombre") or "").strip()
        apellidos = (e.get("apellidos") or "").strip()
        if not eid or not nombre:
            continue
        mapa.setdefault(_normalizar_texto(nombre), eid)
        if apellidos:
            mapa.setdefault(_normalizar_texto(f"{nombre} {apellidos}"), eid)
    return mapa


def resolver_ids_por_nombres(nombres: list, id_empresa=None) -> list:
    """Best-effort: para cada nombre libre de `grid["names"]`, intenta encontrar el `rrhh_empleados.id`
    correspondiente (match exacto normalizado de "nombre" o "nombre apellidos"). Devuelve una lista del
    mismo tamaño, con `None` en las posiciones sin match (nombre vacío, empleado no encontrado, o
    nombre ambiguo/no-real como "Empleado 2")."""
    mapa = _mapa_empleados(id_empresa=id_empresa)
    resultado = []
    for n in (nombres or []):
        clave = _normalizar_texto(n)
        resultado.append(mapa.get(clave) if clave else None)
    return resultado


def nombre_para_id(id_empleado, id_empresa=None) -> str | None:
    """Resuelve un id_empleado real a "Nombre Apellidos" para pintar la rejilla (uso en Fase E)."""
    if not id_empleado:
        return None
    from src.rrhh.db.empleados import obtener_empleado

    e = obtener_empleado(id_empleado, id_empresa=id_empresa)
    if not e:
        return None
    nombre = (e.get("nombre") or "").strip()
    apellidos = (e.get("apellidos") or "").strip()
    return f"{nombre} {apellidos}".strip() if apellidos else nombre


def normalizar_grid(grid: dict, id_empresa=None) -> dict:
    """Devuelve una COPIA de `grid` con la clave `"ids"` añadida/completada (lista alineada con
    `"names"`). No muta el dict de entrada. Si `"ids"` ya existe y tiene el tamaño correcto, solo
    rellena las posiciones `None`/faltantes por resolución de nombre; las ya resueltas se respetan
    (para no pisar una asignación ya hecha manualmente por la Fase E en el futuro)."""
    nuevo = dict(grid)
    names = list(grid.get("names", []))
    ids_previos = list(grid.get("ids", []))
    if len(ids_previos) < len(names):
        ids_previos += [None] * (len(names) - len(ids_previos))
    elif len(ids_previos) > len(names):
        ids_previos = ids_previos[: len(names)]

    faltan_por_resolver = any(i is None for i in ids_previos) if ids_previos else True
    if faltan_por_resolver and names:
        resueltos = resolver_ids_por_nombres(names, id_empresa=id_empresa)
        ids_finales = [
            (prev if prev is not None else resueltos[idx])
            for idx, prev in enumerate(ids_previos)
        ]
    else:
        ids_finales = ids_previos

    nuevo["ids"] = ids_finales
    return nuevo


def cargar_horarios_json_normalizado(ruta: str = None, id_empresa=None) -> list:
    """Lectura de SOLO MEMORIA (no escribe en disco): carga `documentos/horarios.json` (o `ruta`) y
    devuelve la lista de semanas con cada `grid` normalizado (clave `"ids"` añadida). Tolera tanto el
    formato legado (solo `"names"`) como uno ya migrado (con `"ids"`). Si el fichero no existe o está
    vacío/corrupto, devuelve `[]`."""
    ruta = ruta or RUTA_HORARIOS_JSON
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("cargar_horarios_json_normalizado: no se pudo leer %s: %s", ruta, e)
        return []
    if not isinstance(data, list):
        return []

    salida = []
    for semana in data:
        semana = dict(semana)
        grid = semana.get("grid")
        if isinstance(grid, dict):
            semana["grid"] = normalizar_grid(grid, id_empresa=id_empresa)
        salida.append(semana)
    return salida


def migrar_horarios_json(ruta: str = None, id_empresa=None) -> dict:
    """Conversor de un solo uso: añade `"ids"` a cada `grid` de `documentos/horarios.json` y
    REESCRIBE el fichero. Idempotente (segura de ejecutar más de una vez). Devuelve un resumen
    `{"ruta", "semanas", "filas_totales", "filas_resueltas", "filas_sin_resolver"}`.

    No se invoca automáticamente desde ningún arranque de la app — es una utilidad para que la Fase E
    (o un operador) la ejecute manualmente cuando esté lista la UI que consume `"ids"`."""
    ruta = ruta or RUTA_HORARIOS_JSON
    resumen = {"ruta": ruta, "semanas": 0, "filas_totales": 0, "filas_resueltas": 0,
               "filas_sin_resolver": 0}
    if not os.path.exists(ruta):
        logger.info("migrar_horarios_json: %s no existe, nada que migrar.", ruta)
        return resumen
    try:
        with open(ruta, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("migrar_horarios_json: no se pudo leer %s: %s", ruta, e)
        return resumen
    if not isinstance(data, list):
        return resumen

    for semana in data:
        grid = semana.get("grid")
        if not isinstance(grid, dict):
            continue
        semana["grid"] = normalizar_grid(grid, id_empresa=id_empresa)
        ids = semana["grid"].get("ids", [])
        resumen["semanas"] += 1
        resumen["filas_totales"] += len(ids)
        resumen["filas_resueltas"] += sum(1 for i in ids if i is not None)
        resumen["filas_sin_resolver"] += sum(1 for i in ids if i is None)

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("migrar_horarios_json: %s migrado (%s).", ruta, resumen)
    return resumen


# ── Grid → tabla real: sincronización de VACACIONES (cierre de brecha) ─────────
# `normalizar_grid`/`cargar_horarios_json_normalizado` (arriba) resuelven `"ids"` para que la
# rejilla SEPA qué empleado real es cada fila; lo que sigue usa ese mismo `"ids"` para completar
# el sentido inverso del patrón ya usado por `bolsa_horas._festivos_y_bajas_desde_horarios`
# (grid → fechas reales, solo lectura): aquí, grid → ESCRITURA en `rrhh_vacaciones` vía
# `vacaciones_servicio.sincronizar_dias_horario` — la MISMA tabla/motor que usa el diálogo
# "Vacaciones y ausencias", nunca un mecanismo paralelo.

def lunes_de_titulo(titulo: str) -> "_dt.date | None":
    """Extrae la fecha de INICIO (lunes) de un título de semana con el formato del placeholder
    ("Semana DD/MM/AAAA – DD/MM/AAAA"). El título es texto LIBRE editado por el usuario — si no
    encaja ningún patrón `DD/MM/AAAA`, devuelve `None` (esa semana no se puede sincronizar contra
    fechas reales; mismo criterio/limitación conocida que `bolsa_horas._lunes_de_titulo_semana`)."""
    m = _RE_LUNES_TITULO.search(titulo or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        return _dt.date(y, mo, d)
    except ValueError:
        return None


def sincronizar_vacaciones_horario(semanas: list, id_empresa=None) -> None:
    """Sincroniza los días marcados como VACACIONES en la rejilla de Horarios contra
    `rrhh_vacaciones`, para que "Vacaciones y ausencias" y el cálculo de Finiquito reflejen
    automáticamente lo que un admin/SUPERADMIN marca en Horarios (sin doble registro manual).

    `semanas`: lista de estados tal como los devuelve `_HorarioSemana.get_state()`
    (`{"title": ..., "grid": {"ids": [...], "absences": {...}}}`), una por semana visible en la
    ventana de Horarios — pensada para llamarse desde `gui/horarios_gui.py::_h_guardar_horarios`
    justo antes de persistir `documentos/horarios.json`.

    Por cada semana con título reconocible (`lunes_de_titulo`) y por cada fila con `id_empleado`
    resuelto, calcula el conjunto de fechas marcadas "VACACIONES" y delega en
    `vacaciones_servicio.sincronizar_dias_horario` (upsert/borrado idempotente, un registro por
    día). Un empleado de la semana SIN ningún día marcado también se sincroniza con conjunto
    vacío, para que un des-marcado total borre lo que hubiera quedado de un guardado anterior.
    Best-effort y bulletproof por semana/empleado: un fallo puntual (BD, fila corrupta) se
    registra en el log y no interrumpe el resto de la sincronización ni el guardado del horario."""
    from src.rrhh import vacaciones_servicio as _VS

    for semana in semanas or []:
        grid = semana.get("grid") or {}
        ids = grid.get("ids") or []
        if not any(ids):
            continue
        lunes = lunes_de_titulo(semana.get("title", ""))
        if lunes is None:
            continue
        domingo = lunes + _dt.timedelta(days=6)
        absences = grid.get("absences") or {}

        marcados_por_empleado: dict = {}
        for k, info in absences.items():
            try:
                e_idx_str, dia_idx_str = k.split(",")
                e_idx, dia_idx = int(e_idx_str), int(dia_idx_str)
            except Exception:
                continue
            if not (0 <= e_idx < len(ids)) or not (0 <= dia_idx <= 6):
                continue
            id_emp = ids[e_idx]
            if not id_emp:
                continue
            texto = str((info or {}).get("text", "")).strip().upper()
            if texto != "VACACIONES":
                continue
            fecha = lunes + _dt.timedelta(days=dia_idx)
            marcados_por_empleado.setdefault(id_emp, set()).add(fecha)

        for id_emp in {i for i in ids if i}:
            dias = marcados_por_empleado.get(id_emp, set())
            try:
                _VS.sincronizar_dias_horario(id_emp, dias, lunes, domingo, id_empresa=id_empresa)
            except Exception as e:
                logger.error("sincronizar_vacaciones_horario(emp=%s, semana=%s): %s",
                            id_emp, semana.get("title"), e)
