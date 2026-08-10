# ENTERPRISE DIGITAL TWIN — Gemelo Digital Empresarial

**Paquete Enterprise 8 — Smart Manager**
Representacion VIVA del estado de toda la organizacion en tiempo real: una capa de conocimiento
construida SOBRE la base de datos, que se convierte en la unica fuente de estado que consultan la
IA, el Copiloto y los Agentes especializados.

Estado: **implementado, verificado en local, sin commitear.**
Migracion: `0094_gemelo_digital` (idempotente, reversible, aditiva).

---

## 1. Arquitectura

Fachada publica UNICA (patron `servicio()` como el resto de paquetes Enterprise). Toda consulta de
estado global pasa por aqui; IA/Copiloto/Agentes nunca acceden a decenas de modulos por su cuenta:

```python
from src.services import gemelo
gemelo.servicio().estado_empresa()
gemelo.servicio().estado_tienda("Valencia")
gemelo.servicio().dashboard()
gemelo.servicio().dependencias("factura", 5)
```

Modulos (`src/services/gemelo/`):

| Modulo | Subfase | Responsabilidad |
|---|---|---|
| `motor.py` (`DigitalTwinService`) | 8.1 | Fachada unica. Cachea el estado por dominio (TTL en proceso), lo invalida por eventos y coordina todo. |
| `fuentes.py`       | 8.16 | Capa UNICA de lectura. Reutiliza Event Bus, Sincronizacion, BI, PredictionService, Gobierno, adaptadores IA, Tesoreria. Best-effort. |
| `estado_global.py` | 8.2 | Estado vivo de empresa/tiendas/almacenes/usuarios/terminales/pedidos/facturas/incidencias/tareas/workflows/sync/automatizaciones. |
| `inventario.py`    | 8.3 | Stock, reservas, roturas, sobrestock, ubicaciones, ultima actualizacion, riesgo. |
| `comercial.py`     | 8.4 | Clientes, ventas, pedidos, facturacion, impagos, rentabilidad. |
| `rrhh.py`          | 8.5 | Empleados, contratos, ausencias, delegaciones, estado operativo. |
| `financiero.py`    | 8.6 | Tesoreria, cobros, pagos, liquidez, cuentas pendientes, riesgo. |
| `logistico.py`     | 8.7 | Proveedores, compras, recepciones, envios, sincronizacion. |
| `dependencias.py`  | 8.8 | Grafo de dependencias recorrible en ambos sentidos. |
| `eventos_twin.py`  | 8.9 | Suscripcion al Event Bus; invalidacion + alta de aristas de dependencia. |
| `consultas.py`     | 8.10 | Consultas instantaneas (empresa, tienda, procesos, recursos bloqueados, contratos, pedidos, incidencias). |
| `consistencia.py`  | 8.15 | Verificacion automatica + log + auditoria + resincronizacion + job scheduler. |
| `dashboard.py`     | 8.14 | Backend del panel de estado vivo. |
| `snapshot.py`      | — | Foto materializada del estado global (cache reconstruible). |
| `modelo.py`        | — | Estructuras ligeras + niveles de riesgo. |

---

## 2. Modelo

El Gemelo Digital **no sustituye ni duplica** la base de datos. El estado por dominio se **deriva
bajo demanda** de las fuentes existentes y se mantiene en una **cache en proceso con TTL** (30 s),
refrescada por eventos. Solo se persiste lo que NO existe en ningun otro modulo (migracion 0094):

- **`dt_dependencias`** — grafo de trazabilidad (pedido→proveedor→recepcion→stock→venta→factura→
  cobro→contabilidad). Aristas idempotentes, recorribles hacia adelante y hacia atras.
- **`dt_incoherencias`** — log de inconsistencias detectadas (idempotente por hash), para auditoria
  y resincronizacion.
- **`dt_snapshots`** — foto materializada del estado global (dashboard + linea base de consistencia).
  Cache reconstruible; nunca fuente de verdad.

Cada estado de dominio expone un contrato uniforme: `{dominio, resumen, riesgo, indicadores,
alertas, detalle}`. El riesgo (BAJO/MEDIO/ALTO) se agrega al peor de los dominios para el panel.

---

