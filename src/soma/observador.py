"""
SomaObserver (Fase 4) — inteligencia PROACTIVA de SOMA. Proceso residente (dentro del SomaKernel) que
OBSERVA continuamente el ERP y decide cuándo merece la pena intervenir, como un responsable de
operaciones. Es transparente: el usuario nunca interactúa directamente con él.

REUTILIZA (no duplica): Event Bus (tiempo real), Scheduler (comprobaciones periódicas),
PredictionService / Gemelo Digital / Workflow / Auditoría / BI-KPIs (vía el motor de razonamiento).
El análisis corre en SEGUNDO PLANO (hilo daemon) para no afectar al rendimiento ni bloquear la UI;
los hallazgos vuelven al hilo principal por señal Qt. Nunca ejecuta acciones: solo sugiere (todo
sigue pasando por Workflow/Gobierno/Autonomía).
"""

import logging
import threading
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from src.soma import prioridad as P
from src.soma import razonamiento

logger = logging.getLogger("soma.observador")

_THROTTLE_EVENTOS = 45      # s mínimos entre análisis disparados por eventos
_LATIDO_MS = 90_000         # latido que activa el job del Scheduler (~90 s)
_COOLDOWN_AVISO = 1800      # s antes de repetir el MISMO aviso (30 min)
_ANALISIS_INICIAL_MS = 8000  # primer análisis tras arrancar (no molestar al login)


class SomaObserver(QObject):
    """Observador residente. Emite `hallazgo_listo` (hilo principal) cuando algo merece intervención."""

    hallazgo_listo = pyqtSignal(object)

    def __init__(self, kernel):
        super().__init__()
        self._kernel = kernel
        self._activo = False
        self._suscrito = False
        self._handler = None
        self._latido = None
        self._ultimo_analisis = 0.0
        self._analizando = False
        # Memoria de observación (sesión): clave → {ts, estado: 'mostrado'|'aceptado'|'ignorado'}
        self._memoria = {}
        try:
            self.hallazgo_listo.connect(self._kernel.intervenir)
        except Exception as e:
            logger.debug("conectar intervenir: %s", e)

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    def iniciar(self):
        if self._activo:
            return
        self._activo = True
        self._suscribir_bus()
        self._registrar_scheduler()
        # Latido que ACTIVA el job del Scheduler durante la sesión (reutiliza el Scheduler existente).
        self._latido = QTimer()
        self._latido.timeout.connect(self._tick_scheduler)
        self._latido.start(_LATIDO_MS)
        QTimer.singleShot(_ANALISIS_INICIAL_MS, self._disparar_analisis)
        logger.info("SomaObserver iniciado (observación proactiva en segundo plano).")

    def detener(self):
        self._activo = False
        try:
            if self._latido:
                self._latido.stop()
        except Exception:
            pass
        if self._suscrito:
            try:
                from src.services import eventos as EV
                EV.desuscribir("*", self._handler)
            except Exception:
                pass
            self._suscrito = False

    # ── Event Bus (tiempo real, sin timer) ────────────────────────────────────
    def _suscribir_bus(self):
        if self._suscrito:
            return
        try:
            from src.services import eventos as EV

            def _h(ev):
                # Cualquier evento relevante puede disparar un análisis (throttled).
                self._disparar_analisis()

            self._handler = _h
            EV.suscribir("*", _h)
            self._suscrito = True
        except Exception as e:
            logger.debug("suscribir bus: %s", e)

    # ── Scheduler (comprobaciones periódicas — reutilizado) ───────────────────
    def _registrar_scheduler(self):
        try:
            from src.services import scheduler
            scheduler.registrar("soma_observacion", lambda _emp=None: self._job_observacion())
            scheduler.registrar_job("soma_observacion", intervalo_horas=1,
                                    descripcion="Observación proactiva de SOMA")
        except Exception as e:
            logger.debug("registrar scheduler: %s", e)

    def _tick_scheduler(self):
        # Ejecuta el job de SOMA A TRAVÉS del Scheduler existente (queda registrado en su historial).
        try:
            from src.services import scheduler
            scheduler.ejecutar_job("soma_observacion")
        except Exception:
            self._disparar_analisis()   # fallback directo

    def _job_observacion(self) -> str:
        self._disparar_analisis()
        return "análisis lanzado"

    # ── Análisis en SEGUNDO PLANO (no bloquea la UI) ──────────────────────────
    def _disparar_analisis(self):
        if not self._activo or self._analizando:
            return
        ahora = time.time()
        if ahora - self._ultimo_analisis < _THROTTLE_EVENTOS:
            return
        self._ultimo_analisis = ahora
        self._analizando = True
        threading.Thread(target=self._analizar_bg, daemon=True, name="soma-observer").start()

    def _analizar_bg(self):
        try:
            # Dirección de operaciones (Fase 7): genera iniciativas (riesgos + oportunidades +
            # objetivos), las vuelca en la BANDEJA de sesión y devuelve la que merece intervención.
            # Reutiliza el razonamiento (Fase 4) por dentro; no duplica detectores. Si el paquete de
            # dirección no está, cae al razonamiento puro (compatibilidad).
            try:
                from src.soma import direccion
                _top, todas = direccion.generar_y_priorizar()
            except Exception as e:
                logger.debug("dirección no disponible, uso razonamiento: %s", e)
                todas = razonamiento.recopilar()
            mejor = self._elegir(todas)
            if mejor is not None:
                self.hallazgo_listo.emit(mejor)   # → hilo principal → kernel.intervenir
        except Exception as e:
            logger.debug("análisis observador: %s", e)
        finally:
            self._analizando = False

    # ── Filtro de interrupciones (no saturar) ─────────────────────────────────
    def _elegir(self, hallazgos):
        """Elige el hallazgo de mayor prioridad que MERECE intervención y no se haya mostrado hace poco.
        (El "no molestar" por estado de SOMA/usuario se aplica en el hilo principal, en el kernel.)"""
        candidatos = [h for h in hallazgos if P.merece_intervencion(h.get("prioridad"))]
        ahora = time.time()
        vivos = []
        for h in candidatos:
            m = self._memoria.get(h["clave"])
            if m and (ahora - m["ts"] < _COOLDOWN_AVISO):
                continue  # ya avisado hace poco → no repetir
            vivos.append(h)
        if not vivos:
            return None
        vivos.sort(key=lambda h: P.nivel(h.get("prioridad")), reverse=True)
        return vivos[0]

    # ── Memoria de observación (sesión) ───────────────────────────────────────
    def registrar_mostrado(self, hallazgo, estado="mostrado"):
        try:
            self._memoria[hallazgo["clave"]] = {"ts": time.time(), "estado": estado,
                                                "titulo": hallazgo.get("titulo")}
        except Exception:
            pass

    def marcar(self, clave, estado):
        if clave in self._memoria:
            self._memoria[clave]["estado"] = estado

    def resumen_memoria(self) -> dict:
        return {k: v.get("estado") for k, v in self._memoria.items()}
