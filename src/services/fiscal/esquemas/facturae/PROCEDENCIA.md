# Esquemas Facturae — procedencia y trazabilidad (C3.4)

XSD oficiales de Facturae usados para **generar y validar** la factura electrónica.

| Fichero | Versión | Origen (estado actual) |
|---|---|---|
| Facturaev3_2_2.xsd | 3.2.2 (principal) | espejo `gisce/facturae` (GitHub) |
| Facturaev3_2_1.xsd | 3.2.1 (compat) | espejo `gisce/facturae` (GitHub) |

`targetNamespace` 3.2.2: `http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml`.
El XSD **importa** `xmldsig-core-schema.xsd` (firma). Para validar **offline/.exe** se
resuelve ese import al fichero local `../xmldsig-core-schema.xsd` mediante un resolver
de lxml (no se modifica el XSD oficial).

## ⚠️ Pendiente de re-sellado oficial
Descargar los XSD desde `facturae.gob.es` (la fuente oficial bloquea el cliente TLS
actual) y comparar/re-sellar. La **política de firma** Facturae (Identifier + DigestValue)
debe confirmarse contra el PDF oficial. Estado: **ESPEJO**, validado estructuralmente.
