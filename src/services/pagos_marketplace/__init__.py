"""
Pagos del Marketplace B2B (Lonja) — capa de orquestación sobre el PSP regulado (Stripe Connect).

Modelo TOKENIZADO (F0): Smart Manager NO custodia fondos ni almacena IBAN completo. Guarda el token opaco
de la cuenta conectada del PSP + metadatos (banco, últimos 4, divisa, estado KYB). La retención (escrow),
el split de comisión y los payouts los ejecuta el PSP; Smart Manager solo orquesta y concilia.

Reutiliza infraestructura existente (N7, sin motores paralelos):
- Abstracción/adaptadores de pasarela: `services.tpv.pagos` (registry + config cifrada `pasarela_config`).
- Motor de webhooks con firma + idempotencia: `services.tpv.pagos.webhooks`.
- Mercado atómico e idempotente: `services.lonja` (`lonja_transacciones`).
- Libro contable de partida doble: `services.contabilidad`.
- Ledger de comisiones del servicio: `services.compras.cobro_servicio` (`servicio_cobros`).
"""
