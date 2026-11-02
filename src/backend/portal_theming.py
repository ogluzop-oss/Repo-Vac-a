"""
Tema visual compartido por los 3 portales internos (Empleado, Empresa B2B/Gestión, Proveedor).

Reutiliza `services.saas.branding` (tabla `empresa_branding`, FASE SAAS-J) como ÚNICA fuente de
color por empresa — el mismo motor ya usado para el branding de documentos/PDF
(`color_primario`/`color_secundario`), ahora también para la identidad visual de estos tres
portales. Deliberadamente NO se reutiliza `db.web_tienda`/`web_config`: esa tabla es la marca de
la TIENDA ONLINE PÚBLICA (Canal Web, responsabilidad "congelada" documentada en CLAUDE.md), un
surface distinto de estos portales internos para empleados/proveedores/la propia empresa — usarla
aquí habría conflado dos identidades de marca potencialmente distintas bajo el mismo color.

Tres colores son personalizables (`color_primario` → acento `--ac`, `color_secundario` →
superficie de tarjetas `--bg2`, `color_terciario` → fondo general `--bg`, migración 0311): texto y
bordes se mantienen fijos, para que una elección de color del usuario nunca rompa el contraste de
lectura del resto de la interfaz — mismo criterio de seguridad que cualquier sistema de theming con
variables acotadas.
"""

import re

from markupsafe import escape


def _e(x):
    return str(escape(x if x is not None else ""))


# Pulido visual compartido por los 3 portales (sombras, transiciones suaves, hover de filas de
# tabla, scrollbar fina): mantiene EXACTAMENTE la misma paleta de cada portal (usa solo las
# variables `--*` ya definidas, nunca un color nuevo) — responde a "se ve muy básico" sin tocar
# ningún color. Un único bloque reutilizado por los 3 `_layout()` en vez de triplicarlo.
CSS_POLISH = """
*{scrollbar-width:thin;scrollbar-color:var(--borde) transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--borde);border-radius:999px}
::-webkit-scrollbar-thumb:hover{background:var(--text2)}
::selection{background:var(--ac);color:var(--bg)}
body{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
header{box-shadow:0 2px 14px rgba(0,0,0,.35)}
.card{box-shadow:0 2px 10px rgba(0,0,0,.22);transition:box-shadow .18s ease,border-color .18s ease}
.card:hover{box-shadow:0 4px 18px rgba(0,0,0,.3);border-color:var(--borde)}
nav a{transition:background .15s ease,color .15s ease}
button,.btn{transition:background .15s ease,color .15s ease,border-color .15s ease,
transform .08s ease,box-shadow .15s ease}
button:not(:disabled):hover,.btn:hover{box-shadow:0 2px 10px rgba(0,0,0,.25);transform:translateY(-1px)}
button:not(:disabled):active,.btn:active{transform:translateY(0)}
input,select,textarea{transition:border-color .15s ease,box-shadow .15s ease}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--ac);
box-shadow:0 0 0 3px color-mix(in srgb, var(--ac) 20%, transparent)}
table tbody tr{transition:background .12s ease}
table tbody tr:hover{background:rgba(255,255,255,.035)}
h1,h2{letter-spacing:.2px}
"""


# Paleta por defecto — IDÉNTICA a los literales que ya tenían los 3 portales antes de este
# cambio (cero diferencia visual si la empresa no ha personalizado nada).
_DEFECTOS = {
    "ac": "#00FFC6",
    "bg": "#0D1117",
    "bg2": "#161B22",
    "borde": "#30363D",
    "text": "#E6EDF3",
    "text2": "#8B949E",
    "err": "#F85149",
    "ok": "#3FB950",
}

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex_valido(v) -> bool:
    return bool(v) and bool(_HEX_RE.match(v))


def obtener_tema(id_empresa=None) -> dict:
    """Paleta efectiva de un portal para la empresa dada: `ac`/`bg2`/`bg` personalizables (si la
    empresa tiene `empresa_branding.color_primario`/`color_secundario`/`color_terciario`
    válidos), el resto fijo. Nunca lanza; degrada siempre a la paleta por defecto."""
    tema = dict(_DEFECTOS)
    try:
        from src.services.saas import branding
        b = branding.obtener_branding(id_empresa) or {}
        if _hex_valido(b.get("color_primario")):
            tema["ac"] = b["color_primario"]
        if _hex_valido(b.get("color_secundario")):
            tema["bg2"] = b["color_secundario"]
        if _hex_valido(b.get("color_terciario")):
            tema["bg"] = b["color_terciario"]
    except Exception:
        pass
    return tema


