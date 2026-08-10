"""
Distribución de eventos entre instancias (Fase 10) — capa de TRANSPORTE, NO un segundo Event Bus. El Event Bus
de dominio (`services.eventos.bus`) y el hub de tiempo real (`realtime`) siguen siendo la única lógica de
eventos. Un adaptador de distribución sólo PROPAGA el evento serializado a otras réplicas y ENTREGA los
eventos remotos al hub local (`realtime._on_event(ev, _remoto=True)`), preservando el aislamiento por tenant
(el `id_empresa` viaja en el evento y el reparto lo filtra igual que en single-instance).

Backends:
  • LocalDistribution   — por defecto; single-instance (no propaga). Comportamiento actual, sin cambios.
  • InProcessDistribution — determinista, para TESTS multi-instancia (conecta hubs en el mismo proceso).
  • RedisDistribution   — PREPARADO, degradable (redis perezoso). NUNCA operativo sin Redis real.
"""

import json
import logging
import os
import uuid

logger = logging.getLogger("eventbus.distribucion")

# Identidad ÚNICA de esta instancia (proceso). Permite descartar el ECO del propio publicador en un broker
# Pub/Sub (que entrega el mensaje también al emisor). Configurable para tests/despliegue.
INSTANCE_ID = os.getenv("INSTANCE_ID") or ("inst_" + uuid.uuid4().hex[:12])
_CAMPO_ORIGEN = "_source_instance_id"


def sellar(ev: dict, instance_id) -> dict:
    """Devuelve una COPIA del evento con el sello de instancia de origen (para el transporte)."""
    env = dict(ev)
    env[_CAMPO_ORIGEN] = instance_id
    return env


def es_eco(ev: dict, instance_id) -> bool:
    """True si el evento proviene de la MISMA instancia (eco a descartar)."""
    return ev.get(_CAMPO_ORIGEN) == instance_id


def limpiar_sello(ev: dict) -> dict:
    ev.pop(_CAMPO_ORIGEN, None)
    return ev


class InProcessBroker:
    """Broker DETERMINISTA en memoria que modela Pub/Sub para tests multi-instancia (sin red ni mocks de
    infra). Cada instancia se conecta con su `instance_id` + su entregador (`realtime._on_event` remoto). Al
    publicar, entrega a TODAS las instancias suscritas EXCEPTO a la de origen (evita el self-echo, exactamente
    como debe hacerlo el filtro por `instance_id` en Redis)."""

    def __init__(self):
        self._subs = []       # (instance_id, entregar)

    def conectar(self, instance_id, entregar):
        self._subs.append((instance_id, entregar))

    def publicar(self, ev: dict, *, origen) -> int:
        env = sellar(ev, origen)
        crudo = json.dumps(env, default=str)         # cruce de proceso simulado (JSON)
        entregados = 0
        for iid, entregar in self._subs:
            recibido = json.loads(crudo)
            if es_eco(recibido, iid):
                continue                              # descarta el eco del propio origen
            entregar(limpiar_sello(recibido))
            entregados += 1
        return entregados


class Distribucion:
    nombre = "base"

    def publicar(self, ev: dict) -> None:
        raise NotImplementedError

    def iniciar(self) -> None:
        pass

    def detener(self) -> None:
        pass


class LocalDistribution(Distribucion):
    """Single-instance: no propaga. Es el estado por defecto (equivale a no tener distribución)."""
    nombre = "local"

    def publicar(self, ev: dict) -> None:
        return


class InProcessDistribution(Distribucion):
    """Adaptador DETERMINISTA para tests: entrega el evento a una lista de 'entregadores' que representan
    otras instancias (cada uno = `realtime._on_event` de otra instancia). No usa red ni mocks de infra;
    prueba la LÓGICA de propagación + aislamiento por tenant."""
    nombre = "inprocess"

    def __init__(self):
        self._peers = []      # callables entregar(ev)

    def conectar(self, entregar_remoto):
        self._peers.append(entregar_remoto)

    def publicar(self, ev: dict) -> None:
        # Serializa/deserializa como haría un broker real (JSON) para simular el cruce de proceso.
        crudo = json.dumps(ev, default=str)
        for entregar in self._peers:
            try:
                entregar(json.loads(crudo))
            except Exception as e:
                logger.debug("peer entrega: %s", e)


class RedisDistribution(Distribucion):
    """PREPARADO — degradable. Usa `redis` de forma perezosa; si no está instalado o no hay servidor, la
    construcción falla explícitamente (no se simula operativo). Publica en un canal Pub/Sub y, en un hilo,
    entrega los mensajes remotos al hub local. El aislamiento por tenant es el del hub (no cambia)."""
    nombre = "redis"

    def __init__(self, url=None, canal="smartmanager.eventos", *, entregar_remoto=None, instance_id=None):
        try:
            import redis  # noqa: F401
        except Exception as e:
            raise RuntimeError(f"redis no instalado: distribución PREPARADA, no operativa ({e})")
        import redis
        self._url = url or os.getenv("REALTIME_BROKER_URL")
        if not self._url:
            raise RuntimeError("REALTIME_BROKER_URL no configurado")
        self._canal = canal
        self._cli = redis.Redis.from_url(self._url)
        self._entregar = entregar_remoto
        self._instance_id = instance_id or INSTANCE_ID
        self._sub = None
        self._hilo = None

    def publicar(self, ev: dict) -> None:
        # Sella el origen para que el propio publicador pueda descartar su eco (Pub/Sub reparte a TODOS,
        # incluido el emisor). NO muta el evento original (se envía una copia con el sello).
        self._cli.publish(self._canal, json.dumps(sellar(ev, self._instance_id), default=str))

    def _entregar_si_remoto(self, ev: dict) -> bool:
        """Entrega el evento SÓLO si proviene de OTRA instancia. Devuelve True si se entregó."""
        if es_eco(ev, self._instance_id):
            return False                                     # ECO propio → descartar (evita doble entrega)
        if self._entregar:
            self._entregar(limpiar_sello(ev))                # → realtime._on_event(ev, _remoto=True)
        return True

    def iniciar(self) -> None:
        import threading
        self._sub = self._cli.pubsub()
        self._sub.subscribe(self._canal)

        def _run():
            for msg in self._sub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    self._entregar_si_remoto(json.loads(msg["data"]))
                except Exception as e:
                    logger.debug("redis entrega: %s", e)

        self._hilo = threading.Thread(target=_run, daemon=True, name="RedisDistribution")
        self._hilo.start()


def redis_disponible() -> bool:
    try:
        import redis  # noqa: F401
        return True
    except Exception:
        return False
