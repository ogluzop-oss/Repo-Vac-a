"""
Bandeja de OPORTUNIDADES/RECOMENDACIONES de SOMA (Fase 7). Cuando SOMA decide NO interrumpir, guarda la
iniciativa aquí (memoria de sesión). El usuario puede pedir "¿qué has detectado hoy?", "muéstrame
oportunidades", "¿hay riesgos?", "¿qué me recomiendas?" y SOMA responde desde esta bandeja. Dedup por
clave con cooldown para no acumular repeticiones.
"""

import time

_COOLDOWN = 1800   # s antes de volver a listar el mismo aviso


class Bandeja:
    def __init__(self):
        self._items = {}   # clave → {iniciativa, ts}

    def añadir(self, ini):
        clave = ini.get("clave")
        if not clave:
            return
        m = self._items.get(clave)
        if m and (time.time() - m["ts"] < _COOLDOWN):
            m["iniciativa"] = ini   # actualiza contenido, mantiene ts
            return
        self._items[clave] = {"iniciativa": ini, "ts": time.time()}

    def añadir_muchas(self, inis):
        for i in inis or []:
            self.añadir(i)

    def listar(self, *, tipo=None, limite=6) -> list:
        vivos = sorted(self._items.values(), key=lambda m: m["ts"], reverse=True)
        out = [m["iniciativa"] for m in vivos]
        if tipo:
            out = [i for i in out if i.get("tipo") == tipo]
        # prioridad primero
        from src.soma import prioridad as P
        out.sort(key=lambda i: P.nivel(i.get("prioridad")), reverse=True)
        return out[:limite]

    def hay(self, tipo=None) -> bool:
        return bool(self.listar(tipo=tipo, limite=1))

    def obtener(self, clave):
        m = self._items.get(clave)
        return m["iniciativa"] if m else None

    def marcar(self, clave, estado):
        if clave in self._items:
            self._items[clave]["estado"] = estado

    def quitar(self, clave):
        self._items.pop(clave, None)

    def resumen(self) -> dict:
        items = list(self._items.values())
        return {"total": len(items),
                "riesgos": len([m for m in items if m["iniciativa"].get("tipo") == "riesgo"]),
                "oportunidades": len([m for m in items if m["iniciativa"].get("tipo") == "oportunidad"]),
                "objetivos": len([m for m in items if m["iniciativa"].get("tipo") == "objetivo"])}


_bandeja = None


def bandeja() -> Bandeja:
    global _bandeja
    if _bandeja is None:
        _bandeja = Bandeja()
    return _bandeja
