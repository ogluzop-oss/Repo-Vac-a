"""
PCD · Fulfillment · Evaluadores de sourcing (CD-005 · Fase 4). Contrato **Strategy → Evaluator → Plan**:
múltiples evaluadores pluggables (Equilibrado, Coste, Rapidez, IA, futuros) que puntúan (SCORE) cada
alternativa a partir del mapa de disponibilidad. Fulfillment NO contiene algoritmos rígidos: elige el
evaluador por estrategia. Determinista. La IA es un evaluador degradable (provider-agnostic, I9).

Cada evaluador: `(disponibilidad, contexto) -> [alternativa]`, alternativa = {bucket, ubicacion,
disponible, eta_dias, coste, score}. Score MAYOR = mejor. La cobertura domina (un origen que cubre
la solicitud siempre supera a uno que no).
"""

from __future__ import annotations

# Coste heurístico por bucket (determinista; se sustituirá por logística real en fases futuras).
_COSTE_BUCKET = {"tienda_activa": 0.0, "otras_tiendas": 2.0, "central": 1.0, "bajo_pedido": 5.0,
                 "digital": 0.0}
# Pesos por estrategia (cobertura alta → domina; el resto desempata entre orígenes que cubren).
PESOS = {
    "equilibrado": {"cobertura": 10.0, "eta": 0.3, "coste": 0.3, "prioridad": 2.0},
    "coste":       {"cobertura": 10.0, "eta": 0.05, "coste": 2.0, "prioridad": 1.0},
    "rapidez":     {"cobertura": 10.0, "eta": 2.0, "coste": 0.05, "prioridad": 1.0},
    "ia":          {"cobertura": 10.0, "eta": 0.3, "coste": 0.3, "prioridad": 2.0},
}

_EVALUADORES = {}


def registrar(nombre, fn):
    """Registra un evaluador de sourcing (extensible sin tocar Fulfillment)."""
    _EVALUADORES[nombre] = fn


def evaluador(estrategia):
    return _EVALUADORES.get(estrategia) or _EVALUADORES.get("equilibrado")


def estrategias():
    return sorted(_EVALUADORES)


def pesos(estrategia):
    return dict(PESOS.get(estrategia, PESOS["equilibrado"]))


def _coste(bucket):
    return _COSTE_BUCKET.get(bucket, 3.0)


def _puntuar(disponibilidad, pesos_, prioridad):
    cant = int(disponibilidad.get("cantidad_solicitada", 1) or 1)
    alts = []
    for b in disponibilidad.get("buckets", []):
        disp = int(b.get("disponible", 0) or 0)
        eta = float(b.get("eta_dias", 0) or 0)
        coste = _coste(b.get("bucket"))
        cobertura = (min(disp, cant) / cant) if cant else (1.0 if disp > 0 else 0.0)
        # Prioridad empresarial: "vaciar:<bucket>" → bonifica ese origen.
        boost = pesos_.get("prioridad", 0.0) if (prioridad and
                str(prioridad).split(":")[-1] == b.get("bucket")) else 0.0
        score = (pesos_.get("cobertura", 1.0) * cobertura
                 - pesos_.get("eta", 0.0) * eta
                 - pesos_.get("coste", 0.0) * coste
                 + boost)
        alts.append({"bucket": b.get("bucket"), "ubicacion": b.get("ubicacion"),
                     "id_tienda": b.get("id_tienda"), "disponible": disp, "eta_dias": eta,
                     "coste": coste, "score": round(score, 4)})
    # Orden determinista: score desc; desempate por eta asc y bucket (estable).
    alts.sort(key=lambda a: (-a["score"], a["eta_dias"], a["bucket"] or ""))
    return alts


def _hacer(estrategia):
    def _fn(disponibilidad, contexto=None):
        return _puntuar(disponibilidad, PESOS[estrategia], (contexto or {}).get("prioridad"))
    return _fn


def _eval_ia(disponibilidad, contexto=None):
    """Evaluador IA — PREPARADO y degradable (I9, provider-agnostic). Usa la capacidad de IA si
    ofrece scoring; si no, cae al evaluador equilibrado. Nunca acopla a un proveedor concreto."""
    try:
        from src.platform import capabilities as cap
        ia = cap.ia()
        if ia is not None and hasattr(ia, "puntuar_sourcing"):
            return ia.puntuar_sourcing(disponibilidad, contexto)
    except Exception:
        pass
    return _hacer("equilibrado")(disponibilidad, contexto)


registrar("equilibrado", _hacer("equilibrado"))
registrar("coste", _hacer("coste"))
registrar("rapidez", _hacer("rapidez"))
registrar("ia", _eval_ia)


__all__ = ["PESOS", "registrar", "evaluador", "estrategias", "pesos"]
