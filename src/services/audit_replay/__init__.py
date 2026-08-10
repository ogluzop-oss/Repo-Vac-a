"""
Audit Replay (Fase III · B6) — fachada pública (solo lectura).

    from src.services import audit_replay
    rec = audit_replay.reconstruir(id_empresa=..., com_id="COM-2026-00000001")
    print(audit_replay.a_texto(rec))
"""

from src.services.audit_replay.replay_engine import reconstruir  # noqa: F401
from src.services.audit_replay.visualizer import a_texto  # noqa: F401
from src.services.audit_replay import timeline_builder as timeline_builder  # noqa: F401

__all__ = ["reconstruir", "a_texto", "timeline_builder"]
