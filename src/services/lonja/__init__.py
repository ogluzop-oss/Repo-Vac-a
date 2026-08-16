"""
Lonja B2B — mercado/subasta entre varias EMPRESAS compradoras y VENDEDORES (proveedores).

Un vendedor publica listados (precio de compra directa + puja mínima + divisa + cantidad) visibles por
todas las compradoras; una empresa compra directamente (el primero que llega se lo lleva) o puja, y se
adjudica a la mejor. Las operaciones son ATÓMICAS (bloqueo de fila, sin dobles ventas) e IDEMPOTENTES, y
generan el pedido REAL en el tenant comprador (reutiliza `db.compras`). Multidivisa con conversión propia.

Distinto del "Marketplace" de plugins (App Store) y de la "bolsa" per-tenant: la Lonja es el mercado
COMPARTIDO entre empresas. Fachada plana: `from src.services import lonja` (Fase M1: núcleo).
"""

from .divisa import convertir, set_tasa, tasa, tasas
from .vendedores import (alta_vendedor, set_divisa, obtener as obtener_vendedor, resolver_token,
                         listar as listar_vendedores, vendedor_de_proveedor)
from .listados import publicar, listar as listar_listados, obtener as obtener_listado, retirar
from .transacciones import (adjudicar, comprar_directo, mejor_puja, pujar, transacciones_de)
from .mercado import bolsa_unificada, divisa_referencia
from .jobs import cerrar_subastas_vencidas, registrar_jobs_lonja, subastas_vencidas

__all__ = [
    "convertir", "set_tasa", "tasa", "tasas",
    "alta_vendedor", "set_divisa", "obtener_vendedor", "resolver_token", "listar_vendedores",
    "vendedor_de_proveedor",
    "publicar", "listar_listados", "obtener_listado", "retirar",
    "comprar_directo", "pujar", "adjudicar", "mejor_puja", "transacciones_de",
    "bolsa_unificada", "divisa_referencia",
    "cerrar_subastas_vencidas", "subastas_vencidas", "registrar_jobs_lonja",
]
