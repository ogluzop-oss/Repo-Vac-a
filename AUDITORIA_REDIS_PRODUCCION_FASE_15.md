# AUDITORÍA REDIS PRODUCCIÓN — FASE 15

Fecha 2026-07-27. **BLOQUEADO: no hay ElastiCache/Redis ni `redis` instalado.**

## Software (verificado)

🟢 `RedisDistribution` (perezoso) con `INSTANCE_ID` + `sellar/es_eco/limpiar_sello` → sin self-echo; anti-loop
(`_on_event(_remoto=True)` no reenvía); aislamiento por tenant. `InProcessBroker` prueba de forma determinista
la entrega exactamente-una-vez multi-instancia.

## Validación en AWS (Fase 15.6)

🟣 **BLOQUEADA**. No ejecutado sobre Redis real: A publica → B recibe una vez / A sin self-echo; ausencia de
loops; SSE tras ALB/CloudFront; reconexión ante caída de Redis (🟡 pendiente de implementar antes de escalar).

## Resume

Provisionar ElastiCache Redis en subred privada; instalar `redis`. Variable: `REALTIME_BROKER_URL`. Cablear
`RedisDistribution` + `set_distribucion`. Completar reconexión/backoff. Validar exactamente-una-entrega y
aislamiento tenant sobre Redis real. Estado: 🟢 software (single-instance) / 🟣 multi-instancia externa.
