"""
IOC v2 · IdentityCache (Parte 1.10) — caché en proceso para la identidad, consultada intensivamente.

- Aislamiento MULTIEMPRESA estricto: la clave incluye `id_empresa`; jamás se comparten datos entre
  empresas.
- TTL configurable por entrada.
- Invalidación automática por Event Bus (se SUSCRIBE a '*' con un único handler, patrón del Gemelo):
  cualquier evento `identidad.*` de mutación invalida la caché de esa empresa.
- Se integra con Repository/Resolver/Service; los módulos nunca acceden a la caché directamente.

No crea un bus nuevo: reutiliza `services.eventos`. No accede a módulos funcionales.
"""

import logging
import threading
import time

logger = logging.getLogger("identidad.cache")

_TTL_DEFECTO = 300  # segundos


class IdentityCache:
    """Caché TTL con espacio de nombres por empresa. Segura para hilos."""

    def __init__(self, ttl_por_defecto: int = _TTL_DEFECTO):
        self._ttl = int(ttl_por_defecto)
        self._data = {}           # {(id_empresa, namespace, key): (expira_ts, valor)}
        self._lock = threading.RLock()
        self._suscrito = False
        self._hits = 0
        self._miss = 0

    # ── API principal ────────────────────────────────────────────────────────
    def _k(self, id_empresa, namespace, key):
        return (str(id_empresa), str(namespace), str(key))

    def get(self, id_empresa, namespace, key):
        k = self._k(id_empresa, namespace, key)
        with self._lock:
            item = self._data.get(k)
            if not item:
                self._miss += 1
                return None
            expira, valor = item
            if expira and time.time() > expira:
                self._data.pop(k, None)
                self._miss += 1
                return None
            self._hits += 1
            return valor

    def set(self, id_empresa, namespace, key, valor, *, ttl=None):
        k = self._k(id_empresa, namespace, key)
        exp = time.time() + int(ttl if ttl is not None else self._ttl)
        with self._lock:
            self._data[k] = (exp, valor)

    def obtener_o_calcular(self, id_empresa, namespace, key, calc, *, ttl=None):
        """Devuelve el valor cacheado o lo calcula con `calc()` y lo guarda."""
        v = self.get(id_empresa, namespace, key)
        if v is not None:
            return v
        v = calc()
        if v is not None:
            self.set(id_empresa, namespace, key, v, ttl=ttl)
        return v

    def invalidar(self, id_empresa=None, namespace=None):
        """Invalida entradas de una empresa (y opcionalmente un namespace). Sin args = todo."""
        with self._lock:
            if id_empresa is None:
                n = len(self._data)
                self._data.clear()
            else:
                claves = [k for k in self._data
                          if k[0] == str(id_empresa) and (namespace is None or k[1] == str(namespace))]
                for k in claves:
                    self._data.pop(k, None)
                n = len(claves)
        try:
            from src.services import eventos
            eventos.publicar("identidad.cache.invalidado", id_empresa=id_empresa,
                             payload={"namespace": namespace, "entradas": n})
        except Exception:
            pass
        return n

    def metricas(self) -> dict:
        with self._lock:
            total = self._hits + self._miss
            return {"entradas": len(self._data), "hits": self._hits, "miss": self._miss,
                    "ratio_acierto": round(self._hits / total, 3) if total else None,
                    "ttl_defecto": self._ttl, "suscrito_bus": self._suscrito}

    # ── Invalidación por Event Bus ───────────────────────────────────────────
    def _handler_evento(self, ev):
        """Invalida la caché de la empresa afectada ante mutaciones de identidad. Best-effort."""
        try:
            tipo = ev.get("tipo") if isinstance(ev, dict) else getattr(ev, "tipo", "")
            if not tipo or not str(tipo).startswith("identidad."):
                return
            # No re-invalidar por el propio evento de invalidación (evita bucles).
            if str(tipo) in ("identidad.cache.invalidado", "identidad.cache.actualizado",
                             "identidad.resuelta", "identidad.validada"):
                return
            emp = ev.get("id_empresa") if isinstance(ev, dict) else getattr(ev, "id_empresa", None)
            self.invalidar(emp)
        except Exception as e:
            logger.debug("_handler_evento: %s", e)

    def suscribir_bus(self) -> bool:
        """Suscribe la invalidación al Event Bus existente (idempotente)."""
        if self._suscrito:
            return True
        try:
            from src.services.eventos import bus as _bus
            _bus.suscribir("*", self._handler_evento)
            self._suscrito = True
            return True
        except Exception as e:
            logger.debug("suscribir_bus: %s", e)
            return False


# Singleton de proceso + suscripción idempotente al bus.
_CACHE = IdentityCache()
try:
    _CACHE.suscribir_bus()
except Exception:
    pass


def cache() -> IdentityCache:
    """Punto de acceso al IdentityCache (nunca instanciar desde módulos)."""
    return _CACHE