## 3. Fuentes (reutilizacion absoluta)

Ningun modulo del gemelo consulta un servicio ajeno directamente: todo pasa por `fuentes.py`, que
reutiliza:

- **Event Bus** (`eventos.metricas/buscar/suscribir`) — actualizacion por eventos.
- **Centro de Actividad / Sincronizacion** (`actividad.sincronizacion.infraestructura/panel`) —
  terminales, tiendas offline, estado de reparto.
- **PredictionService** (`prediccion.servicio().stock/clientes/riesgos`) — riesgo de rotura/
  sobrestock/impagos, sin recalcular.
- **BI** (`bi.dashboard.panel`) — KPIs.
- **Gobierno Corporativo** (`gobierno.servicio().dashboard/delegaciones_activas`, organigrama) —
  estructura organizativa y responsables.
- **Tesoreria** (`tesoreria.posicion.posicion`) — liquidez.
- **Automatizacion** (`automatizacion.panel.resumen`) — pendientes.
- **Adaptadores de IA** (`ia.adaptadores.articulos_bajo_umbral/exceso`) — inventario.
- **BD operativa** (solo lectura) — conteos agregados sobre tablas reales verificadas:
  `compras_pedidos`, `facturas_cliente`, `rrhh_contratos`, `rrhh_empleados`, `rrhh_ausencias`,
  `wf_instancias`, `tickets`, `movimientos_stock`, `vencimientos`, `ventas`, `clientes`,
  `ventas_pedidos_cliente`, `factura_envios`, `proveedores`, `usuarios`.

---

## 4. Integraciones

- **IA (8.11)** — `IAService.estado_empresa()` / `estado_dominio()` delegan EXCLUSIVAMENTE en el
  DigitalTwinService. La IA ya no consulta decenas de modulos para conocer el estado global.
- **Copiloto (8.12)** — `CopilotService` responde "¿Como esta la empresa?", "estado general",
  "¿que ocurre en la tienda de X?" usando solo el gemelo (fuente «Gemelo Digital»), antes de
  delegar en agentes/IA. Aditivo y a prueba de fallos.
- **Agentes (8.13)** — el `AgentManager` inyecta el estado vivo del dominio (`ctx['estado_twin']`)
  ANTES de invocar a cada agente; `base.Agente._twin(ctx)` lo expone. Cada especialista consulta su
  Gemelo Digital (p.ej. Agente RRHH → Digital Twin RRHH) sin cruces innecesarios entre modulos.
- **Event Bus (8.9)** — el gemelo se suscribe a `*`; cada evento relevante invalida el/los
  dominio(s) afectado(s) y registra oportunisticamente aristas de dependencia. La actualizacion
  jamas se hace por llamadas manuales entre modulos.
- **Scheduler (8.15)** — job `gemelo_consistencia` (cada 6 h) registrado de forma aditiva en
  `registrar_jobs_por_defecto`.

---

## 5. Rendimiento

- **Nunca recorre todas las tablas**: conteos agregados acotados por `id_empresa` + cache por
  dominio con TTL, invalidada solo cuando un evento cambia algo (SUBFASE 8.16).
- El grafo de dependencias usa indices sobre `(origen)` y `(destino)`; el recorrido es BFS acotado
  en profundidad.
- Reutiliza calculos ya hechos por PredictionService/BI/Sincronizacion en lugar de rehacerlos.

Verificado: el estado global de los 6 dominios se materializa con conteos agregados; una segunda
consulta dentro de la ventana TTL se sirve de cache sin tocar la BD.

---

## 6. Consistencia

`verificar_consistencia()` compara el estado con las fuentes vivas y detecta incoherencias tipicas
(tiendas/terminales offline persistentes, cadenas de valor sin trazabilidad registrada). Ante una
incoherencia: la **registra** (`dt_incoherencias`), la **audita** (`log_auditoria`), **invalida** la
cache y publica un evento `GEMELO_RESINCRONIZAR`. Ejecutable bajo demanda o por el job de scheduler
(cada 6 h). El gemelo nunca puede quedar desactualizado: los eventos lo invalidan al instante y la
verificacion periodica cierra cualquier deriva.

---

## 7. Escalabilidad / SaaS

