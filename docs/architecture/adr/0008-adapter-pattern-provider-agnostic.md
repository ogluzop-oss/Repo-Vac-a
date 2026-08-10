# ADR-0008: Adapter Pattern provider-agnostic para canales/conectores

- **Estado**: Aceptado
- **Fecha**: 2026-07-18

## Contexto

La integración con sistemas externos (marketplaces, ERP/CRM, pasarelas, transportistas, correo/firma)
no puede acoplar el dominio a ningún proveedor concreto.

## Decisión

Las integraciones usan el **Adapter Pattern**: un adaptador es un **traductor puro** entre el dominio y
la API externa, sin lógica de negocio y sin conocer el dominio.

- Contrato `ChannelAdapter` (`comercio_digital/canales/adaptador.py`) y transporte HTTP real genérico
  `RestChannelAdapter` (`rest_adapter.py`), **provider-agnostic**.
- Las credenciales/endpoint llegan por `AdapterContext`, resueltos en runtime por
  `comercio_digital.conexiones` (cifrados con el Secret Manager).
- Degradable: sin endpoint/credenciales, el adaptador no realiza llamadas.

Añadir un proveedor = una subclase que cambia mapeo/rutas; el dominio no cambia.

## Consecuencias

- (+) Independencia de proveedor; alta extensibilidad; multiempresa por diseño.
- (+) Reutilizado por los conectores Enterprise (ADR-0011).
- (−) Requiere un mapeo de traducción por proveedor.
