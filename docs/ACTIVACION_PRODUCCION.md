# Activación de integraciones de producción (R2 · R3 · R4)

Estas tres integraciones aportan su valor completo solo con **credenciales/infra externas de pago**. Su
**motor ya está construido en el repo y es degradable** a modo `simulado`: la base está lista y solo hay
que **encenderla** cuando se disponga de las credenciales. Nada aquí se simula como "activado" si no lo
está — el estado real se consulta con:

```python
from src.services.integraciones import activacion
activacion.resumen()          # {total, en_produccion:[...], preparadas:[...], detalle:[...]}
activacion.estado_activacion()  # por integración: modo 'live'|'simulado' + qué falta
```

> Honestidad: `modo='simulado'` significa "motor operativo en modo degradable, base preparada, sin
> credenciales reales". `modo='live'` significa que el material de producción está presente. La aceptación
> real de la AEAT la fija el worker con el acuse oficial (nunca se inventa `enviado/aceptado`).

## R2 · Pasarela de pago (Stripe / PayPal / Redsys)

- **Motor**: [`src/services/comercio_digital/pagos`](../src/services/comercio_digital/pagos/__init__.py)
  (provider-agnostic; `cobrar_express` = cobro en 1 clic; webhooks HMAC).
- **Para activar**:
  1. Alta en la pasarela (cuenta de comercio).
  2. Guardar las **claves de API de producción** como conexión cifrada (`comercio_digital.conexiones.registrar`).
  3. Configurar el **webhook firmado** apuntando al endpoint de pagos.
- Sin credenciales → `cobrar_express` opera en `simulado` (marca `simulado=True`, no cobra de verdad). Con
  pasarela real NO auto-confirma: deja el pago **pendiente** hasta el webhook firmado.

## R3 · Conexión bancaria PSD2 (open banking)

- **Motor**: [`src/services/banca_online`](../src/services/banca_online/) (gateway + `psd2_generico` + sync
  → conciliación).
- **Para activar**:
  1. Contrato con un **agregador PSD2 (TPP)**.
  2. Guardar las **credenciales de producción** cifradas (`banca_online.config.guardar_conexion`).
  3. Consentimiento de cuentas y poner `modo_simulado=False`.
- Sin credenciales → gateway en `modo_simulado`.

## R4 · Verifactu / factura-e (AEAT)

- **Motor**: [`src/services/fiscal`](../src/services/fiscal/) (SOAP real a AEAT + mTLS + certificados PKCS#12;
  `worker.procesar_cola` con máquina de estados).
- **Para activar**:
  1. Importar y **activar el certificado PKCS#12 de producción** (`fiscal.certificados.importar/activar`).
  2. **Alta del obligado tributario** en la AEAT.
  3. mTLS operativo contra los endpoints oficiales.
- Sin certificado de producción → fallback `simulado`; **la transmisión nunca se acepta simulada** (invariante).

## R6 · Volumen masivo (relacionado, coste de despliegue)

El despliegue cloud (para "miles de tx/min") tiene coste y queda fuera. La parte **sin coste** ya está: el
arnés local de **throughput** ([`tests/load`](../tests/load/harness.py), `medir_throughput` → tx/min) mide
capacidad in-process de forma reproducible. Ejecutar:

```bash
QT_QPA_PLATFORM=offscreen DB_NAME=smart_manager_test python tests/load/run_load.py 300
```