- **Multiempresa/multitienda**: todo se acota por `id_empresa` (y tienda cuando aplica).
- **Modular**: cada dominio es un modulo independiente; anadir un dominio nuevo es registrar una
  entrada en `DOMINIOS` sin tocar el resto.
- **SaaS-ready**: cache por proceso, tablas propias reversibles, sin estado compartido entre
  empresas.
- **Estimador/predictivo pluggable** heredado de los servicios reutilizados.

---

## 8. Compatibilidad

Aditivo y no intrusivo. No modifica el funcionamiento de: TPV, Facturacion, CRM, Inventario,
Compras, RRHH, Tesoreria, Workflow/BPM, Gobierno Corporativo, IA, Copiloto, Agentes,
Automatizacion, Prediccion, Centro de Actividad, Distribucion, Sincronizacion ni Event Bus. La
integracion con IA/Copiloto/Agentes va envuelta en `try/except`: si el gemelo no esta disponible,
cada uno se comporta exactamente como antes. **Certificado intacto** (Verifactu, AEAT, hashes,
numeraciones, Kardex, Contabilidad).

---

## 9. Pruebas

Verificacion end-to-end (`DB_NAME=smart_manager_test`):

- 8.1/8.2 Estado global: 6 dominios materializados, riesgo agregado, resumen ejecutivo. ✔
- 8.3-8.7 Estados por dominio con indicadores reales (workflows=1, facturas_pend=22, clientes=22,
  impagos=1, cobros_pend=291, recepciones_pend=42, ultima_actualizacion real de `movimientos_stock`). ✔
- 8.8 Grafo: `pedido P1 → recepcion → stock → venta → factura F5` recorrible hacia adelante Y hacia
  atras. ✔
- 8.9 Evento `VENTA_REGISTRADA` invalida la cache de `comercial`/`inventario`/`empresa`. ✔
- 8.10 Consultas instantaneas (procesos, recursos bloqueados, pedidos, incidencias). ✔
- 8.11 `IAService.estado_empresa/estado_dominio` sirven del gemelo. ✔
- 8.12 Copiloto: intents `estado.empresa` y `estado.tienda`, fuente «Gemelo Digital». ✔
- 8.13 Agente RRHH consume el gemelo (`fuentes` incluye «Gemelo Digital», datos con estado twin). ✔
- 8.14 Dashboard: 15 indicadores + riesgo global + alertas por dominio. ✔
- 8.15 Consistencia: verificacion + job scheduler `gemelo_consistencia` ejecutado. ✔

**Garantia de solo-lectura sobre datos operativos:** 0 INSERT/UPDATE/DELETE en los modulos de
estado y consulta; las unicas escrituras van a las tablas propias `dt_*`.

**Smoke:** `5 passed`.

---

## 10. Limitaciones (v1)

- Las aristas de dependencia se registran por API explicita o por pistas en el payload de eventos
  (`dt_origen`/`dt_destino`); el cableado automatico desde cada publicador certificado se hara de
  forma incremental y aditiva (sin tocar los flujos certificados).
- Los conteos operativos se apoyan en tablas cuyo nombre/estado se ha verificado contra el esquema
  real; modulos con esquema opcional degradan a 0 sin romper.
- El panel del gemelo es backend; la pantalla visual dedicada queda para una fase de GUI.
- `dt_snapshots` guarda foto global; el historico de series temporales del gemelo se puede ampliar
  reutilizando el Data Warehouse de BI.

---

## 11. Preparacion para el Simulador Empresarial (Enterprise 9)

El Gemelo Digital deja lista la base para el **Simulador Empresarial**:

- El **grafo de dependencias** permite propagar un cambio hipotetico por la cadena de valor
  (que pasaria si un pedido se retrasa, si sube un coste, si una tienda cae).
- El **estado por dominio con riesgo** es el punto de partida de cualquier escenario "what-if".
- Los **snapshots** proporcionan lineas base sobre las que comparar el resultado simulado.
- La **fachada unica** garantiza que el simulador consulte el mismo estado que ve la organizacion,
  sin duplicar logica.

---

*Local, sin commitear. Migracion 0094 aplicada y registrada en `MODULOS`. Smoke: 5 passed.*
