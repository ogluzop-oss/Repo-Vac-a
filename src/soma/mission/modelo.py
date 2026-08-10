"""
Modelo del Mission Engine (Fase 6): Misión + Tareas (con dependencias, estados y progreso). Estructuras
ligeras; la lógica vive en el motor. Sin Qt.
"""

import time

# ── Estados de tarea ──────────────────────────────────────────────────────────
T_PENDIENTE = "PENDIENTE"
T_EN_CURSO = "EN_CURSO"
T_HECHA = "HECHA"
T_FALLIDA = "FALLIDA"
T_OMITIDA = "OMITIDA"
T_ESPERA_APROB = "ESPERANDO_APROBACION"
T_TERMINALES = {T_HECHA, T_FALLIDA, T_OMITIDA}

# ── Estados de misión ─────────────────────────────────────────────────────────
M_PLANIFICADA = "PLANIFICADA"
M_EN_CURSO = "EN_CURSO"
M_PAUSADA = "PAUSADA"
M_ESPERA_APROB = "ESPERANDO_APROBACION"
M_COMPLETADA = "COMPLETADA"
M_CANCELADA = "CANCELADA"
M_FALLIDA = "FALLIDA"

# ── Prioridades ───────────────────────────────────────────────────────────────
P_CRITICA, P_ALTA, P_NORMAL, P_BAJA = "CRITICA", "ALTA", "NORMAL", "BAJA"
_ORDEN_P = {P_CRITICA: 3, P_ALTA: 2, P_NORMAL: 1, P_BAJA: 0}


def orden_prioridad(p) -> int:
    return _ORDEN_P.get(str(p).upper(), 1)


class Tarea:
    def __init__(self, clave, titulo, *, dominio=None, deps=None, paralelo=True,
                 especialista=None, eta_min=1, critica=False):
        self.clave = clave
        self.titulo = titulo
        self.dominio = dominio
        self.deps = list(deps or [])
        self.paralelo = paralelo
        self.especialista = especialista or dominio
        self.eta_min = eta_min
        self.critica = critica
        self.estado = T_PENDIENTE
        self.progreso = 0
        self.resultado = None      # dict {texto, fuentes, ...}
        self.error = None

    def to_dict(self):
        return {"clave": self.clave, "titulo": self.titulo, "dominio": self.dominio,
                "deps": self.deps, "estado": self.estado, "progreso": self.progreso,
                "especialista": self.especialista, "eta_min": self.eta_min,
                "resultado": (self.resultado or {}).get("texto") if self.resultado else None}


class Mision:
    def __init__(self, objetivo, *, plantilla=None, prioridad=P_NORMAL, usuario=None,
                 id_empresa=None):
        self.id = None                    # id en BD (soma_misiones)
        self.objetivo = objetivo
        self.plantilla = plantilla
        self.prioridad = prioridad
        self.usuario = usuario
        self.id_empresa = id_empresa
        self.estado = M_PLANIFICADA
        self.tareas = []                  # [Tarea]
        self.creada = time.time()
        self.cerrada = None
        self.resultado = None             # dict consolidado
        self.aprobaciones = 0
        self.errores = 0
        self._pausada = False
        self._cancelada = False

    # Helpers de coordinación
    def por_clave(self, clave):
        return next((t for t in self.tareas if t.clave == clave), None)

    def listas(self):
        """Tareas cuyas dependencias están ya HECHAS y aún están PENDIENTES."""
        hechas = {t.clave for t in self.tareas if t.estado == T_HECHA}
        return [t for t in self.tareas
                if t.estado == T_PENDIENTE and all(d in hechas for d in t.deps)]

    def pendientes(self):
        return [t for t in self.tareas if t.estado not in T_TERMINALES]

    def especialistas_usados(self):
        return sorted({t.especialista for t in self.tareas if t.especialista and t.estado == T_HECHA})

    def to_dict(self):
        return {"id": self.id, "objetivo": self.objetivo, "prioridad": self.prioridad,
                "estado": self.estado, "tareas": [t.to_dict() for t in self.tareas],
                "especialistas": self.especialistas_usados(), "aprobaciones": self.aprobaciones,
                "errores": self.errores}
