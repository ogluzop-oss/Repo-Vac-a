"""
Migración 0155 — Física de seguridad del artículo (autocobro). ADITIVA, idempotente, reversible.

Añade a `articulos` el peso unitario esperado y la tolerancia por artículo que usa el control
antifraude de las cajas de autocobro (Capa 1: micro-motor de seguridad local). Hasta ahora el peso
esperado usaba SIEMPRE un valor por defecto (0.300 kg) y la tolerancia era global (±60 g); con estos
campos el control puede ser real y específico por producto (p. ej. pasta 0.500 kg ±0.015 kg).

  · peso_unitario   DECIMAL(10,3)  — peso esperado por unidad (kg). NULL = usa el valor por defecto.
  · tolerancia_peso DECIMAL(10,3)  — margen aceptado (kg). NULL = usa el suelo global.

No crea motor nuevo: es master data que alimenta a `BaggingAreaController` (self_checkout_service).
"""

VERSION = "0155"
DESCRIPCION = "articulos: peso_unitario + tolerancia_peso (física de seguridad del autocobro)"
REVERSIBLE = True
REQUIERE_BACKUP = False


def aplicar(cur):
    for col, ddl in (
        ("peso_unitario", "ALTER TABLE articulos ADD COLUMN IF NOT EXISTS peso_unitario DECIMAL(10,3) DEFAULT NULL"),
        ("tolerancia_peso", "ALTER TABLE articulos ADD COLUMN IF NOT EXISTS tolerancia_peso DECIMAL(10,3) DEFAULT NULL"),
    ):
        try:
            cur.execute(ddl)
        except Exception:
            pass  # instalaciones mínimas / columna ya existente


def revertir(cur):
    for col in ("peso_unitario", "tolerancia_peso"):
        try:
            cur.execute(f"ALTER TABLE articulos DROP COLUMN IF EXISTS {col}")
        except Exception:
            pass
