"""
`SomaTTS._hablar_elevenlabs` — enganche del control de uso/cuota de voz (migración 0285,
`services/voz_control_uso.py`) en la MISMA degradación a Edge TTS que ya existía para cualquier
otro fallo de la API de ElevenLabs (red, clave inválida). Cero mecanismo de error nuevo: un límite
mensual de caracteres agotado (`LimiteUsoVozExcedido`) debe caer en el mismo `except` que un fallo
de red — este test lo comprueba sin red real (mockea `requests.post`/`verificar_acceso_voz`/
`_hablar_edge`), y sin BD (marca `unit`: no depende de MariaDB).
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from src.services.voz_control_uso import LimiteUsoVozExcedido
from src.utils.soma_tts import SomaTTS

pytestmark = pytest.mark.unit


def _instancia_desnuda():
    """Instancia de `SomaTTS` SIN lanzar el hilo de fondo real (que intentaría inicializar
    pygame/edge-tts/ElevenLabs) — solo los atributos que `_hablar_elevenlabs` toca."""
    tts = SomaTTS.__new__(SomaTTS)
    tts._stop_flag = threading.Event()
    tts._mixer = MagicMock()
    tts._mixer.music.get_busy.return_value = False
    return tts


def test_cuota_de_voz_agotada_degrada_a_edge_tts_sin_excepcion_visible():
    """El caso central del plan: `verificar_acceso_voz` lanza `LimiteUsoVozExcedido` ANTES de la
    llamada HTTP real → debe caer en el mismo fallback a Edge TTS, sin que la excepción escape."""
    tts = _instancia_desnuda()
    with patch("src.services.ia_control_uso.resolver_tenant_actual", return_value=("emp-1", 7)), \
         patch("src.services.voz_control_uso.verificar_acceso_voz",
               side_effect=LimiteUsoVozExcedido("límite mensual de voz agotado")), \
         patch("src.utils.soma_tts.SomaTTS._hablar_edge") as hablar_edge, \
         patch("requests.post") as http_post:
        tts._hablar_elevenlabs("Hola, esto es una prueba de cuota agotada.")

    # Nunca debió llegar a golpear la API real de ElevenLabs: la cuota se verifica ANTES.
    http_post.assert_not_called()
    hablar_edge.assert_called_once()
    assert hablar_edge.call_args[0][0] == "Hola, esto es una prueba de cuota agotada."


def test_fallo_de_red_elevenlabs_tambien_degrada_a_edge_tts():
    """Mismo fallback para un fallo "de siempre" (red/clave), confirmando que el enganche nuevo no
    sustituyó ni rompió el mecanismo de degradación ya existente."""
    tts = _instancia_desnuda()
    with patch("src.services.ia_control_uso.resolver_tenant_actual", return_value=(None, None)), \
         patch("requests.post", side_effect=OSError("timeout de red")), \
         patch("src.utils.soma_tts.SomaTTS._hablar_edge") as hablar_edge:
        tts._hablar_elevenlabs("Otra prueba, esta vez de fallo de red.")

    hablar_edge.assert_called_once()


def test_tenant_no_resoluble_omite_control_de_cuota_sin_romper_la_sintesis():
    """Sin sesión de escritorio activa resoluble (`resolver_tenant_actual` → (None, None)), no hay
    `id_empresa` contra el que verificar cuota ni registrar uso — debe degradar con normalidad
    (best-effort), nunca lanzar."""
    tts = _instancia_desnuda()
    with patch("src.services.ia_control_uso.resolver_tenant_actual", return_value=(None, None)), \
         patch("requests.post", side_effect=OSError("sin red")), \
         patch("src.utils.soma_tts.SomaTTS._hablar_edge") as hablar_edge:
        tts._hablar_elevenlabs("Texto sin tenant resoluble.")

    hablar_edge.assert_called_once()


def test_sintesis_exitosa_registra_el_uso_real_con_la_longitud_enviada():
    """Tras una síntesis real CON ÉXITO, se registra el uso con `len(texto)` del texto REALMENTE
    enviado (la base de cobro real de ElevenLabs), vía `registrar_uso_voz`."""
    tts = _instancia_desnuda()
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.content = b"audio-fake-mp3-bytes"
    texto = "Texto real enviado a ElevenLabs para síntesis."

    with patch("src.services.ia_control_uso.resolver_tenant_actual", return_value=("emp-1", 7)), \
         patch("src.services.voz_control_uso.verificar_acceso_voz", return_value=None), \
         patch("requests.post", return_value=resp), \
         patch("src.services.voz_control_uso.registrar_uso_voz") as registrar:
        tts._hablar_elevenlabs(texto)

    registrar.assert_called_once()
    args = registrar.call_args[0]
    assert args[0] == "emp-1"
    assert args[1] == 7
    assert args[3] == len(texto)
