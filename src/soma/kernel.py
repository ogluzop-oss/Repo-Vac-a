"""
SomaKernel (Fase 1 — núcleo arquitectónico). El CEREBRO residente de SOMA: un ÚNICO proceso vivo
durante toda la sesión del ERP. Nace tras el login, permanece activo y solo se destruye al cerrar
Smart Manager AI. Responsable de: ciclo de vida, estado, contexto, memoria, coordinación,
activación y comunicación entre componentes.

REUTILIZA (no duplica): SomaWorker/SomaTTS (voz), CopilotService (cerebro conversacional),
AgentManager (Especialistas IA), Event Bus + Event Registry (observación/contexto), Scheduler
(base de proactividad futura). Separación estricta lógica/GUI: aquí NO hay Qt de presentación; la UI
(overlay/personaje/conversación) se conectará en fases posteriores a través del `EspacioNulo`.

En esta fase NO hay experiencia conversacional ni UI: solo infraestructura residente.
"""

import logging
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from src.soma import estado as E
from src.soma.contexto import ScreenContext
from src.soma.espacio import EspacioNulo
from src.soma.memoria import MemoriaConversacional
from src.soma.voz import AdaptadorVoz

logger = logging.getLogger("soma.kernel")


class _PuenteRespuesta(QObject):
    """Puente Qt para traer la respuesta del cerebro (calculada en un hilo) al HILO PRINCIPAL de
    forma segura (la UI/TTS solo pueden tocarse desde el hilo principal)."""
    lista = pyqtSignal(object, float, str)   # (respuesta, t0, texto_original)


