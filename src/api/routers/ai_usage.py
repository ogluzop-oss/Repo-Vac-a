"""
Router /ai — consulta de uso/coste de IA (Anthropic) y cambio de modalidad de plan por empresa
(Fase C del control de uso de IA — ver `services/ia_control_uso.py` Fase A y
`services/saas/ia_plan.py`). Mismo aislamiento por tenant que el resto de la API: `id_empresa`
sale SIEMPRE del contexto autenticado (JWT/API key), nunca del cuerpo/query (ver `api/security.py`).

`PATCH /ai/plan` exige el MISMO guard de step-up MFA (`requiere_step_up`) que el botón equivalente
del escritorio (`gui/saas_admin.py::_cambiar_modo_ia`, acción `"ai.plan.cambiar"`) — la API no puede
usarse para saltarse la barra de seguridad que ya exige la GUI para esta misma acción.
"""

from src.api.security import requiere_auth, requiere_step_up
from src.services.saas import ia_plan as IA

_PLANES_VALIDOS = ("LIMITED", "PAY_AS_YOU_GO")


def registrar(bp):
    @bp.get("/ai/usage")
    @requiere_auth("ai.usage.ver")
    def ai_usage():
        from flask import g, jsonify
        return jsonify(IA.resumen_uso_ia(g.ctx["id_empresa"]))

    @bp.patch("/ai/plan")
    @requiere_step_up(accion="ai.plan.cambiar", permiso="ai.plan.cambiar")
    def ai_plan_cambiar():
        from flask import g, jsonify, request
        body = request.get_json(silent=True) or {}
        nuevo_plan = str(body.get("plan_type") or "").strip().upper()
        if nuevo_plan not in _PLANES_VALIDOS:
            return jsonify({"error": "plan_type inválido", "validos": list(_PLANES_VALIDOS)}), 400
        try:
            resultado = IA.cambiar_plan_ia(g.ctx["id_empresa"], nuevo_plan)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(resultado)
