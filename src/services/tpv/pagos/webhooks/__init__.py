"""
Webhooks de pago (Fase 3) — confirmación automática del cobro.

`procesar_webhook(proveedor, headers, body, id_empresa, ip)` valida la firma,
evita duplicados/replay, localiza el pedido, actualiza su estado y registra
auditoría. Los verificadores por proveedor (Stripe/PayPal/Redsys) se descubren
automáticamente desde el registro: añadir uno nuevo (Bizum, Google Pay, Apple
Pay, Amazon Pay…) no requiere tocar el núcleo.
"""

from src.services.tpv.pagos.webhooks.handler import procesar_webhook
from src.services.tpv.pagos.webhooks.registry import (verificador_de,
                                                      verificadores_registrados)

__all__ = ["procesar_webhook", "verificador_de", "verificadores_registrados"]
