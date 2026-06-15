"""Backend HTTP (server-side) de Smart Manager AI.

Capa fina que expone endpoints (p. ej. webhooks de pago) reutilizando los
servicios del núcleo. Pensada para ejecutarse en un servidor; la app de
escritorio NO la lanza en modo empaquetado. Toda la lógica vive en los servicios
y es testeable sin levantar el servidor.
"""