class SomaKernel:
    """Núcleo residente (singleton — usar `soma.kernel()`)."""

    def __init__(self):
        self._iniciado = False
        self._app = None
        # Componentes propios del núcleo
        self.maquina = E.MaquinaEstados(E.DORMIDO)
        self.contexto = ScreenContext()
        self.memoria = MemoriaConversacional()
        self.voz = AdaptadorVoz()
        self._espacio = EspacioNulo()      # UI real se conecta en fases posteriores
        self._navegador = None             # adaptador de navegación del ERP (lo aporta main.py)
        # Referencias a sistemas REUTILIZADOS (perezosas; se resuelven bajo demanda)
        self._suscrito_bus = False
        self._handler_bus = None
        # Puente para el cerebro asíncrono (respuesta del hilo → hilo principal)
        self._puente = _PuenteRespuesta()
        self._puente.lista.connect(self._on_respuesta)
        # Observador proactivo (Fase 4) — residente; se crea al iniciar
        self._observador = None
        self._ultima_ocultacion = 0.0
        self._ultima_intervencion = 0.0
        self._ultimo_hallazgo = None
        self._propuestas = []            # cola de propuestas proactivas pendientes (badge)
        # Fase 5: operativa (memoria de trabajo, tareas largas, colaboración)
        from src.soma.memoria_trabajo import MemoriaTrabajo
        from src.soma.tareas import GestorTareas
        self.trabajo = MemoriaTrabajo()
        self.tareas = GestorTareas()
        self._esperando = None    # estado de diálogo colaborativo (p.ej. confirmación de un plan)
        # Fase 6: Mission Engine (Director de Orquesta)
        self._mission = None
        self._mission_conectado = False

    # ── Ciclo de vida ─────────────────────────────────────────────────────────
    def iniciar(self, app=None, *, worker=None, tts_getter=None) -> bool:
        """Arranque idempotente tras el login. Toma referencias a los sistemas existentes; NO crea
        hilos/motores paralelos. Devuelve True si el kernel queda vivo."""
        if self._iniciado:
            logger.debug("SomaKernel ya iniciado (singleton); se ignora reinicio.")
            self._reenlazar(app, worker, tts_getter)
            return True
        self._app = app
        self.contexto.enlazar_app(app)
        # Voz: referencia VIVA a worker/tts existentes de la app (se crean tras el arranque del
        # kernel; por eso se usan getters, no valores fijos). Nunca se duplican.
        worker_getter = (lambda: getattr(app, "_soma_worker", None)) if app is not None else None
        if tts_getter is None and app is not None:
            tts_getter = lambda: getattr(app, "_soma_tts", None)   # noqa: E731
        self.voz.enlazar(worker=worker, worker_getter=worker_getter, tts_getter=tts_getter)
        # Observación de contexto vía Event Bus (pantalla activa) — aditivo, no intrusivo
        self._suscribir_bus()
        # Tareas largas: progreso/fin en el hilo principal
        try:
            self.tareas.progreso.connect(self._on_tarea_progreso)
            self.tareas.terminada.connect(self._on_tarea_terminada)
        except Exception:
            pass
        # Mission Engine (Fase 6): Director de Orquesta. Señales de misión → hilo principal.
        try:
            from src.soma import mission as _mm
            self._mission = _mm.engine()
            if not self._mission_conectado:
                self._mission.actualizada.connect(self._on_mision_actualizada)
                self._mission.mensaje.connect(self._on_mision_mensaje)
                self._mission.terminada.connect(self._on_mision_terminada)
                self._mission_conectado = True
        except Exception as e:
            logger.debug("mission engine: %s", e)
        self._iniciado = True
        self.maquina.reset()   # DORMIDO
        # Observador proactivo (Fase 4): residente, observa en segundo plano y decide cuándo intervenir.
        try:
            from src.soma.observador import SomaObserver
            if self._observador is None:
                self._observador = SomaObserver(self)
            self._observador.iniciar()
        except Exception as e:
            logger.debug("observador no iniciado: %s", e)
        logger.info("SomaKernel iniciado (residente). Especialistas IA: %s",
                    ", ".join(self._dominios_especialistas()) or "—")
        return True

    def _reenlazar(self, app, worker, tts_getter):
        if app is not None:
            self._app = app
            self.contexto.enlazar_app(app)
        if worker is not None or tts_getter is not None:
            self.voz.enlazar(worker=worker, tts_getter=tts_getter)

    def shutdown(self) -> None:
        """Destrucción ordenada al cerrar la app. NO detiene el worker/tts (los gestiona la app);
        solo suelta observadores y vuelve a DORMIDO."""
        if not self._iniciado:
            return
        try:
            if self._observador is not None:
                self._observador.detener()
        except Exception:
            pass
        self._desuscribir_bus()
        try:
            self.maquina.transicionar(E.DORMIDO, forzar=True)
        except Exception:
            pass
        self._iniciado = False
        logger.info("SomaKernel apagado.")

    def esta_vivo(self) -> bool:
        return self._iniciado

    # ── Estado ────────────────────────────────────────────────────────────────
    @property
    def estado(self) -> str:
        return self.maquina.estado

    def set_estado(self, nuevo: str, *, forzar=False) -> bool:
        return self.maquina.transicionar(nuevo, forzar=forzar)

    # ── Transiciones conversacionales (la GUI REPORTA eventos; el kernel DECIDE el estado) ──
    # Modelo de poses:
    #   activo e inactivo (no se dice nada) → ESPERANDO (feliz)
    #   el trabajador está diciendo/escribiendo → ESCUCHANDO
    #   silencio consulta→respuesta → PENSANDO ; silencio orden→ejecución → PROCESANDO
    #   respondiendo → HABLANDO (explicando) ; no puede responder/ejecutar → ERROR
    def en_espera(self):
        """Activo pero sin que se esté diciendo nada → pose feliz."""
        return self.set_estado(E.ESPERANDO, forzar=True)

    def al_escuchar(self):
        return self.set_estado(E.ESCUCHANDO, forzar=True)

    def al_pensar(self):
        return self.set_estado(E.PENSANDO, forzar=True)

    def al_procesar(self):
        return self.set_estado(E.PROCESANDO, forzar=True)

    def al_responder(self):
        return self.set_estado(E.HABLANDO, forzar=True)

    def al_confirmar(self):
        return self.set_estado(E.CONFIRMACION, forzar=True)

    def al_error(self):
        return self.set_estado(E.ERROR, forzar=True)

    # ── Acceso a sistemas reutilizados ────────────────────────────────────────
    def cerebro(self):
        """CopilotService (cerebro conversacional). Reutilizado."""
        from src.services import copilot
        return copilot.servicio()

    def especialistas(self):
        """AgentManager (sistema oficial de Especialistas IA). Reutilizado."""
        from src.soma import especialistas
        return especialistas.sistema()

    def scheduler(self):
        """Scheduler existente (base de la proactividad futura). Reutilizado."""
        from src.services import scheduler
        return scheduler

    def _dominios_especialistas(self) -> list:
        try:
            from src.soma import especialistas
            return especialistas.dominios()
        except Exception:
            return []

    # ── Espacio conversacional (UI conectable en fases posteriores) ───────────
    def set_espacio(self, espacio) -> None:
        """Registra el Espacio Conversacional real (overlay) cuando exista. Fase 1: EspacioNulo."""
        self._espacio = espacio or EspacioNulo()

    @property
    def espacio(self):
        return self._espacio

    def set_navegador(self, navegador) -> None:
        """Registra el adaptador de navegación del ERP (lo aporta `main.py`). Debe exponer
        `puede(accion)` y `ejecutar(accion, params, texto) -> {mensaje, repliega}`."""
        self._navegador = navegador

    # ── Contexto de conversación (usuario / empresa) ──────────────────────────
    def _usuario(self):
        try:
            return self.contexto.snapshot().get("usuario")
        except Exception:
            return None

    def _empresa(self):
        try:
            return self.contexto.snapshot().get("empresa")
        except Exception:
            return None

    # ── CONVERSACIÓN REAL (Fase 3) ────────────────────────────────────────────
    def procesar(self, texto, *, origen="texto"):
        """Punto de entrada ÚNICO de una consulta/orden (voz o texto). Fast-path de navegación
        (baja latencia) y, para todo lo demás, DELEGA en CopilotService (inteligencia real +
        Especialistas IA). La GUI no decide: representa el estado que fija el kernel."""
        texto = (texto or "").strip()
        if not self._iniciado or not texto:
            return
        # Interrumpe cualquier discurso en curso (el usuario puede cortar a SOMA).
        self.voz.interrumpir()
        try:
            self.memoria.recordar(self._usuario(), consulta=texto)
        except Exception:
            pass

        self.trabajo.anotar(texto)

        # 0) Explicabilidad: "¿por qué…?" (misión en curso o intervención proactiva).
        if self._es_pregunta_por_que(texto):
            if self._mission is not None and self._mission.activa() is not None:
                self._decir(self._mission.explicar(), tipo="respuesta")
                return
            if self._ultimo_hallazgo:
                self._explicar_hallazgo()
                return

        # 0b) COLABORACIÓN: si SOMA esperaba una respuesta (p.ej. confirmar un plan), la interpreta.
        if self._esperando:
            self._responder_colaboracion(texto)
            return

        # 0c) CONTROL DE MISIÓN (Fase 6): "¿cómo va?", "pausa", "continúa", "cancela".
        if self._mission is not None and self._mission.activa() is not None and self._control_mision(texto):
            return

        # 0d) CONTINUIDAD / memoria de trabajo: "continuemos donde lo dejamos".
        if self._es_retomar(texto):
            self._decir(self.trabajo.retomar(), tipo="respuesta")
            return

        # 0e) DIRECCIÓN (Fase 7): consulta de la bandeja de oportunidades/recomendaciones
        #     ("¿qué has detectado hoy?", "¿hay riesgos?", "muéstrame oportunidades", "¿qué me
        #     recomiendas?"). SOMA responde desde lo ya detectado en segundo plano. Solo informa.
        if self._es_consulta_bandeja(texto):
            self._responder_bandeja(texto)
            return

        # 1) Fast-path: navegación/acciones simples del ERP (sin ida y vuelta al cerebro).
        accion = self._accion_rapida(texto)
        if accion == "ignorar":
            return
        if self._navegador is not None and accion and self._navegador.puede(accion):
            self._ejecutar_navegacion(accion, texto)
            return

        # 2) MISIÓN (Fase 6): un OBJETIVO complejo se convierte en misión (coordina especialistas en
        #    paralelo, consolida; lo crítico espera aprobación). El usuario habla solo con SOMA.
        if self._mission is not None and self._mission.es_mision(texto):
            m = self._mission.crear(texto, usuario=self._usuario(), id_empresa=self._empresa())
            if m is not None:
                self.trabajo.actualizar(topico=f"misión: {m.objetivo}")
                self._mission.iniciar(m)
                return

        # 3) TAREAS LARGAS: trabajos que tardan → segundo plano con progreso (no bloquea).
        from src.soma import tareas as _tareas
        tarea = _tareas.detectar(texto)
        if tarea:
            codigo, handler = tarea
            self.al_procesar()
            if self.tareas.iniciar(codigo, handler, self._empresa()):
                self.trabajo.actualizar(topico=codigo.replace("_", " "))
                self._espacio_estado(f"Trabajando en ello… ({codigo.replace('_', ' ')})")
            return

        # 4) RAZONAMIENTO MULTIPASO (consultas amplias) o CopilotService (resto).
        self._consultar_cerebro(texto)

    def _accion_rapida(self, texto):
        try:
            from src.utils.soma_engine import parsear_comando
            accion, _params = parsear_comando(texto)
            return accion
        except Exception:
            return None

    def _ejecutar_navegacion(self, accion, texto):
        self.al_procesar()
        try:
            from src.utils.soma_engine import parsear_comando
            _a, params = parsear_comando(texto)
            res = self._navegador.ejecutar(accion, params, texto) or {}
        except Exception as e:
            logger.error("navegación SOMA: %s", e)
            self._error("No he podido completar esa acción.")
            return
        mensaje = res.get("mensaje") or ""
        logger.info("SOMA acción=%s → %s", accion, (mensaje or "ok")[:80])
        # Aprendizaje lento: el módulo abierto se registra como hábito (memoria persistente).
        if str(accion).startswith("nav_"):
            vid = accion[len("nav_"):]
            self.trabajo.actualizar(modulo=vid)
            try:
                from src.soma import memoria_persistente as MP
                MP.registrar_uso(self._usuario(), "modulo", vid, id_empresa=self._empresa())
            except Exception:
                pass
        if mensaje:
            self._decir(mensaje, tipo="confirmacion")
        if res.get("repliega"):
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1100, self.ocultar)
        elif not mensaje:
            self.en_espera()

    def _consultar_cerebro(self, texto):
        self.al_pensar()
        t0 = time.perf_counter()
        usuario, empresa = self._usuario(), self._empresa()

        # Aprendizaje lento: registra el dominio consultado como hábito.
        try:
            from src.soma import memoria_persistente as MP
            MP.registrar_uso(usuario, "dominio", (texto.split() or ["consulta"])[0][:40], id_empresa=empresa)
        except Exception:
            pass

        def _worker():
            # Consultas amplias → RAZONAMIENTO MULTIPASO (varias fuentes → una síntesis).
            # El resto → CopilotService (Especialistas IA). El usuario no ve el proceso interno.
            try:
                from src.soma import razonador
                rol = self.contexto.snapshot().get("rol") or "ADMINISTRADOR"
                if razonador.es_analitica(texto):
                    resp = razonador.sintetizar(texto, usuario=usuario, id_empresa=empresa, rol=rol)
                    if not resp:
                        resp = self.cerebro().preguntar(texto, usuario, empresa)
                else:
                    resp = self.cerebro().preguntar(texto, usuario, empresa)
            except Exception as e:
                resp = {"__error__": str(e)}
            try:
                self._puente.lista.emit(resp or {}, t0, texto)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True, name="soma-cerebro").start()

    def _on_respuesta(self, resp, t0, texto):
        """En HILO PRINCIPAL: aplica personalidad, muestra en el overlay (con visual+fuentes), habla."""
        ms = int((time.perf_counter() - t0) * 1000)
        if not isinstance(resp, dict) or resp.get("__error__"):
            logger.warning("SOMA cerebro error (%s ms): %s", ms, (resp or {}).get("__error__"))
            self._error("Ahora mismo no he podido resolver tu consulta.")
            return
        logger.info("SOMA consulta='%s' intent=%s fuentes=%s %sms", (texto or "")[:60],
                    resp.get("intent") or "?", resp.get("fuentes") or [], ms)
        try:
            self.memoria.recordar(self._usuario(), respuesta=resp.get("texto") or resp.get("mensaje"))
        except Exception:
            pass
        self._responder_resultado(resp)

    def _responder_resultado(self, res):
        """Respuesta unificada (cerebro/razonador/tareas/planificador): personalidad + texto + visual
        + fuentes (referencias) en el overlay + voz."""
        if not isinstance(res, dict):
            res = {"texto": str(res)}
        from src.soma.personality.personality import personalidad
        texto = personalidad().modular(res.get("texto") or res.get("mensaje") or "", tipo="respuesta",
                                       contexto=self.contexto.snapshot())
        self._decir(texto, tipo="respuesta",
                    datos={"fuentes": res.get("fuentes"), "visual": res.get("visual")})

    # ── Colaboración / continuidad / tareas (Fase 5) ──────────────────────────
    def _es_retomar(self, texto) -> bool:
        t = (texto or "").lower()
        return any(k in t for k in ("continuemos", "donde lo dejamos", "retomar", "retomamos",
                                    "seguimos", "sigamos", "continua donde", "continúa donde"))

    def _responder_colaboracion(self, texto):
        esp = self._esperando
        self._esperando = None
        t = (texto or "").lower()
        si = any(k in t for k in ("si", "sí", "vale", "adelante", "hazlo", "confirmo", "ok",
                                  "de acuerdo", "prepara", "perfecto"))
        no = any(k in t for k in ("no", "cancela", "cancelar", "déjalo", "dejalo", "mejor no"))
        if esp and esp.get("tipo") == "iniciativa":
            # Aprendizaje de decisiones (Fase 7): registra aceptación/rechazo para ajustar prioridades
            # futuras (nunca la personalidad). Si acepta, PREPARA una misión (que a su vez gobernará la
            # ejecución crítica por aprobación); SOMA no ejecuta nada por su cuenta.
            if no:
                self._decidir_iniciativa(esp, "RECHAZADA")
                self._decir("Entendido, lo dejo en la bandeja por si lo quieres retomar más adelante.",
                            tipo="respuesta")
            elif si:
                self._decidir_iniciativa(esp, "ACEPTADA")
                self._preparar_mision_iniciativa(esp)
            else:
                self._esperando = esp   # ambiguo → re-preguntar
                self._decir("¿Preparo el plan entonces? Dime sí o no.", tipo="respuesta")
        elif esp and esp.get("tipo") == "plan":
            if no:
                self._decir("De acuerdo, lo dejamos. Cuando quieras lo retomamos.", tipo="respuesta")
            elif si:
                from src.soma import planificador
                res = planificador.ejecutar_confirmado(esp["clave"], id_empresa=self._empresa())
                self._responder_resultado(res)
            else:
                self._esperando = esp   # ambiguo → re-preguntar (colaboración natural)
                self._decir("¿Lo preparo entonces? Dime sí o no.", tipo="respuesta")
        else:
            self._consultar_cerebro(texto)

    def _decidir_iniciativa(self, esp, estado):
        try:
            from src.soma.direccion import historial
            historial.decidir(esp.get("clave", ""), estado, usuario=self._usuario(),
                              id_empresa=self._empresa())
            from src.soma.direccion.bandeja import bandeja
            bandeja().marcar(esp.get("clave", ""), estado)
        except Exception as e:
            logger.debug("decidir iniciativa: %s", e)

    def _preparar_mision_iniciativa(self, esp):
        """Convierte una iniciativa aceptada en una MISIÓN (Fase 6). La misión planifica y, para lo
        crítico, exige aprobación (Autonomía/Workflow); SOMA nunca ejecuta acciones críticas."""
        mkey = esp.get("mision")
        texto = self._MISION_TEXTO.get(mkey, (esp.get("ini") or {}).get("titulo") or "")
        m = None
        if self._mission is not None and texto:
            m = self._mission.crear(texto, usuario=self._usuario(), id_empresa=self._empresa())
        if m is not None:
            self.trabajo.actualizar(topico=f"misión: {m.objetivo}")
            self._mission.iniciar(m)
        else:
            self._decir("Tomo nota. Lo dejo preparado como recomendación en la bandeja.",
                        tipo="respuesta")

    def _espacio_estado(self, texto):
        try:
            self._espacio.mostrar_respuesta(texto)
        except Exception:
            pass

    def _on_tarea_progreso(self, codigo, pct, msg):
        # Mantiene la pose PROCESANDO mientras trabaja; sin saturar de mensajes.
        if self.estado != E.PROCESANDO:
            self.al_procesar()

    def _on_tarea_terminada(self, codigo, res):
        self._responder_resultado(res if isinstance(res, dict) else {"texto": str(res)})

    # ── Mission Engine (Fase 6): SOMA como Director de Orquesta ────────────────
    def _control_mision(self, texto) -> bool:
        t = (texto or "").lower()
        if any(k in t for k in ("como va", "cómo va", "que tal va", "qué tal va", "como vas",
                                "cómo vas", "estado de la mision", "estado de la misión")):
            self._decir(self._mission.estado_natural(), tipo="respuesta")
            return True
        if "pausa" in t or "pausar" in t or "espera un momento" in t:
            self._mission.pausar()
            return True
        if any(k in t for k in ("continua", "continúa", "reanuda", "sigue con la mis")):
            self._mission.reanudar()
            return True
        if "cancela" in t or "cancelar" in t or t.strip() in ("para", "detente"):
            self._mission.cancelar()
            return True
        return False

    def _on_mision_actualizada(self, mid):
        try:
            d = self._mission.mision_dict(mid)
            if d and self._espacio.esta_visible():
                self._espacio.mostrar_workspace(d)
        except Exception:
            pass

    def _on_mision_mensaje(self, mid, texto):
        # SOMA informa del progreso de forma natural (aparece si no está visible).
        if not self._espacio.esta_visible():
            self.activar(motivo="mision")
        try:
            d = self._mission.mision_dict(mid)
            if d:
                self._espacio.mostrar_workspace(d)
        except Exception:
            pass
        self._decir(texto, tipo="respuesta")

    def _on_mision_terminada(self, mid, resultado):
        self._responder_resultado(resultado if isinstance(resultado, dict) else {"texto": str(resultado)})

    def _decir(self, texto, *, tipo="respuesta", datos=None):
        """MUESTRA el texto en el overlay (con visual/fuentes si los hay) y lo DICE por voz, fijando la
        expresión (HABLANDO/CONFIRMACION/ERROR) y manteniéndola hasta que la voz termine; luego FELIZ."""
        try:
            self._espacio.mostrar_respuesta(texto, datos=datos)
        except Exception:
            pass
        from src.soma.personality.personality import personalidad
        self.set_estado(personalidad().expresion_para(tipo), forzar=True)
        self.voz.hablar(texto, al_terminar=self.en_espera)

    def _error(self, mensaje):
        from src.soma.personality.personality import personalidad
        self._decir(personalidad().modular(mensaje, tipo="error"), tipo="error")

    def interrumpir(self):
        """El usuario corta a SOMA mientras habla: detiene la voz y queda a la escucha."""
        self.voz.interrumpir()
        if self._iniciado:
            self.al_escuchar()

    # ── DIRECCIÓN (Fase 7): bandeja de oportunidades/recomendaciones ──────────
    # Frase canónica por plantilla de misión → permite ofrecer una misión sin tocar la Fase 6.
    _MISION_TEXTO = {"mejorar_ventas": "mejorar las ventas", "reducir_costes": "reducir costes"}

    def _es_consulta_bandeja(self, texto) -> bool:
        t = (texto or "").lower()
        return any(k in t for k in (
            "que has detectado", "qué has detectado", "detectado hoy", "que me recomiendas",
            "qué me recomiendas", "recomiendas hoy", "muestrame oportunidades", "muéstrame oportunidades",
            "que oportunidades", "qué oportunidades", "hay oportunidades", "hay riesgos", "que riesgos",
            "qué riesgos", "muestrame riesgos", "muéstrame riesgos", "que objetivos", "qué objetivos",
            "que has visto", "qué has visto", "bandeja", "que novedades", "qué novedades"))

    def _responder_bandeja(self, texto):
        from src.soma.direccion import temporal
        from src.soma.direccion.bandeja import bandeja
        t = (texto or "").lower()
        tipo = ("riesgo" if "riesgo" in t else "oportunidad" if "oportunidad" in t
                else "objetivo" if "objetivo" in t else None)
        items = bandeja().listar(tipo=tipo, limite=6)
        m = temporal.momento()
        if not items:
            self._decir(f"{temporal.saludo(m)}. De momento no he detectado nada que merezca tu "
                        "atención; está todo en orden. Seguiré vigilando.", tipo="respuesta")
            return
        etiqueta = {"riesgo": "riesgos", "oportunidad": "oportunidades",
                    "objetivo": "objetivos"}.get(tipo, "cosas")
        intro = f"{temporal.matiz(m)}he estado observando y te resumo lo que he detectado"
        if tipo:
            intro = f"{temporal.matiz(m)}esto es lo que veo en cuanto a {etiqueta}"
        lineas = [f"{i+1}. {it.get('titulo')} — {it.get('mensaje','')}" for i, it in enumerate(items)]
        texto_out = intro + ":\n" + "\n".join(lineas)
        visual = {"tipo": "tabla", "columnas": ["Prioridad", "Tipo", "Título"],
                  "filas": [{"Prioridad": it.get("prioridad", "MEDIA"),
                             "Tipo": it.get("tipo", "").capitalize(),
                             "Título": it.get("titulo", "")} for it in items]}
        # Deja la primera como "última recomendación" para que "¿por qué?" la explique.
        self._ultimo_hallazgo = items[0]
        self._decir(texto_out, tipo="respuesta", datos={"visual": visual, "fuentes": ["Dirección SOMA"]})

    def _ofrecer_mision(self, ini):
        """Si la iniciativa tiene una misión asociada, ofrece prepararla (colaboración). No la lanza:
        espera la confirmación del usuario y, aun aceptada, la ejecución crítica pasa por aprobación."""
        mkey = ini.get("mision")
        if not mkey or self._mission is None:
            return ""
        self._esperando = {"tipo": "iniciativa", "clave": ini.get("clave"), "mision": mkey, "ini": ini}
        return " ¿Quieres que prepare un plan para abordarlo? Dime sí o no."

    # ── PROACTIVIDAD (Fase 4): auto-invocación del observador ─────────────────
    def intervenir(self, hallazgo):
        """Auto-invocación PROACTIVA (hilo principal). Reutiliza overlay/personaje; aplica el filtro
        'no molestar' y muestra el hallazgo de forma natural y explicable. Nunca ejecuta acciones.
        Fase 7: registra la recomendación en el historial y, si procede, ofrece preparar una misión."""
        if not self._iniciado or not isinstance(hallazgo, dict):
            return
        ahora = time.time()
        # NO invade la pantalla: si SOMA ya está activo con el usuario, no molesta.
        if self._espacio.esta_visible():
            return
        if ahora - self._ultima_ocultacion < 30:
            return   # acaba de cerrar SOMA (margen breve)
        # Dedupe por clave: no acumular la misma propuesta dos veces en el badge.
        clave = hallazgo.get("clave")
        if any(p.get("clave") == clave for p in self._propuestas):
            return
        self._ultima_intervencion = ahora
        self._ultimo_hallazgo = hallazgo
        try:
            if self._observador is not None:
                self._observador.registrar_mostrado(hallazgo, "mostrado")
        except Exception:
            pass
        # Historial de recomendaciones (qué/cuándo/por qué) — base del aprendizaje de decisiones.
        try:
            from src.soma.direccion import historial
            historial.registrar(hallazgo, estado="PROPUESTA", usuario=self._usuario(),
                                 id_empresa=self._empresa())
        except Exception:
            pass
        self._propuestas.append(hallazgo)
        logger.info("SOMA propone [%s/%s]: %s (badge=%d)", hallazgo.get("prioridad"),
                    hallazgo.get("dominio"), hallazgo.get("titulo"), len(self._propuestas))
        # Avisa con un badge (contador estilo WhatsApp) + pose 'proponiendo'; sin abrir la conversación.
        try:
            self._espacio.proponer(len(self._propuestas))
        except Exception:
            pass

    def abrir_propuestas(self):
        """El usuario pulsa el personaje con propuestas pendientes: SOMA las PRESENTA (ahora sí abre la
        conversación) y limpia el badge. Reutiliza _decir/_ofrecer_mision (solo propone, no ejecuta)."""
        if not self._iniciado:
            return
        props = list(self._propuestas)
        self._propuestas = []
        try:
            self._espacio.reset_propuestas()
        except Exception:
            pass
        if not props:
            self.activar(motivo="clic_personaje")
            return
        from src.soma import prioridad as _P
        props.sort(key=lambda h: _P.nivel(h.get("prioridad", "MEDIA")), reverse=True)
        top = props[0]
        self._ultimo_hallazgo = top
        self.activar(motivo="propuesta")
        mensaje = top.get("mensaje") or top.get("titulo") or ""
        mensaje += self._ofrecer_mision(top)   # ofrecer misión (solo propone, no ejecuta)
        if len(props) > 1:
            mensaje += f" Por cierto, tengo {len(props) - 1} propuesta(s) más para cuando quieras."
        self._decir(mensaje, tipo="respuesta")

    def observador(self):
        return self._observador

    # ── Explicabilidad de la última intervención ("¿por qué me dices esto?") ──
    def _es_pregunta_por_que(self, texto) -> bool:
        t = (texto or "").lower()
        return any(k in t for k in ("por que", "por qué", "porque me", "en que datos", "en qué datos",
                                    "que ha ocurrido", "qué ha ocurrido", "que consecuencias",
                                    "qué consecuencias", "como lo sabes", "cómo lo sabes",
                                    "explicame", "explícame", "en que te basas", "en qué te basas"))

    def _explicar_hallazgo(self):
        h = self._ultimo_hallazgo or {}
        partes = []
        if h.get("por_que"):
            partes.append(f"¿Por qué te lo digo? {h['por_que']}")
        if h.get("datos"):
            datos = ", ".join(f"{k}: {v}" for k, v in (h.get("datos") or {}).items() if k != "titulo")
            if datos:
                partes.append(f"Me baso en estos datos: {datos}.")
        if h.get("consecuencias"):
            partes.append(f"Consecuencias previstas: {h['consecuencias']}")
        # Explicabilidad total (Fase 7): "¿qué pasa si no hago nada?"
        sino = h.get("si_no_hago_nada") or h.get("consecuencias")
        if sino:
            partes.append(f"Y si no hacemos nada: {sino}")
        if h.get("acciones"):
            partes.append(f"Lo que propongo: {h['acciones']}")
        elif h.get("accion"):
            partes.append(h["accion"])
        texto = " ".join(partes) or "Te lo comento a partir de la información viva del ERP."
        self._decir(texto, tipo="respuesta")

    # ── Activación (infraestructura; sin experiencia conversacional en Fase 1) ─
    def activar(self, *, motivo=None) -> None:
        """Punto de entrada ÚNICO de invocación (wake word / clic / observador). En Fase 1 solo
        conmuta estados y avisa al espacio (EspacioNulo = no-op). La experiencia real llega después."""
        if not self._iniciado:
            return
        self.maquina.transicionar(E.APARECIENDO)
        try:
            self._espacio.mostrar(motivo=motivo)
        except Exception as e:
            logger.debug("espacio.mostrar: %s", e)
        self.maquina.transicionar(E.ESCUCHANDO)

    def ocultar(self) -> None:
        """Oculta el espacio y vuelve a reposo. El cerebro (memoria/contexto) permanece vivo."""
        if not self._iniciado:
            return
        self._ultima_ocultacion = time.time()   # el filtro de interrupciones lo tiene en cuenta
        self.maquina.transicionar(E.DESAPARECIENDO)
        try:
            self._espacio.ocultar()
        except Exception:
            pass
        self.maquina.transicionar(E.DORMIDO)

    # ── Contexto ──────────────────────────────────────────────────────────────
    def contexto_actual(self) -> dict:
        return self.contexto.snapshot()

    # ── Event Bus (observación de contexto; base de proactividad) ─────────────
    def _suscribir_bus(self):
        if self._suscrito_bus:
            return
        try:
            from src.services import eventos as EV

            def _handler(ev):
                # Fase 1: solo actualiza la pantalla activa a partir de eventos de UI. NO reacciona
                # (la proactividad es de una fase posterior).
                try:
                    if isinstance(ev, dict) and ev.get("tipo", "").startswith("UI_PANEL"):
                        payload = ev.get("payload") or {}
                        self.contexto.notificar_pantalla(payload.get("panel"),
                                                         modulo=payload.get("modulo"))
                except Exception:
                    pass

            self._handler_bus = _handler
            EV.suscribir("*", _handler)
            self._suscrito_bus = True
        except Exception as e:
            logger.debug("suscribir bus: %s", e)

    def _desuscribir_bus(self):
        if not self._suscrito_bus:
            return
        try:
            from src.services import eventos as EV
            EV.desuscribir("*", self._handler_bus)
        except Exception:
            pass
        self._suscrito_bus = False
