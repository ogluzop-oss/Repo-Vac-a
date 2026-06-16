# Esquemas y WSDL Verifactu — procedencia y trazabilidad

Artefactos usados por el adaptador Verifactu (C3.3.1.1) para **generar y validar**
los registros conforme a la especificación de AEAT.

## Origen (estado actual)

Obtenidos del **espejo público** `hectorsipe/aeat-verifactu` (GitHub), rama `main`:

| Fichero | Bytes aprox. | Notas |
|---|---|---|
| SuministroLR.xsd | 1.6 KB | raíz `RegFactuSistemaFacturacion`, `Cabecera`, `RegistroFactura` |
| SuministroInformacion.xsd | 49 KB | `RegistroAlta`/`RegistroAnulacion`, tipos, enums |
| RespuestaSuministro.xsd | 6.3 KB | `EstadoEnvio`, `RespuestaLinea`, `CSV`, `TiempoEsperaEnvio` |
| ConsultaLR.xsd / RespuestaConsultaLR.xsd | — | consulta (no usado aún) |
| EventosSIF.xsd | 31 KB | registros de evento (fuera de alcance) |
| xmldsig-core-schema.xsd | 10 KB | `Signature` (opcional en VERI\*FACTU) |
| SistemaFacturacion.wsdl | 8.8 KB | operación `RegFactuSistemaFacturacion`, endpoints |

Las cabeceras de los XSD indican edición con **XMLSpy por la AEAT**, lo que sugiere
que el contenido es de **autoría oficial**. Aun así, **se tratan como ESPEJO** hasta
descargar y comparar con el **ZIP oficial** de AEAT.

## ⚠️ Pendiente de re-sellado oficial

Cuando se disponga del ZIP oficial de AEAT (XSD/WSDL versionados) y los PDF de
*huella* (v0.1.2) y *QR* (v0.5.0), se hará una validación final y se actualizará
esta tabla marcando cada artefacto como **verificado contra oficial**. La prueba
**live contra preproducción** requiere certificado y queda para C3.5.
