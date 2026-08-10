# INVENTARIO DE DEPENDENCIAS UI — Smart Manager AI (Fase 0.5)

Mapa de dependencias de las ventanas afectadas **antes** de modificarlas, para no romper hosts ni
flujos ocultos. Cubre: contrato de navegación, imports, señales Qt, callbacks, rutas y dependencias
cruzadas. Read-only; ningún archivo modificado.

---

## 1. Contrato de navegación (menú → ventana)

`menu_principal.py::abrir_ventana_por_id(v_id)`:
```python
kwargs = {"callback_vuelta": self.mostrar_menu_principal, "usuario": sesion_global.usuario_actual}
# dispatch por v_id → import de la clase → manejar_apertura(v_id, Clase, **kwargs)
```
`menu_principal.py::manejar_apertura(identificador, clase_ventana, **kwargs)`:
- Gate SaaS: `enforcement.acceso_modulo(identificador)` (usa el `v_id`).
- Badge: `actividad.marcar_visto(identificador, usuario)`.
- Cierra instancia previa `self._ventanas[identificador]` (`.close()/.deleteLater()`).
- `kwargs["main"] = self` → **construye `clase_ventana(callback_vuelta, usuario, main)`** →
  `showMaximized()` → guarda en `self._ventanas[identificador]`.

**Implicación**: mantener el `v_id` preserva SaaS-gate, badges, cache de ventanas y navegación
(**regla 2, compatibilidad hacia atrás**). Firma pública obligatoria de toda ventana host:
`__init__(self, callback_vuelta=None, usuario=None, main=None, parent=None, **_kw)` (ya la cumplen
las 4 ventanas afectadas).

---

## 2. Ventanas afectadas

### 2.1 `bi` → `BIDashboardWindow` (`bi_dashboard.py`)
- **Firma**: `(callback_vuelta=None, usuario=None, main=None, parent=None, **_kw)`. ✔ contrato.
- **Imports compartidos**: `catalogo_gestion` → `_BG,_CIAN,_DIM,_btn,_btn_x,_combo,_tabla`.
- **Servicios**: `src.services.bi.kpis`, `bi.dashboard` (`_D.panel(...con_forecast=True)`).
- **Cross-dep**: usa `self.main` para navegar a Documentos → Exportaciones
  (`_abrir_documentos_exportaciones`, abre `self._doc_win.showMaximized()`). ⚠ Al embeber, **pasar
  `main`** para no romper "Ver archivo".
- **Self-show**: NO se auto-muestra en `__init__` (el único `showMaximized` es de `self._doc_win`,
  hijo bajo demanda). ✔ embebible como pestaña.
- **Señales públicas**: ninguna (`pyqtSignal` = 0). Bajo acoplamiento.
- **Botón volver**: solo si `callback_vuelta` → al embeber se pasa `None` (sin botón interno).

### 2.2 `notificaciones` → `CentroActividadWindow` (`centro_actividad.py`)
- **Firma**: contrato ✔. **Imports**: `catalogo_gestion` (`…,_inp,_tabla`).
- **Servicios**: `actividad`, `ia`, `copilot.servicio().preguntar(...)` (input "Preguntar" inline),
  `prediccion`, `automatizacion` (resumen). ⚠ Este input IA inline es **existente** y se conserva
  (no es la "UI del Copiloto" reservada; es una caja de consulta ya integrada).
- **Self-show**: `setWindowTitle(...)` (ignorado dentro de una pestaña); no `showMaximized` propio. ✔
- **Ruta**: `v_id "notificaciones"` sigue existiendo en el dispatcher (el botón se retiró, la ruta
  no). Se **conserva** (regla 2). El Centro pasa además a ser pestaña del Centro de Inteligencia.
- **Señales públicas**: ninguna.

### 2.3 `seguridad` → `SeguridadWindow` (`seguridad_gui.py`)
- **Firma**: contrato ✔. **Patrón host**: `QTabWidget` con métodos `_tab_roles/_tab_asignaciones/
  _tab_acl` → `self.tabs.addTab(w, "…")`. **Añadir** `_tab_gobierno` sin tocar los existentes.
- **Imports**: `catalogo_gestion` (`…,_inp,_tabla`), `_cat` (catálogo RBAC), `_R` (roles).
- **Al abrir**: `_cat.sincronizar_roles_sistema(_empresa())` (idempotente). Señales públicas: ninguna.

### 2.4 `workflow` → `WorkflowWindow` (`workflow_gui.py`)
- **Firma**: contrato ✔. **Patrón host**: `QTabWidget` (`_tab...` → "Pendientes"/"Diseñador").
  **Añadir** pestañas "Automatización", "Autonomía", "Historial" sin tocar las existentes.
- **Imports**: `catalogo_gestion` (`…,_tabla`), `_E` (workflow_engine `tareas_para_usuario`).
- **Señales públicas**: ninguna.

---

## 3. Dependencias cruzadas / riesgos

| Riesgo | Detalle | Mitigación |
|---|---|---|
| Romper "Ver archivo" de BI | `BIDashboardWindow` navega a Documentos vía `self.main` | Al embeber, pasar `main=` |
| Perder SaaS-gate/badges de `bi` | Dependen del `v_id="bi"` | **Conservar `v_id="bi"`**; solo cambia la clase destino y la etiqueta de tarjeta |
| Ruta `notificaciones` huérfana | El botón se retiró; la ruta sigue | Se conserva la ruta (regla 2); no se elimina |
| Estilos divergentes | Los 4 hosts usan helpers de `catalogo_gestion` | Foundation/tokens se **alinean** con `_BG/_CIAN/_DIM`; no se rompen |
| Input IA del Centro | `centro_actividad` usa `copilot.servicio()` | Se conserva intacto (no es la UI reservada del Copiloto) |

- **Señales Qt públicas**: **ninguna** en las 4 ventanas → no hay suscriptores externos que romper.
- **Acoplamiento de navegación**: solo `callback_vuelta` (volver) + `main` (navegación a otros
  módulos). Contrato estable.

---

## 4. Puntos de edición previstos (mínimos, compatibles)

1. `menu_principal.py`:
   - Tarjeta `bi`: cambiar **solo el texto** "Business Intelligence" → "Centro de Inteligencia
     Empresarial" (v_id "bi" intacto). Línea ~555.
   - Dispatcher `elif v_id == "bi"`: importar `InteligenciaWindow` (nuevo) en vez de
     `BIDashboardWindow`. Línea ~1310. (`BIDashboardWindow` se sigue usando embebido.)
2. `seguridad_gui.py`: `+ self.tabs.addTab(PanelGobierno(...), "Gobierno")`.
3. `workflow_gui.py`: `+ addTab` de Automatización/Autonomía/Historial (orden definido).
4. Nuevos: `inteligencia_gui.py`, `src/gui/paneles/*`, `src/gui/foundation/*`, `src/gui/components/*`.

Ninguna firma pública, `v_id`, ruta ni señal existente se elimina o cambia (solo se añade).

---

*Fase 0.5 completada. Siguiente: Fase 1 → construir `gui/foundation/` sin modificar ninguna ventana.*
