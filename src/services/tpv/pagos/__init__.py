"""
Pasarelas de pago online (cobro real) — multiplataforma y enchufables.

`pasarela_actual()` devuelve la pasarela configurada para la empresa activa
(simulado / Stripe / PayPal / Redsys). Todas cumplen la interfaz `PasarelaPago` y
degradan con elegancia (sin credenciales o sin red devuelven {ok: False} sin
romper el flujo del pedido). Ver [[project_venta_online]].
"""

from src.services.tpv.pagos.factory import pasarela_actual, pasarela_para

__all__ = ["pasarela_actual", "pasarela_para"]
