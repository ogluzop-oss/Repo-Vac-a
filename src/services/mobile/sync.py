"""
Mobile · Sync (Fase V · Bloque 1). Sincronización OFFLINE-FIRST del dispositivo: outbox de
operaciones pendientes, sincronización diferida contra la REST API y resolución de conflictos. Es
el contrato en el dispositivo (SQLite local en la app nativa); aquí se modela la lógica, verificable
y reutilizable, siguiendo el patrón offline del bloque Resiliencia (idempotencia + versión).
"""

from __future__ import annotations

import time
import uuid

ESTRATEGIAS = ("ultimo_gana", "servidor_gana", "cliente_gana", "manual")


class Outbox:
    """Cola de operaciones creadas offline, pendientes de sincronizar (idempotentes por `idem`)."""

    def __init__(self):
        self._items = []

    def encolar(self, entidad, operacion, datos, *, idem=None):
        item = {"id": uuid.uuid4().hex, "entidad": entidad, "operacion": operacion,
                "datos": datos, "idem": idem or uuid.uuid4().hex, "ts": time.time(),
                "estado": "pendiente"}
        self._items.append(item)
        return item["id"]

    def pendientes(self):
        return [i for i in self._items if i["estado"] == "pendiente"]

    def marcar(self, item_id, estado):
        for i in self._items:
            if i["id"] == item_id:
                i["estado"] = estado
                return True
        return False

    def sincronizar(self, cliente):
        """Envía las pendientes por la REST API (idempotencia por cabecera). Devuelve resumen."""
        ok = fallo = 0
        for i in self.pendientes():
            try:
                r = cliente.solicitar("POST", f"/api/v1/{i['entidad']}",
                                      cuerpo={**i["datos"], "_idem": i["idem"]})
                if isinstance(r, dict) and (r.get("status", 200) < 400 or r.get("preparada")):
                    self.marcar(i["id"], "sincronizado"); ok += 1
                else:
                    fallo += 1
            except Exception:
                fallo += 1
        return {"sincronizados": ok, "fallidos": fallo, "restantes": len(self.pendientes())}


def resolver_conflicto(local: dict, remoto: dict, estrategia="ultimo_gana") -> dict:
    """Resuelve un conflicto entre la versión local y la remota según la estrategia."""
    if estrategia == "servidor_gana":
        return remoto
    if estrategia == "cliente_gana":
        return local
    if estrategia == "manual":
        return {"_conflicto": True, "local": local, "remoto": remoto}
    # ultimo_gana: mayor versión/timestamp.
    vl, vr = local.get("version", 0), remoto.get("version", 0)
    if vl != vr:
        return local if vl > vr else remoto
    return local if local.get("ts", 0) >= remoto.get("ts", 0) else remoto


__all__ = ["ESTRATEGIAS", "Outbox", "resolver_conflicto"]
