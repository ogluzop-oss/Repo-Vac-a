"""
Memoria de TRABAJO de SOMA (Fase 5). Recuerda QUÉ está haciendo el usuario (tema, módulo, actividad
reciente) durante la sesión, para poder retomar el hilo ("continuemos donde lo dejamos") sin volver a
explicar el contexto. Es memoria de SESIÓN (en proceso); el último tema se persiste de forma ligera
en la memoria persistente para recuperar continuidad entre sesiones. No duplica la memoria
conversacional (propósito distinto: foco de trabajo, no historial).
"""

import time

_MODULO_LEGIBLE = {
    "tpv": "el TPV", "stock": "el inventario", "logistica": "las recepciones",
    "ventas": "las ventas", "compras": "los proveedores", "clientes_crm": "el CRM",
    "contabilidad": "la contabilidad", "tesoreria": "la tesorería", "bi": "el Centro de Inteligencia",
    "workflow": "las aprobaciones", "rrhh": "RRHH", "correo": "el correo",
    "reposicion": "la reposición", "mermas": "las mermas", "etiquetas": "las etiquetas",
}


class MemoriaTrabajo:
    def __init__(self):
        self._topico = None
        self._modulo = None
        self._ts = 0.0
        self._actividad = []   # [(ts, texto)] reciente

    def actualizar(self, *, topico=None, modulo=None):
        if topico:
            self._topico = topico
        if modulo:
            self._modulo = modulo
        self._ts = time.time()

    def anotar(self, texto):
        if texto:
            self._actividad.append((time.time(), str(texto)[:160]))
            self._actividad = self._actividad[-20:]
            self._ts = time.time()

    def hay_contexto(self) -> bool:
        return bool(self._topico or self._modulo or self._actividad)

    def foco(self) -> str:
        if self._topico:
            return self._topico
        if self._modulo:
            return _MODULO_LEGIBLE.get(self._modulo, self._modulo)
        return ""

    def resumen(self) -> str:
        foco = self.foco()
        if not foco:
            return ""
        return f"Hemos estado en {foco}."

    def retomar(self) -> str:
        foco = self.foco()
        if not foco:
            return "No teníamos nada a medias, pero dime en qué te ayudo."
        ult = self._actividad[-1][1] if self._actividad else ""
        extra = f" Lo último fue: {ult}." if ult else ""
        return f"Seguimos donde lo dejamos: {foco}.{extra}"

    def snapshot(self) -> dict:
        return {"topico": self._topico, "modulo": self._modulo,
                "actividad_reciente": [a[1] for a in self._actividad[-5:]]}