def bloque_css_variables(id_empresa=None) -> str:
    """Bloque `:root{...}` con las 8 variables semánticas de color, para interpolar DENTRO del
    `<style>` de cada portal en vez (o además) de los literales `:root{--ac:#00FFC6;}` previos."""
    t = obtener_tema(id_empresa)
    return ("{" + "".join(f"--{k}:{v};" for k, v in t.items()) + "}")


def guardar_tema(id_empresa, *, color_primario=None, color_secundario=None,
                 color_terciario=None) -> dict:
    """Guarda el acento/superficie/fondo elegidos para la empresa. Valida formato HEX; ignora
    (no guarda, no falla) cualquier valor que no sea un `#RRGGBB` válido. Devuelve
    {ok, errores:[...]}."""
    campos = {}
    errores = []
    if color_primario is not None:
        if _hex_valido(color_primario):
            campos["color_primario"] = color_primario.upper()
        else:
            errores.append("color_primario")
    if color_secundario is not None:
        if _hex_valido(color_secundario):
            campos["color_secundario"] = color_secundario.upper()
        else:
            errores.append("color_secundario")
    if color_terciario is not None:
        if _hex_valido(color_terciario):
            campos["color_terciario"] = color_terciario.upper()
        else:
            errores.append("color_terciario")
    if not campos:
        return {"ok": False, "errores": errores or ["sin_cambios"]}
    try:
        from src.services.saas import branding
        ok = branding.set_branding(id_empresa, **campos)
        return {"ok": bool(ok), "errores": errores}
    except Exception:
        return {"ok": False, "errores": errores + ["error_guardado"]}


def restablecer_tema(id_empresa) -> bool:
    """Vuelve la empresa a la paleta por defecto (acento turquesa + superficie + fondo estándar)."""
    try:
        from src.services.saas import branding
        return bool(branding.set_branding(
            id_empresa, color_primario=_DEFECTOS["ac"], color_secundario=_DEFECTOS["bg2"],
            color_terciario=_DEFECTOS["bg"]))
    except Exception:
        return False


def pagina_colores_html(*, titulo: str, accion_guardar: str, accion_volver: str,
                        accion_restablecer: str | None = None,
                        id_empresa=None, mensaje=None, error=None) -> str:
    """Fragmento de CONTENIDO (para pasar como `contenido` a la `_layout` de cada portal — no
    incluye `<html>/<head>`) de la página "Colores": selector de acento + superficie + fondo
    general (inputs HTML5 `type=color`, soportados nativamente por todos los navegadores
    modernos). Sin vista previa (retirada a petición explícita)."""
    t = obtener_tema(id_empresa)
    aviso = f'<p class="ok">{mensaje}</p>' if mensaje else ""
    aviso += f'<p class="error">{error}</p>' if error else ""
    restablecer_html = (
        f'<form method="post" action="{accion_restablecer}" style="display:inline">'
        f'<button type="submit" class="btn-danger">Restablecer</button></form>'
        if accion_restablecer else "")
    return f"""
<div class="card">
<h1>{titulo}</h1>
<p style="color:var(--text2);font-size:13px">Elige el color de acento, el de las tarjetas y el de
fondo general de este portal para tu empresa. El texto y los bordes se mantienen fijos para
garantizar la legibilidad.</p>
{aviso}
<form method="post" action="{accion_guardar}" id="form-colores">
<label>Color de acento (botones, enlaces, títulos)</label>
<input type="color" name="color_primario" id="inp-ac" value="{t['ac']}">
<label>Color de las tarjetas / superficies</label>
<input type="color" name="color_secundario" id="inp-bg2" value="{t['bg2']}">
<label>Color de fondo general de la interfaz</label>
<input type="color" name="color_terciario" id="inp-bg" value="{t['bg']}">
<div style="margin-top:14px">
<button type="submit">Guardar</button>
<a class="btn btn-ghost" href="{accion_volver}">Cancelar</a>
{restablecer_html}
</div>
</form>
</div>
"""
