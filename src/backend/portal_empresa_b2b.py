"""
Extranet B2B de la Empresa (Smart Suppliers · Fase B) — servido por el backend, mismo patrón que
`storefront.py`/`portal_proveedor.py`: HTML por funciones puras + Flask fino. Sesión sin cookies: el
token (emitido por `b2b_sesion_empresa.crear_sesion`, futuro botón "Entrar al portal B2B" del
escritorio — Fase E) viaja en la URL y se revalida en cada petición.

"Actualizar Ofertas B2B" no es una sincronización que haya que disparar: `b2b_catalogo.buscar_para_empresa`
consulta la tabla en vivo en cada petición, así que el botón simplemente vuelve a cargar la página con
los datos más recientes — no hay caché ni copia local que refrescar (nunca se finge una sincronización
que no ocurre).
"""

import logging

from markupsafe import escape

from src.backend.portal_i18n import idioma_actual, registrar_selector_idioma, selector_idioma_html, t as _t

logger = logging.getLogger("backend.portal_empresa_b2b")

_ETIQUETA_UNIDAD = {"kg": "Kilos", "unidad": "Unidades", "pale": "Palés", "caja": "Cajas"}


def _e(x):
    return str(escape(x if x is not None else ""))


def _nav_html(token, activo, *, no_leidos=0):
    base = f"/portal/empresa/{token}"
    badge = f' <span class="badge-alerta">{no_leidos}</span>' if no_leidos else ""
    enlaces = (("dashboard", f"{base}/dashboard", _t("portal_emp2.nav_inicio", "Inicio")),
              ("catalogo", f"{base}/catalogo", _t("portal_emp2.nav_catalogo", "Catálogo B2B")),
              ("reposicion", f"{base}/reposicion", _t("portal_emp2.nav_reposicion", "Desde reposición")),
              ("carrito", f"{base}/carrito", _t("portal_emp2.nav_carrito", "Carrito")),
              ("plantillas", f"{base}/plantillas", _t("portal_emp2.nav_plantillas", "Plantillas")),
              ("pedidos", f"{base}/pedidos", f'{_t("portal_emp2.nav_pedidos", "Mis pedidos")}{badge}'),
              ("consignacion", f"{base}/consignacion", _t("portal_emp2.nav_consignacion", "Consignación")),
              ("gestion", f"{base}/gestion", _t("portal_emp2.nav_gestion", "Gestión")),
              ("colores", f"{base}/colores", _t("portal_emp2.nav_personalizacion", "Personalización")))
    return "".join(f'<a href="{href}"{" class=\"on\"" if activo == key else ""}>{label}</a>'
                   for key, href, label in enlaces) + selector_idioma_html(accion="/portal/empresa/idioma")


_FLECHA_SVG = ("data:image/svg+xml;utf8,"
              "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 8'%3E"
              "%3Cpath d='M1 1l5 5 5-5' stroke='%2300FFC6' stroke-width='2' fill='none' "
              "stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")

# Un <select> nativo solo se puede restilizar en su estado CERRADO — el popup de opciones lo pinta
# el navegador y ignora casi todo el CSS (colores fijos del SO, sin border-radius/hover propio). Para
# que el desplegado se parezca de verdad al QComboBox del escritorio (fondo oscuro, contorno cian,
# fila resaltada en cian al pasar el ratón), se sustituye la interacción por un popup propio en HTML:
# el <select> original se queda oculto pero sigue existiendo (su valor viaja igual en el formulario),
# así que si este script no llegara a ejecutarse el desplegable nativo seguiría siendo usable.
_CSEL_CSS = """
.csel-wrap{display:block;width:100%;position:relative;margin-bottom:10px}
.csel-trigger{padding:9px 10px;border-radius:10px;border:2px solid var(--ac);background:var(--bg);
color:#E6EDF3;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px}
.csel-arrow{width:12px;height:8px;flex:none;background-repeat:no-repeat;background-size:contain}
.csel-pop{display:none;position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:50;
background:var(--bg);border:2px solid var(--ac);border-radius:10px;max-height:240px;
overflow-y:auto;padding:4px}
.csel-pop.open{display:block}
.csel-opt{padding:8px 12px;border-radius:6px;color:#E6EDF3;cursor:pointer;font-weight:700;
font-size:14px}
.csel-opt:hover,.csel-opt.sel{background:var(--ac);color:var(--bg)}
"""
_CSEL_JS = f"""
document.addEventListener('DOMContentLoaded',function(){{
 document.querySelectorAll('select').forEach(function(sel){{
  var wrap=document.createElement('div');wrap.className='csel-wrap';
  sel.parentNode.insertBefore(wrap,sel);wrap.appendChild(sel);
  var trig=document.createElement('div');trig.className='csel-trigger';trig.tabIndex=0;
  var lbl=document.createElement('span');
  var arw=document.createElement('span');arw.className='csel-arrow';
  arw.style.backgroundImage=`url("{_FLECHA_SVG}")`;
  trig.appendChild(lbl);trig.appendChild(arw);
  var pop=document.createElement('div');pop.className='csel-pop';
  function refrescar(){{var o=sel.options[sel.selectedIndex];lbl.textContent=o?o.textContent:'';}}
  refrescar();
  Array.prototype.forEach.call(sel.options,function(opt,i){{
   var row=document.createElement('div');
   row.className='csel-opt'+(i===sel.selectedIndex?' sel':'');
   row.textContent=opt.textContent;
   row.addEventListener('click',function(){{
    sel.selectedIndex=i;refrescar();
    pop.querySelectorAll('.csel-opt').forEach(function(r){{r.classList.remove('sel');}});
    row.classList.add('sel');pop.classList.remove('open');
    sel.dispatchEvent(new Event('change',{{bubbles:true}}));
   }});
   pop.appendChild(row);
  }});
  trig.addEventListener('click',function(e){{
   e.stopPropagation();
   document.querySelectorAll('.csel-pop.open').forEach(function(p){{if(p!==pop)p.classList.remove('open');}});
   pop.classList.toggle('open');
  }});
  wrap.appendChild(trig);wrap.appendChild(pop);
  sel.style.display='none';
 }});
 document.addEventListener('click',function(){{
  document.querySelectorAll('.csel-pop.open').forEach(function(p){{p.classList.remove('open');}});
 }});
}});
"""

# El botón nativo de <input type=file> (::file-selector-button) y el texto "Ningún archivo
# seleccionado" que lo acompaña son parte del control del sistema operativo: su alto y su
# separación del resto no se pueden ajustar con fiabilidad entre navegadores (de ahí que quedara
# pegado al botón "Importar" con una altura ligeramente distinta). Se sustituye por el mismo patrón
# que el desplegable: un disparador propio con el mismo alto/tipografía que el resto de botones +
# el nombre del archivo en un <span> aparte, con espaciado explícito — el <input> original se
# mantiene oculto pero funcional (el archivo se sigue enviando igual en el formulario).
_CFILE_CSS = """
.cfile-wrap{display:flex;align-items:center;flex-wrap:wrap;gap:14px;margin-top:14px;margin-bottom:10px}
.cfile-trigger{padding:9px 16px;border-radius:8px;border:2px solid var(--ac);background:transparent;
color:var(--ac);font-weight:900;cursor:pointer;font-family:'Segoe UI',system-ui,sans-serif;
font-size:13px}
.cfile-trigger:hover{background:var(--ac);color:var(--bg)}
.cfile-name{color:#8B949E;font-weight:700;font-size:14px;font-family:'Segoe UI',system-ui,sans-serif}
"""
_CFILE_JS = """
document.addEventListener('DOMContentLoaded',function(){
 document.querySelectorAll('input[type=file]').forEach(function(inp){
  var wrap=document.createElement('div');wrap.className='cfile-wrap';
  inp.parentNode.insertBefore(wrap,inp);wrap.appendChild(inp);
  var trig=document.createElement('div');trig.className='cfile-trigger';trig.tabIndex=0;
  trig.textContent='Seleccionar archivo';
  var name=document.createElement('span');name.className='cfile-name';
  name.textContent='Ningún archivo seleccionado';
  trig.addEventListener('click',function(){inp.click();});
  inp.addEventListener('change',function(){
   name.textContent=(inp.files&&inp.files.length)?inp.files[0].name:'Ningún archivo seleccionado';
  });
  wrap.appendChild(trig);wrap.appendChild(name);
  inp.style.display='none';
 });
});
"""


# El popup nativo de <input type=date>/<input type=datetime-local> lo pinta el navegador/SO y está
# fuera del alcance de CSS en todos los motores (Chrome/Firefox/Edge, Windows/mac/Linux): `color-scheme:
# dark` solo insinúa la paleta de color por defecto del popup, nunca puede darle el borde/radio cian de
# la app — limitación real de la plataforma web, sin arreglo solo-CSS. Un primer intento interceptó el
# `mousedown` del <input> real (`preventDefault` + foco manual) para impedir que el picker nativo
# llegara a abrirse — resultó NO fiable: el icono de calendario de Chrome/Edge es un control interno
# de shadow-DOM que no siempre respeta `preventDefault` sobre ese target, y en varias versiones de
# Chromium un clic en cualquier punto del campo podía seguir disparando el popup nativo — se confirmó
# en producción con AMBOS calendarios (el propio y el nativo) abiertos a la vez.
#
# Arreglo robusto (el mismo criterio que el <select>/<input type=file> de arriba, llevado un paso más
# lejos): el <input> real pasa a `type="text"` — un campo de texto no tiene NUNCA picker nativo, en
# ningún navegador, así que no hay nada que suprimir. El `name` y el FORMATO del valor
# (`AAAA-MM-DD`/`AAAA-MM-DDTHH:MM`) se mantienen exactamente iguales — el backend que procesa el
# formulario no se toca. Como ya no hay `type=date/datetime-local` que detectar, el HTML marca cada
# campo con `data-cdate-tipo="date"` / `"datetime-local"` (además de un `placeholder` explícito, que
# el navegador ya no rellena solo al ser texto) y el script se engancha a ese atributo. Si este script
# no llegara a ejecutarse, el campo sigue siendo un <input type=text> normal y editable (degradación
# segura: el usuario podría teclear la fecha a mano en el mismo formato). Deliberadamente NO se usa
# `readonly`: un campo `readonly` queda "barred from constraint validation" (spec HTML) y el atributo
# `required` de los formularios de Licitaciones/Contratos/Rappels dejaría de bloquear el envío —
# `required` sobre `type="text"` sí participa en la validación de restricciones exactamente igual que
# sobre `type="date"` (misma sección del spec, "barred from constraint validation" no aplica a texto
# normal), así que el campo sigue siendo 100% validable sin ese truco.
_CDATE_CSS = """
.cdate-wrap{display:inline-block;position:relative;vertical-align:middle}
input[data-cdate-tipo]::placeholder{color:#8B949E;opacity:1;font-weight:700}
.cdate-pop{display:none;position:absolute;top:calc(100% + 6px);left:0;z-index:1000;width:240px;
background:var(--bg);border:2px solid var(--ac);border-radius:10px;padding:12px;
box-shadow:0 8px 24px rgba(0,0,0,.5)}
.cdate-pop.open{display:block}
.cdate-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.cdate-nav{padding:0;margin:0;width:26px;height:26px;border-radius:6px;border:1px solid var(--ac);
background:transparent;color:var(--ac);font-weight:900;font-size:14px;line-height:1;cursor:pointer}
.cdate-nav:hover{background:var(--ac);color:var(--bg)}
.cdate-label{color:#E6EDF3;font-weight:900;font-size:13px;text-transform:capitalize}
.cdate-dow{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:4px}
.cdate-dow span{display:block;text-align:center;font-size:11px;color:#8B949E;font-weight:900}
.cdate-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.cdate-day{display:block;text-align:center;padding:6px 0;border-radius:6px;font-size:13px;
color:#E6EDF3;cursor:pointer;font-weight:700}
.cdate-day:hover{background:#21262D}
.cdate-day.hoy{border:1px solid var(--ac)}
.cdate-day.sel{background:var(--ac);color:var(--bg);font-weight:900}
.cdate-day.vacio{visibility:hidden;cursor:default}
.cdate-time{display:flex;align-items:center;gap:6px;margin-top:10px;padding-top:10px;
border-top:1px solid #30363D}
.cdate-time input{width:50px;margin:0;padding:6px;text-align:center}
.cdate-time span{color:#8B949E;font-weight:900;font-size:12px}
.cdate-foot{display:flex;justify-content:space-between;gap:8px;margin-top:10px;padding-top:10px;
border-top:1px solid #30363D}
.cdate-foot button{margin:0;padding:6px 10px;font-size:12px}
"""
_CDATE_JS = """
document.addEventListener('DOMContentLoaded',function(){
 var MESES=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre',
   'octubre','noviembre','diciembre'];
 var DOW=['L','M','X','J','V','S','D'];
 function pad2(n){n=String(n);return n.length<2?'0'+n:n;}
 function crear(inp){
  var esDT=inp.dataset.cdateTipo==='datetime-local';
  var wrap=document.createElement('div');wrap.className='cdate-wrap';
  inp.parentNode.insertBefore(wrap,inp);wrap.appendChild(inp);
  var pop=document.createElement('div');pop.className='cdate-pop';
  var head=document.createElement('div');head.className='cdate-head';
  var btnPrev=document.createElement('button');btnPrev.type='button';btnPrev.className='cdate-nav';
  btnPrev.textContent='\\u2039';
  var lbl=document.createElement('span');lbl.className='cdate-label';
  var btnNext=document.createElement('button');btnNext.type='button';btnNext.className='cdate-nav';
  btnNext.textContent='\\u203a';
  head.appendChild(btnPrev);head.appendChild(lbl);head.appendChild(btnNext);
  var dow=document.createElement('div');dow.className='cdate-dow';
  DOW.forEach(function(d){var s=document.createElement('span');s.textContent=d;dow.appendChild(s);});
  var grid=document.createElement('div');grid.className='cdate-grid';
  var inHora=null,inMin=null,timeRow=null;
  if(esDT){
   timeRow=document.createElement('div');timeRow.className='cdate-time';
   inHora=document.createElement('input');inHora.type='number';inHora.min='0';inHora.max='23';
   inMin=document.createElement('input');inMin.type='number';inMin.min='0';inMin.max='59';
   var sep=document.createElement('span');sep.textContent=':';
   var etq=document.createElement('span');etq.textContent='Hora';etq.style.marginLeft='6px';
   timeRow.appendChild(inHora);timeRow.appendChild(sep);timeRow.appendChild(inMin);
   timeRow.appendChild(etq);
  }
  var foot=document.createElement('div');foot.className='cdate-foot';
  var btnBorrar=document.createElement('button');btnBorrar.type='button';btnBorrar.textContent='Borrar';
  var btnHoy=document.createElement('button');btnHoy.type='button';btnHoy.textContent='Hoy';
  foot.appendChild(btnBorrar);foot.appendChild(btnHoy);
  pop.appendChild(head);pop.appendChild(dow);pop.appendChild(grid);
  if(timeRow)pop.appendChild(timeRow);
  pop.appendChild(foot);
  wrap.appendChild(pop);
  var vista={year:null,month:null};
  function leer(){
   var v=inp.value;if(!v)return null;
   var m=/^(\\d{4})-(\\d{2})-(\\d{2})(?:T(\\d{2}):(\\d{2}))?/.exec(v);
   if(!m)return null;
   return{y:+m[1],mo:+m[2]-1,d:+m[3],h:m[4]?+m[4]:0,mi:m[5]?+m[5]:0};
  }
  function escribir(y,mo,d,h,mi){
   var s=y+'-'+pad2(mo+1)+'-'+pad2(d);
   if(esDT)s+='T'+pad2(h==null?0:h)+':'+pad2(mi==null?0:mi);
   inp.value=s;
   inp.dispatchEvent(new Event('input',{bubbles:true}));
   inp.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function pintar(){
   var hoy=new Date();var actual=leer();
   lbl.textContent=MESES[vista.month].charAt(0).toUpperCase()+MESES[vista.month].slice(1)+' '+vista.year;
   grid.innerHTML='';
   var primero=new Date(vista.year,vista.month,1);
   var offset=(primero.getDay()+6)%7;
   var totalDias=new Date(vista.year,vista.month+1,0).getDate();
   for(var i=0;i<offset;i++){
    var vac=document.createElement('span');vac.className='cdate-day vacio';vac.textContent='.';
    grid.appendChild(vac);
   }
   var _loop=function(dia){
    var celda=document.createElement('span');celda.className='cdate-day';celda.textContent=dia;
    if(vista.year===hoy.getFullYear()&&vista.month===hoy.getMonth()&&dia===hoy.getDate())
     celda.classList.add('hoy');
    if(actual&&actual.y===vista.year&&actual.mo===vista.month&&actual.d===dia)
     celda.classList.add('sel');
    celda.addEventListener('click',function(e){
     e.stopPropagation();
     var h=esDT?(parseInt(inHora.value,10)||0):null;
     var mi=esDT?(parseInt(inMin.value,10)||0):null;
     escribir(vista.year,vista.month,dia,h,mi);
     pintar();
     if(!esDT)cerrar();
    });
    grid.appendChild(celda);
   };
   for(var d=1;d<=totalDias;d++)_loop(d);
   if(esDT){
    var base=actual||{h:0,mi:0};
    inHora.value=pad2(base.h);inMin.value=pad2(base.mi);
   }
  }
  function abrir(){
   document.querySelectorAll('.cdate-pop.open').forEach(function(p){if(p!==pop)p.classList.remove('open');});
   var actual=leer();var base=actual?null:new Date();
   vista.year=actual?actual.y:base.getFullYear();
   vista.month=actual?actual.mo:base.getMonth();
   pintar();
   pop.classList.add('open');
  }
  function cerrar(){pop.classList.remove('open');}
  btnPrev.addEventListener('click',function(e){
   e.stopPropagation();vista.month--;if(vista.month<0){vista.month=11;vista.year--;}pintar();
  });
  btnNext.addEventListener('click',function(e){
   e.stopPropagation();vista.month++;if(vista.month>11){vista.month=0;vista.year++;}pintar();
  });
  btnHoy.addEventListener('click',function(e){
   e.stopPropagation();
   var hoy=new Date();
   escribir(hoy.getFullYear(),hoy.getMonth(),hoy.getDate(),esDT?hoy.getHours():null,
     esDT?hoy.getMinutes():null);
   vista.year=hoy.getFullYear();vista.month=hoy.getMonth();
   pintar();cerrar();
  });
  btnBorrar.addEventListener('click',function(e){
   e.stopPropagation();
   inp.value='';
   inp.dispatchEvent(new Event('input',{bubbles:true}));
   inp.dispatchEvent(new Event('change',{bubbles:true}));
   cerrar();
  });
  pop.addEventListener('click',function(e){e.stopPropagation();});
  if(esDT){
   [inHora,inMin].forEach(function(campo){
    campo.addEventListener('click',function(e){e.stopPropagation();});
    campo.addEventListener('change',function(){
     var actual=leer();
     var base=actual||{y:vista.year,mo:vista.month,d:(new Date()).getDate()};
     var h=Math.min(23,Math.max(0,parseInt(inHora.value,10)||0));
     var mi=Math.min(59,Math.max(0,parseInt(inMin.value,10)||0));
     escribir(base.y,base.mo,base.d,h,mi);
    });
    campo.addEventListener('blur',function(){
     setTimeout(function(){if(!wrap.contains(document.activeElement))cerrar();},0);
    });
   });
  }
  inp.addEventListener('click',function(e){e.stopPropagation();abrir();});
  inp.addEventListener('focus',function(){abrir();});
  inp.addEventListener('blur',function(){
   setTimeout(function(){if(!wrap.contains(document.activeElement))cerrar();},0);
  });
  inp.addEventListener('keydown',function(e){
   if(e.altKey&&e.key==='ArrowDown'){e.preventDefault();abrir();}
   else if(e.key==='Escape'){cerrar();}
  });
 }
 document.querySelectorAll('input[data-cdate-tipo]').forEach(function(inp){
  if(inp.dataset.cdate)return;
  inp.dataset.cdate='1';
  crear(inp);
 });
 document.addEventListener('click',function(){
  document.querySelectorAll('.cdate-pop.open').forEach(function(p){p.classList.remove('open');});
 });
});
"""


def _layout(titulo, contenido, nav="", id_empresa=None):
    from src.backend import portal_theming as _tema
    if id_empresa is None:
        try:
            from flask import g
            id_empresa = getattr(g, "id_empresa", None)
        except Exception:
            pass
    return f"""<!doctype html><html lang="{_e(idioma_actual())}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(titulo)} · Portal B2B</title><style>
:root{_tema.bloque_css_variables(id_empresa)}
*{{box-sizing:border-box}}body{{margin:0;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;
background:var(--bg);color:var(--text)}}
header{{display:flex;align-items:center;gap:16px;padding:14px 24px;background:#111418;
border-bottom:2px solid var(--ac)}}
.logo{{font-weight:900;font-size:20px;color:var(--ac)}}
nav{{display:flex;flex-wrap:wrap;gap:8px;padding:12px 24px;background:var(--bg);border-bottom:1px solid #21262D}}
nav a{{color:var(--text2);text-decoration:none;font-weight:700;font-size:13px;padding:6px 10px;
border-radius:8px}}nav a.on,nav a:hover{{color:var(--bg);background:var(--ac)}}
main{{max-width:1000px;margin:0 auto;padding:24px}}
h1,h2{{color:var(--ac);font-weight:900}}
.card{{background:var(--bg2);border:1px solid var(--borde);border-radius:12px;padding:18px;margin-bottom:16px}}
label{{display:block;font-size:14px;color:var(--text2);margin:10px 0 4px;font-weight:700}}
input,select{{padding:9px 10px;border-radius:8px;border:1px solid var(--borde);
background:var(--bg);color:var(--text);font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;
font-weight:700;margin:0 10px 10px 0}}
input[type=color]{{height:42px;padding:4px;cursor:pointer}}
select{{appearance:none;-webkit-appearance:none;border:2px solid var(--ac);border-radius:10px;
background-color:var(--bg);background-image:url("{_FLECHA_SVG}");background-repeat:no-repeat;
background-position:right 12px center;background-size:12px 8px;padding-right:32px;cursor:pointer}}
select:focus{{outline:none;border-color:var(--ac)}}
input[type=number]::-webkit-inner-spin-button,input[type=number]::-webkit-outer-spin-button{{
-webkit-appearance:none;margin:0}}
input[type=number]{{-moz-appearance:textfield}}
input[type=time],input[data-cdate-tipo]{{background:var(--bg);color:var(--text);
border:1px solid var(--ac);border-radius:8px;color-scheme:dark}}
input[type=time]::-webkit-calendar-picker-indicator{{filter:invert(1) sepia(1) saturate(5)
hue-rotate(120deg);cursor:pointer}}
button,.btn{{padding:9px 16px;border-radius:8px;border:2px solid var(--ac);background:transparent;
color:var(--ac);font-weight:900;cursor:pointer;text-decoration:none;display:inline-block;
font-size:13px;font-family:'Segoe UI',system-ui,sans-serif;margin:0 10px 10px 0}}
button:hover,.btn:hover{{background:var(--ac);color:var(--bg)}}
.btn-ghost{{background:transparent;color:var(--text2);border:2px solid var(--borde)}}
.btn-ghost:hover{{background:var(--text2);color:var(--bg);border-color:var(--text2)}}
.btn-danger{{background:transparent;color:var(--err);border:2px solid var(--err)}}
.btn-danger:hover{{background:var(--err);color:var(--bg)}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #21262D;font-size:13px;vertical-align:middle}}
th{{color:var(--text2)}}
.badge{{display:inline-block;background:#21262D;color:var(--ac);border-radius:6px;padding:2px 8px;
font-size:11px;font-weight:700}}
.badge-ok{{background:var(--ok);color:var(--bg)}}
.error{{color:var(--err);font-weight:700}}.ok{{color:var(--ok);font-weight:700}}
.total{{font-size:20px;font-weight:900;color:var(--ac)}}
form.inline{{display:flex;gap:8px;align-items:center}}
form.inline input[type=number]{{width:70px}}
a.gestion-card{{display:block;margin-bottom:10px;padding:14px 16px;text-align:left;
background:transparent;border:2px solid var(--ac);border-radius:10px;text-decoration:none}}
a.gestion-card b{{color:var(--ac)}}
a.gestion-card span{{color:var(--text2);font-size:14px;font-weight:700;
font-family:'Segoe UI',system-ui,sans-serif}}
a.gestion-card:hover{{background:var(--ac)}}
a.gestion-card:hover b,a.gestion-card:hover span{{color:var(--bg)}}
.badge-alerta{{display:inline-block;min-width:16px;padding:1px 6px;border-radius:999px;
background:var(--err);color:#fff;font-size:11px;font-weight:900;text-align:center}}
.banner-abandono{{background:var(--bg2);border:2px solid var(--ac);border-radius:12px;padding:16px 18px;
margin-bottom:16px;box-shadow:0 0 16px rgba(0,255,198,.3);display:flex;align-items:center;
justify-content:space-between;gap:16px;flex-wrap:wrap}}
.banner-abandono p{{margin:0;font-weight:900;color:var(--ac);font-size:14px}}
.banner-abandono button{{margin:0}}
.progreso{{width:100%;height:14px;border-radius:999px;background:var(--bg);border:1px solid var(--borde);
overflow:hidden;margin-top:8px}}
.progreso-barra{{height:100%;border-radius:999px;transition:width .2s}}
.chat{{display:flex;flex-direction:column;gap:10px;max-height:420px;overflow-y:auto;margin-bottom:12px}}
.msg{{max-width:75%;padding:8px 12px;border-radius:12px;background:var(--bg);border:1px solid var(--borde)}}
.msg-propio{{align-self:flex-end;border-color:var(--ac)}}
.msg-otro{{align-self:flex-start}}
.msg-autor{{font-size:11px;color:var(--ac);font-weight:900;margin-bottom:2px}}
.msg-cuerpo{{font-size:14px;color:var(--text);white-space:pre-wrap;word-break:break-word}}
.msg-fecha{{font-size:10px;color:var(--text2);margin-top:4px}}
textarea{{width:100%;padding:9px 10px;border-radius:8px;border:1px solid var(--borde);background:var(--bg);
color:var(--text);font-size:14px;font-family:'Segoe UI',system-ui,sans-serif;font-weight:700;resize:vertical;
margin-bottom:10px}}
{_CSEL_CSS}
{_CFILE_CSS}
{_CDATE_CSS}
.sel-idioma{{margin-left:auto}}.sel-idioma select{{padding:5px 24px 5px 8px;font-size:12px;margin:0}}
{_tema.CSS_POLISH}
</style></head><body>
<header><span class="logo">🏢 {_t("portal_emp2.titulo_marca", "Portal B2B")}</span></header>
<nav>{nav}</nav>
<main>{contenido}</main>
<script>{_CSEL_JS}</script>
<script>{_CFILE_JS}</script>
<script>{_CDATE_JS}</script>
</body></html>"""


def _pagina_error(titulo, mensaje, codigo=200):
    return _layout(titulo, f"<div class='card'><h1>{_e(titulo)}</h1><p class='error'>{_e(mensaje)}</p></div>")


# ── Detección de duplicados antes de un pedido (petición explícita) ────────────────────────────
def pagina_confirmar_duplicado(token, art, dup, id_catalogo, cantidad):
    """Coincidencia EXACTA de Nombre+Talla+Marca+Color entre el artículo del catálogo del
    proveedor (`art`) y uno YA EXISTENTE en el catálogo interno (`dup`) — Sí/No explícito antes de
    seguir con el pedido: "No" continúa el pedido como artículo distinto (mismo POST de añadir al
    carrito, con `confirmado=1` para no volver a preguntar); "Sí" va a Alta artículo para crear la
    equivalencia (vincular la referencia del proveedor al artículo existente, sin duplicar nada)."""
    base = f"/portal/empresa/{token}"
    from urllib.parse import urlencode
    qs_si = urlencode({
        "vincular_a": dup["codigo"], "id_suministrador": art["id_suministrador"],
        "nombre_proveedor": art.get("proveedor_nombre") or "", "referencia_proveedor": art["codigo"],
    })
    return _layout(_t("portal_emp2.posible_duplicado_titulo", "Posible duplicado"), f"""
<div class="card"><h1>⚠ {_t("portal_emp2.posible_duplicado_h1", "Posible artículo duplicado")}</h1>
<p>{_t("portal_emp2.coincide_exactamente", "El artículo del proveedor {n} coincide EXACTAMENTE en nombre", n=f"<b>{_e(art['nombre'])}</b>")}
{_t("portal_emp2.y_talla", " y talla ({t})", t=_e(art.get('talla'))) if art.get('talla') else ""}
{_t("portal_emp2.y_marca", " y marca ({m})", m=_e(art.get('marca'))) if art.get('marca') else ""}
{_t("portal_emp2.y_color", " y color ({c})", c=_e(art.get('color'))) if art.get('color') else ""}
{_t("portal_emp2.con_articulo_existente", "con un artículo que YA tienes en tu catálogo interno:")}</p>
<p><b>{_e(dup['nombre'])}</b> ({_t("portal_emp2.codigo_lbl", "código {c}", c=_e(dup['codigo']))})</p>
<p>{_t("portal_emp2.es_mismo_articulo", "¿Es el mismo artículo?")}</p>
<div style="display:flex;gap:12px;margin-top:10px">
<a href="{base}/gestion/alta_articulo?{qs_si}" class="btn btn-primary">{_t("portal_emp2.si_es_mismo_btn", "Sí, es el mismo — vincular")}</a>
<form method="post" action="{base}/catalogo/anadir">
<input type="hidden" name="id_catalogo" value="{_e(id_catalogo)}">
<input type="hidden" name="cantidad" value="{_e(cantidad)}">
<input type="hidden" name="confirmado" value="1">
<button type="submit" class="btn btn-ghost">{_t("portal_emp2.no_es_distinto_btn", "No, es un artículo distinto — continuar el pedido")}</button>
</form>
</div>
</div>""", nav=_nav_html(token, "catalogo"))


# ── Dashboard ──────────────────────────────────────────────────────────────────
def _banner_carrito_abandonado_html(token, abandono):
    """Aviso "Reanudar Pedido" (cierre de brecha de automatización — carritos B2B abandonados). Solo
    se muestra si hay un carrito sin resolver para esta empresa (`b2b_carrito_abandono`, detectado por
    `b2b_carrito_abandono.detectar_y_marcar`). El botón envía al endpoint de reanudación, que
    transfiere las líneas al `token_sesion` de la sesión ACTUAL antes de ir al carrito — ver
    `b2b_carrito.reasignar_token` para por qué hace falta transferir y no solo enlazar."""
    if not abandono:
        return ""
    base = f"/portal/empresa/{token}"
    return f"""<div class="banner-abandono">
<p>🛒 {_t("portal_emp2.pedido_pendiente_finalizar", "Tienes un pedido pendiente de finalizar — {n} artículo(s) por {t} €, sin actividad desde hace más de 2 horas.", n=abandono['n_lineas'], t=abandono['total'])}</p>
<form method="post" action="{base}/carrito/reanudar/{_e(abandono['token_sesion'])}">
<button type="submit">{_t("portal_emp2.reanudar_pedido_btn", "Reanudar Pedido")}</button></form>
</div>"""


def pagina_dashboard(token, sesion, *, n_carrito=0, limite_actual=None, no_leidos=0, abandono=None):
    base = f"/portal/empresa/{token}"
    valor_limite = f'value="{limite_actual}"' if limite_actual is not None else ""
    banner = _banner_carrito_abandonado_html(token, abandono)
    return _layout(_t("portal_emp2.nav_inicio", "Inicio"), f"""
{banner}
<div class="card">
<h1>{_t("portal_emp2.bienvenido_h1", "Bienvenido, {n}", n=_e(sesion.get('nombre_usuario') or _t("portal_emp2.usuario_generico", "usuario")))}</h1>
<p>{_t("portal_emp2.tienda_conectada_lbl", "Tienda conectada:")} <span class="badge">#{_e(sesion.get('id_tienda'))}</span>
· {_t("portal_emp2.sector_lbl", "Sector:")} <span class="badge">{_e(sesion.get('sector_id'))}</span></p>
<p>{_t("portal_emp2.reponer_otra_tienda_desc", "Para reponer una tienda distinta, vuelve a Smart Manager, conéctate remotamente a ella y entra de nuevo al portal.")}</p>
<p>{_t("portal_emp2.articulos_carrito_lbl", "Artículos en tu carrito:")} <span class="badge">{n_carrito}</span></p>
</div>
<div class="card"><h2>{_t("portal_emp2.limite_gasto_h2", "Límite de gasto mensual (B2B)")}</h2>
<p>{_t("portal_emp2.limite_gasto_desc",
      "Aviso visual (no bloqueante) en el carrito cuando el gasto validado del mes más el "
      "carrito actual supere este límite. Déjalo vacío para desactivarlo.")}</p>
<form class="inline" method="post" action="{base}/dashboard/limite-gasto">
<input type="number" name="limite" step="0.01" min="0" placeholder="{_t("portal_emp2.sin_limite_ph", "Sin límite")}" style="min-width:120px" {valor_limite}>
<span>{_t("portal_emp2.eur_mes", "€ / mes")}</span>
<button type="submit">{_t("portal_emp2.guardar_btn", "Guardar")}</button>
</form></div>""", nav=_nav_html(token, "dashboard", no_leidos=no_leidos))


# ── Consignación (Fase C — Stock en Consignación) ────────────────────────────
# Vista de empresa, en tiempo real (consulta el ledger en vivo, mismo criterio que el catálogo B2B —
# ver docstring de cabecera del módulo): saldo por proveedor × artículo de TODO el stock en
# consignación que esta empresa tiene depositado, aún sin consumir ni devolver. `b2b_consignacion_
# saldo`/`_movimientos` son la fuente real (`services.compras.b2b_pedidos`); el escrow B2B
# (`b2b_escrow.py`) nunca interviene en estos pedidos.
def pagina_consignacion_empresa(token, bloques, *, no_leidos=0):
    """`bloques`: [(nombre_proveedor, [saldo_dict, ...])]."""
    secciones = []
    for nombre_proveedor, saldos in bloques:
        filas = "".join(f"""<tr><td>{_e(s['codigo_articulo'])}</td>
<td>{s['cantidad_depositada']}</td><td>{s['cantidad_consumida']}</td><td>{s['cantidad_devuelta']}</td>
<td><b>{int(s['cantidad_depositada']) - int(s['cantidad_consumida']) - int(s['cantidad_devuelta'])}</b></td>
<td>{s['precio_unitario']} €</td></tr>""" for s in saldos)
        tabla = (f'<table><tr><th>{_t("portal_emp2.col_articulo", "Artículo")}</th>'
                f'<th>{_t("portal_emp2.col_depositado", "Depositado")}</th>'
                f'<th>{_t("portal_emp2.col_consumido", "Consumido")}</th>'
                f'<th>{_t("portal_emp2.col_devuelto", "Devuelto")}</th>'
                f'<th>{_t("portal_emp2.col_disponible", "Disponible")}</th>'
                f'<th>{_t("portal_emp2.col_precio", "Precio")}</th></tr>{filas}</table>' if saldos
                else f'<p>{_t("portal_emp2.sin_depositos", "Sin depósitos todavía.")}</p>')
        secciones.append(f"""<div class="card"><h2>{_e(nombre_proveedor)}</h2>{tabla}</div>""")
    contenido = "".join(secciones) or (
        f'<div class=\'card\'><p>{_t("portal_emp2.sin_consignacion_proveedor", "No tienes stock en consignación de ningún proveedor todavía.")}</p></div>')
    return _layout(_t("portal_emp2.nav_consignacion", "Consignación"), f"""
<div class="card"><h1>{_t("portal_emp2.stock_consignacion_h1", "Stock en consignación")}</h1>
<p>{_t("portal_emp2.stock_consignacion_desc",
      'Mercancía depositada por tus proveedores que sigue siendo SUYA hasta que la consumes '
      '(vendes/usas): al consumirse se liquida y factura automáticamente, sola. "Disponible" es '
      "lo que aún puedes usar o devolver sin ningún coste.")}</p>
</div>
{contenido}""", nav=_nav_html(token, "consignacion", no_leidos=no_leidos))


# ── Catálogo B2B ───────────────────────────────────────────────────────────────
def pagina_catalogo(token, articulos, *, texto="", mensaje=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    anadir_btn = _t("portal_emp2.anadir_btn", "Añadir")
    disp_consig_badge = _t("portal_emp2.disponible_consignacion_badge", "Disponible en consignación")
    filas = "".join(f"""<tr>
<td><a href="{base}/catalogo/{a['id']}" style="color:var(--ac);font-weight:900;text-decoration:none">
{_e(a['nombre'])}</a><br><span class="badge">{_e(a['proveedor_nombre'])}</span>
{f'<br><span class="badge badge-ok">{disp_consig_badge}</span>' if a.get('disponible_consignacion') else ''}</td>
<td>{_ETIQUETA_UNIDAD.get(a['unidad_medida'], a['unidad_medida'])}</td>
<td>{a['moq']}</td><td>{a['precio_unitario']} €</td>
<td><form class="inline" method="post" action="{base}/catalogo/anadir">
<input type="hidden" name="id_catalogo" value="{a['id']}">
<input type="number" name="cantidad" min="{a['moq']}" value="{a['moq']}">
<button type="submit">{anadir_btn}</button></form></td></tr>""" for a in articulos)
    tabla = (f'<table><tr><th>{_t("portal_emp2.col_articulo", "Artículo")}</th>'
            f'<th>{_t("portal_emp2.col_unidad", "Unidad")}</th><th>MOQ</th>'
            f'<th>{_t("portal_emp2.col_precio", "Precio")}</th><th></th></tr>'
            f"{filas}</table>") if articulos else f'<p>{_t("portal_emp2.sin_ofertas_sector", "No hay ofertas disponibles para tu sector ahora mismo.")}</p>'
    return _layout(_t("portal_emp2.nav_catalogo", "Catálogo B2B"), f"""
<div class="card">
<h1>{_t("portal_emp2.catalogo_b2b_sector_h1", "Catálogo B2B de tu sector")}</h1>
<form method="get" action="{base}/catalogo">
<input type="text" name="q" placeholder="{_t("portal_emp2.buscar_articulo_ph", "Buscar artículo…")}" value="{_e(texto)}">
<button type="submit" class="btn-ghost">🔍</button>
<button type="submit" name="actualizar" value="1">🔄 {_t("portal_emp2.actualizar_ofertas_btn", "Actualizar Ofertas B2B")}</button>
</form>
{aviso}{tabla}
</div>""", nav=_nav_html(token, "catalogo", no_leidos=no_leidos))


# ── Ficha de producto (cross-sell + bundles) ─────────────────────────────────
def _bloque_relacionados_html(base, relacionados):
    if not relacionados:
        return ""
    tarjetas = "".join(f"""<div class="card" style="flex:1 1 200px;margin-bottom:0">
<b>{_e(a['nombre'])}</b><br><span class="badge">{a['precio_unitario']} €</span>
<form class="inline" method="post" action="{base}/catalogo/anadir" style="margin-top:8px">
<input type="hidden" name="id_catalogo" value="{a['id']}">
<input type="number" name="cantidad" min="{a['moq']}" value="{a['moq']}">
<button type="submit" class="btn-ghost">{_t("portal_emp2.anadir_btn", "Añadir")}</button></form></div>""" for a in relacionados)
    return f"""<div class="card"><h2>{_t("portal_emp2.comprados_juntos_h2", "Comprados juntos habitualmente")}</h2>
<div style="display:flex;gap:12px;flex-wrap:wrap">{tarjetas}</div></div>"""


def _bloque_bundles_html(regla_items):
    if not regla_items:
        return ""
    filas = "".join(f"""<p>· {_t("portal_emp2.compra_uds_de", "Compra")} <b>{r['cantidad_minima']}</b> {_t("portal_emp2.uds_de", "uds. de")}
<code>{_e(r['codigo_disparador'])}</code> {_t("portal_emp2.y_obten", "y obtén")}
{_t("portal_emp2.pct_descuento_texto", "<b>{p}%</b> de descuento", p=r['pct_descuento']) if r['forma_recompensa'] == 'pct_descuento'
 else _t("portal_emp2.precio_especial_texto", "un <b>precio especial de {p} €</b>", p=r['precio_pack_fijo'])} {_t("portal_emp2.en_lbl", "en")}
<code>{_e(r['codigo_recompensa'])}</code> ({_e(r['nombre'])}).</p>""" for r in regla_items)
    return f"""<div class="banner-abandono" style="display:block">
<p style="margin-bottom:8px">💰 {_t("portal_emp2.ahorra_pack", "Ahorra comprando el Pack")}</p>{filas}</div>"""


def pagina_producto_detalle(token, articulo, *, relacionados=None, reglas_bundle=None,
                            no_leidos=0):
    base = f"/portal/empresa/{token}"
    consig = (f'<br><span class="badge badge-ok">{_t("portal_emp2.disponible_consignacion_badge", "Disponible en consignación")}</span>'
             if articulo.get("disponible_consignacion") else "")
    return _layout(articulo["nombre"], f"""
<div class="card"><h1>{_e(articulo['nombre'])}</h1>
<p><span class="badge">{_e(articulo.get('proveedor_nombre') or '')}</span>{consig}</p>
<p>{_t("portal_emp2.precio_lbl", "Precio:")} <b>{articulo['precio_unitario']} €</b> / {_ETIQUETA_UNIDAD.get(articulo['unidad_medida'], articulo['unidad_medida'])}
· MOQ: {articulo['moq']}</p>
{f"<p>{_e(articulo['descripcion'])}</p>" if articulo.get('descripcion') else ''}
<form class="inline" method="post" action="{base}/catalogo/anadir">
<input type="hidden" name="id_catalogo" value="{articulo['id']}">
<input type="number" name="cantidad" min="{articulo['moq']}" value="{articulo['moq']}">
<button type="submit">{_t("portal_emp2.anadir_carrito_btn", "Añadir al carrito")}</button></form>
</div>
{_bloque_bundles_html(reglas_bundle)}
{_bloque_relacionados_html(base, relacionados)}
<p><a href="{base}/catalogo" style="color:var(--ac);font-weight:700">{_t("portal_emp2.volver_catalogo", "← Volver al catálogo")}</a></p>
""", nav=_nav_html(token, "catalogo", no_leidos=no_leidos))


# ── Desde reposición ─────────────────────────────────────────────────────────
def pagina_reposicion(token, propuestas, *, mensaje=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="error">{_e(mensaje)}</p>' if mensaje else ""
    filas = []
    anadido_badge = _t("portal_emp2.anadido_badge", "Añadido")
    anadir_carrito_btn = _t("portal_emp2.anadir_carrito_btn", "Añadir al carrito")
    for p in propuestas:
        anadido = p["estado"] in ("en_carrito", "tramitada")
        accion = (f'<span class="badge badge-ok">{anadido_badge}</span>' if anadido else
                 f'''<form method="post" action="{base}/reposicion/anadir/{p['id']}">
<button type="submit">{anadir_carrito_btn}</button></form>''')
        filas.append(f"""<tr><td>{_e(p['nombre'])}</td><td>{p['stock_actual']}</td>
<td>{p['stock_objetivo']}</td><td><b>{p['cantidad']}</b></td>
<td>{accion}</td></tr>""")
    tabla = (f'<table><tr><th>{_t("portal_emp2.col_articulo", "Artículo")}</th>'
            f'<th>{_t("portal_emp2.col_stock_actual", "Stock actual")}</th>'
            f'<th>{_t("portal_emp2.col_objetivo", "Objetivo")}</th>'
            f'<th>{_t("portal_emp2.col_sugerido", "Sugerido")}</th><th></th></tr>{"".join(filas)}</table>'
            if propuestas else f'<p>{_t("portal_emp2.sin_articulos_bajo_minimos", "No hay artículos bajo mínimos en tu tienda ahora mismo.")}</p>')
    return _layout(_t("portal_emp2.nav_reposicion", "Desde reposición"), f"""
<div class="card">
<h1>{_t("portal_emp2.sugerencias_reposicion_h1", "Sugerencias de reposición — tu tienda")}</h1>
<p>{_t("portal_emp2.sugerencias_reposicion_desc",
      'Solo se muestran artículos de la tienda con la que estás conectado. Los artículos que no '
      'añadas al carrito seguirán apareciendo aquí; los añadidos se marcan "Añadido" pero no '
      "desaparecen hasta que tramites el pedido.")}</p>
{aviso}
{tabla}
</div>""", nav=_nav_html(token, "reposicion", no_leidos=no_leidos))


_ORIGEN_ETIQUETA = {"reposicion": "Desde reposición", "plantilla": "Plantilla"}


def _badge_origen(origen):
    return _t(f"portal_emp2.origen_{origen}", _ORIGEN_ETIQUETA.get(origen, "Catálogo"))


def _barra_progreso_descuento_html(progreso):
    """Termómetro "Añade X más para desbloquear Y% adicional" (bundle o rappel, el que esté más
    cerca — ver `b2b_bundles.progreso_mas_cercano`)."""
    if not progreso:
        return ""
    return f"""<div class="card"><h2>{_t("portal_emp2.proximo_descuento_h2", "Próximo descuento")}</h2>
<p>{_e(progreso['etiqueta'])}</p>
<div class="progreso"><div class="progreso-barra" style="width:{progreso['pct_progreso']}%;background:var(--ac)"></div></div>
</div>"""


def _barra_presupuesto_html(resumen):
    if resumen["limite"] is None:
        return ""
    pct_barra = min(resumen["pct"], 100)
    color = "#F85149" if resumen["excedido"] else "var(--ac)"
    aviso = (f'<p class="error">⚠ {_t("portal_emp2.gasto_proyectado_supera",
            "El gasto proyectado de este mes ({p} €) supera tu límite de {l} €. Puedes seguir "
            "tramitando el pedido si lo necesitas.", p=resumen["proyectado"], l=resumen["limite"])}</p>'
            if resumen["excedido"] else "")
    return f"""<div class="card"><h2>{_t("portal_emp2.gasto_mensual_b2b_h2", "Gasto mensual B2B")}</h2>
<p>{_t("portal_emp2.gasto_validado_mes_lbl", "Gasto validado este mes:")} {resumen['gasto_mes']} € · {_t("portal_emp2.carrito_actual_lbl", "Carrito actual:")} {resumen['total_carrito']} € ·
{_t("portal_emp2.proyectado_lbl", "Proyectado:")} <b>{resumen['proyectado']} €</b> / {resumen['limite']} € ({resumen['pct']}%)</p>
<div class="progreso"><div class="progreso-barra" style="width:{pct_barra}%;background:{color}"></div></div>
{aviso}</div>"""


# ── Carrito ────────────────────────────────────────────────────────────────────
def pagina_carrito(token, lineas, total, *, mensaje=None, error=None, resumen_presupuesto=None,
                   no_leidos=0, consignacion_disponible=False, progreso_descuento=None,
                   bundles_ganados=None):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else (f'<p class="error">{_e(error)}</p>' if error else "")
    quitar_btn = _t("portal_emp2.quitar_btn", "Quitar")
    filas = "".join(f"""<tr><td>{_e(l['nombre'])}
<br><span class="badge">{_badge_origen(l['origen'])}</span></td>
<td>{l['cantidad']} {_ETIQUETA_UNIDAD.get(l['unidad_medida'], l['unidad_medida'] or '')}</td>
<td>{l['precio_unitario']} €</td>
<td>{round(float(l['cantidad'])*float(l['precio_unitario']), 2)} €</td>
<td><form method="post" action="{base}/carrito/quitar/{l['id']}">
<button type="submit" class="btn-danger">{quitar_btn}</button></form></td></tr>""" for l in lineas)
    tabla = (f'<table><tr><th>{_t("portal_emp2.col_articulo", "Artículo")}</th>'
            f'<th>{_t("portal_emp2.col_cantidad", "Cantidad")}</th>'
            f'<th>{_t("portal_emp2.col_precio", "Precio")}</th>'
            f'<th>{_t("portal_emp2.col_subtotal", "Subtotal")}</th>'
            f"<th></th></tr>{filas}</table>") if lineas else f'<p>{_t("portal_emp2.carrito_vacio", "Tu carrito está vacío.")}</p>'
    acciones = ""
    if lineas:
        # Casilla de consignación (Fase 1): el carrito solo puede contener artículos de UN proveedor
        # a la vez (b2b_carrito.anadir lo impone), así que "tramitar en consignación" es una decisión
        # de TODO el pedido, no línea a línea — se ofrece solo si TODOS los artículos del carrito
        # están marcados `disponible_consignacion=1` por ese proveedor (si el carrito mezclara
        # artículos flageados y no flageados, marcar consignación consignaría también los que no
        # corresponde; el backend revalida esto de todos modos, ver `b2b_pedidos.tramitar`).
        casilla_consig = (f"""<label class="inline" style="display:flex;align-items:center;gap:6px">
<input type="checkbox" name="es_consignacion" value="1">
{_t("portal_emp2.tramitar_consignacion_lbl", "Tramitar como stock en consignación (sin coste inmediato — se liquida al consumirse)")}</label>"""
                          if consignacion_disponible else "")
        acciones = f"""<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px">
<form method="post" action="{base}/carrito/tramitar">{casilla_consig}
<button type="submit">{_t("portal_emp2.tramitar_pedidos_btn", "Tramitar pedido(s)")}</button></form>
<form class="inline" method="post" action="{base}/carrito/guardar-plantilla">
<input type="text" name="nombre" placeholder="{_t("portal_emp2.nombre_plantilla_ph", "Nombre de la plantilla")}" required>
<button type="submit" class="btn-ghost">{_t("portal_emp2.guardar_plantilla_btn", "Guardar como plantilla")}</button></form>
</div>"""
    barra = _barra_presupuesto_html(resumen_presupuesto) if resumen_presupuesto else ""
    ganados = [b for b in (bundles_ganados or []) if b.get("cumple") and b.get("descuento_total")]
    bloque_ganados = (f"""<div class="card"><h2 class="ok">✓ {_t("portal_emp2.descuentos_pack_aplicados_h2", "Descuentos de pack aplicados")}</h2>"""
                      + "".join(f"<p>{_e(b['nombre'])}: -{b['descuento_total']} € {_t('portal_emp2.en_lbl', 'en')} "
                                f"<code>{_e(b['codigo_recompensa'])}</code></p>" for b in ganados)
                      + "</div>") if ganados else ""
    bloque_progreso = _barra_progreso_descuento_html(progreso_descuento)
    return _layout(_t("portal_emp2.nav_carrito", "Carrito"), f"""
<div class="card"><h1>{_t("portal_emp2.tu_carrito_h1", "Tu carrito")}</h1>{aviso}{tabla}
<p class="total">{_t("portal_emp2.total_lbl", "Total: {t} €", t=total)}</p>
{acciones}
</div>
{bloque_ganados}
{bloque_progreso}
{barra}""", nav=_nav_html(token, "carrito", no_leidos=no_leidos))


def pagina_pedido_confirmado(token, pedidos, *, no_leidos=0):
    def _fila_pedido_confirmado(p):
        id_html = f"<code>{_e(p['id_tx'])}</code>"
        return _t("portal_emp2.pedido_proveedor_item", "Pedido {id} — proveedor #{s} ({e})",
                  id=id_html, s=_e(p['id_suministrador']), e=p['transicion'].get('hasta', '?'))
    filas = "".join(f"<li>{_fila_pedido_confirmado(p)}</li>" for p in pedidos)
    return _layout(_t("portal_emp2.pedido_tramitado_titulo", "Pedido tramitado"), f"""
<div class="card"><h1 class="ok">✓ {_t("portal_emp2.pedidos_tramitados_h1", "Pedido(s) tramitado(s)")}</h1>
<p>{_t("portal_emp2.pedido_por_proveedor_desc", "Se ha generado un pedido por cada proveedor de tu carrito:")}</p>
<ul>{filas}</ul>
<p><a href="/portal/empresa/{_e(token)}/catalogo" style="color:var(--ac);font-weight:700">
{_t("portal_emp2.seguir_comprando", "Seguir comprando →")}</a> · <a href="/portal/empresa/{_e(token)}/pedidos" style="color:var(--ac);font-weight:700">
{_t("portal_emp2.ver_mis_pedidos", "Ver mis pedidos →")}</a></p>
</div>""", nav=_nav_html(token, "carrito", no_leidos=no_leidos))


# ── Plantillas de aprovisionamiento ───────────────────────────────────────────
def pagina_plantillas(token, plantillas, *, mensaje=None, no_leidos=0):
    base = f"/portal/empresa/{token}"
    aviso = f'<p class="ok">{_e(mensaje)}</p>' if mensaje else ""
    enviar_btn = _t("portal_emp2.enviar_al_carrito_btn", "Enviar al carrito")
    eliminar_btn = _t("portal_emp2.eliminar_btn", "Eliminar")
    filas = "".join(f"""<tr><td>{_e(p['nombre'])}</td><td>{p['n_lineas']}</td>
<td>{p['creado_en']}</td>
<td style="display:flex;gap:8px">
<form method="post" action="{base}/plantillas/{p['id']}/enviar">
<button type="submit">{enviar_btn}</button></form>
<form method="post" action="{base}/plantillas/{p['id']}/eliminar">
<button type="submit" class="btn-danger">{eliminar_btn}</button></form>
</td></tr>""" for p in plantillas)
    tabla = (f'<table><tr><th>{_t("portal_emp2.col_nombre", "Nombre")}</th>'
            f'<th>{_t("portal_emp2.col_articulos", "Artículos")}</th>'
            f'<th>{_t("portal_emp2.col_creada", "Creada")}</th><th></th></tr>{filas}</table>'
            if plantillas else f'<p>{_t("portal_emp2.sin_plantillas",
            "Aún no has guardado ninguna plantilla. Desde el carrito, guarda tus compras "
            "recurrentes con un nombre para reutilizarlas con un clic.")}</p>')
    return _layout(_t("portal_emp2.nav_plantillas", "Plantillas"), f"""
<div class="card"><h1>{_t("portal_emp2.plantillas_aprovisionamiento_h1", "Plantillas de aprovisionamiento")}</h1>{aviso}{tabla}</div>""",
        nav=_nav_html(token, "plantillas", no_leidos=no_leidos))


# ── Mis pedidos + detalle (chat) ───────────────────────────────────────────────
_ETIQUETA_ESTADO = {"BORRADOR": "Borrador", "CONFIRMADA": "Confirmado", "PAGADA": "Pagado",
                    "PREPARANDO": "Preparando", "ENVIADA": "Enviado", "ENTREGADA": "Entregado",
                    "FACTURADA": "Facturado", "DEVUELTA": "Devuelto", "ABONADA": "Abonado",
                    "CANCELADA": "Cancelado", "EXPIRADA": "Expirado"}


def _etiqueta_estado_t(estado):
    return _t(f"portal_emp2.estado_{estado}", _ETIQUETA_ESTADO.get(estado, estado))


def pagina_mis_pedidos(token, pedidos, *, no_leidos=0):
    base = f"/portal/empresa/{token}"
    ver_chat = _t("portal_emp2.ver_chat", "Ver / chat")
    filas = "".join(f"""<tr><td><code>{_e(p['id_tx'])}</code></td>
<td>{_e(_etiqueta_estado_t(p['estado']))}</td>
<td>{p['total']} €</td><td>{p['creada']}</td>
<td><a class="btn" href="{base}/pedido/{p['id_tx']}">{ver_chat}</a></td></tr>""" for p in pedidos)
    tabla = (f'<table><tr><th>{_t("portal_emp2.col_pedido", "Pedido")}</th>'
            f'<th>{_t("portal_emp2.col_estado", "Estado")}</th>'
            f'<th>{_t("portal_emp2.col_total", "Total")}</th>'
            f'<th>{_t("portal_emp2.col_fecha", "Fecha")}</th>'
            f"<th></th></tr>{filas}</table>") if pedidos else f'<p>{_t("portal_emp2.sin_pedidos_b2b", "Aún no has tramitado ningún pedido B2B.")}</p>'
    return _layout(_t("portal_emp2.mis_pedidos_titulo", "Mis pedidos"),
                   f'<div class="card"><h1>{_t("portal_emp2.mis_pedidos_h1", "Mis pedidos")}</h1>{tabla}</div>',
        nav=_nav_html(token, "pedidos", no_leidos=no_leidos))


def _burbujas_chat_html(mensajes, lado):
    if not mensajes:
        return f'<p>{_t("portal_emp2.sin_mensajes", "Aún no hay mensajes en este pedido.")}</p>'
    burbujas = []
    for m in mensajes:
        propio = m["autor_tipo"] == lado
        clase = "msg-propio" if propio else "msg-otro"
        burbujas.append(f"""<div class="msg {clase}">
<div class="msg-autor">{_e(m.get('autor_nombre') or m['autor_tipo'].capitalize())}</div>
<div class="msg-cuerpo">{_e(m['cuerpo'])}</div>
<div class="msg-fecha">{m['creado_en']}</div></div>""")
    return f'<div class="chat">{"".join(burbujas)}</div>'


_ETIQUETA_ESTADO_RMA = {"pendiente_aprobacion": "Pendiente de aprobación", "aprobada": "Aprobada",
                        "rechazada": "Rechazada", "registrada": "Registrada"}


def _rma_html(token, tx, lineas, rmas):
    """Sección "Solicitar Devolución (RMA)" del detalle de pedido — SOLO visible para pedidos
    ENTREGADA (autoservicio del comprador, `services.compras.b2b_disputas.
    solicitar_devolucion_autoservicio`): selecciona líneas+cantidad, motivo y fotos de evidencia
    (opcional); el RMA nace 'pendiente_aprobacion' — SIN efecto de stock/reembolso todavía, eso
    queda para cuando el proveedor lo apruebe o rechace desde su propio portal."""
    base = f"/portal/empresa/{token}/pedido/{tx['id_tx']}"
    titulo_rma = _t("portal_emp2.solicitar_devolucion_rma_h2", "Solicitar Devolución (RMA)")
    filas_sel = "".join(f"""<tr><td><input type="checkbox" name="linea_{l['id']}" value="1"></td>
<td>{_e(l.get('codigo_articulo'))} · {_e(l['nombre'])}</td>
<td><input type="number" name="cant_{l['id']}" min="1" max="{l['cantidad']}" value="{l['cantidad']}"
style="width:80px"></td><td>{l['cantidad']}</td></tr>""" for l in lineas)
    historial = ""
    if rmas:
        filas_h = "".join(f"""<tr><td>{r['id_devolucion']}</td><td>{_e(r.get('motivo') or '—')}</td>
<td><span class="badge">{_e(_t(f"portal_emp2.estado_rma_{r['estado']}", _ETIQUETA_ESTADO_RMA.get(r['estado'], r['estado'])))}</span></td>
<td>{_e(r.get('motivo_rechazo') or '—')}</td><td>{_e(r['fecha'])}</td></tr>""" for r in rmas)
        historial = (f"""<h3 style="color:#8B949E;font-size:14px;margin-top:16px">{_t("portal_emp2.rma_ya_solicitados_h3", "RMA ya solicitados sobre este pedido")}</h3>
<table><tr><th>ID</th><th>{_t("portal_emp2.col_motivo", "Motivo")}</th><th>{_t("portal_emp2.col_estado", "Estado")}</th><th>{_t("portal_emp2.col_alegacion_proveedor", "Alegación proveedor")}</th>
<th>{_t("portal_emp2.col_fecha", "Fecha")}</th></tr>{filas_h}</table>""")
    return f"""<div class="card"><h2>{titulo_rma}</h2>
<p>{_t("portal_emp2.rma_desc",
      "Selecciona las líneas y cantidades a devolver. La devolución queda pendiente de "
      "aprobación del proveedor — el stock y, si procede, el reembolso solo se aplican "
      "cuando la apruebe.")}</p>
<form method="post" action="{base}/rma" enctype="multipart/form-data">
<table><tr><th></th><th>{_t("portal_emp2.col_articulo", "Artículo")}</th><th>{_t("portal_emp2.col_cantidad_devolver", "Cantidad a devolver")}</th><th>{_t("portal_emp2.col_cantidad_pedido", "Cantidad del pedido")}</th></tr>
{filas_sel}</table>
<label>{_t("portal_emp2.motivo_lbl", "Motivo")}</label>
<textarea name="motivo" rows="2" placeholder="{_t("portal_emp2.motivo_rma_ph", "Producto dañado, no corresponde al pedido…")}" required></textarea>
<label>{_t("portal_emp2.fotos_evidencia_lbl", "Fotos de evidencia (opcional, máx. 10 archivos / 25 MB en total)")}</label>
<input type="file" name="fotos" multiple accept="image/*,.pdf">
<p><button type="submit">{titulo_rma}</button></p>
</form>{historial}</div>"""


def pagina_pedido_detalle(token, tx, lineas, mensajes, *, lado="empresa", no_leidos=0,
                          tiene_albaran=False, rmas=None):
    base = f"/portal/empresa/{token}"
    filas_lineas = "".join(f"""<tr><td>{_e(l['nombre'])}</td><td>{l['cantidad']}</td>
<td>{l['precio_unitario']} €</td>
<td>{_e(l.get('lote') or '—')}</td><td>{_e(l.get('fecha_caducidad') or '—')}</td></tr>"""
                           for l in lineas)
    rma_html = _rma_html(token, tx, lineas, rmas or []) if tx.get("estado") == "ENTREGADA" else ""
    chat = _burbujas_chat_html(mensajes, lado)
    albaran_html = (f'<p><a href="{base}/pedido/{tx["id_tx"]}/albaran">📄 {_t("portal_emp2.descargar_albaran", "Descargar albarán")}</a></p>'
                   if tiene_albaran else "")
    # Punto 3 bis / rearquitectura del flujo de recepción B2B: la recepción física de stock ya NO se
    # confirma desde aquí — se hace desde la pestaña "Recepciones" de Logística (escritorio), que
    # unifica el pedido B2B con los traspasos internos bajo el mismo escaneo (`gui.recepcion_pale`,
    # `db.logistica.registrar_documento_b2b` + `b2b_pedidos.recibir_mercancia`). El Portal Empresa
    # SOLO informa del estado (visibilidad/seguimiento), como pidió expresamente el rediseño — nunca
    # muta stock desde el navegador.
    # Landed Cost (Fase B): enlace a Gestión para registrar/prorratear costes extra (transporte,
    # aduanas, seguro…) sobre este pedido — vive en `portal_empresa_gestion.py` (mismo patrón que
    # la recepción de compra), no aquí (este portal solo informa, nunca muta stock/costes).
    _base_gestion = f"/portal/empresa/{token}/gestion/b2b/{tx['id_tx']}"
    costes_extra_lbl = _t("portal_emp2.costes_extra_landed", "💰 Costes extra / coste landed")
    recepcion_html = ""
    if tx.get("estado") not in ("BORRADOR", "CANCELADA"):
        if tx.get("stock_recibido_en"):
            recepcion_html = (f'<p class="ok">✅ {_t("portal_emp2.mercancia_recibida", "Mercancía recibida en almacén ({a}).", a=_e(tx["stock_recibido_en"]))}</p>'
                              f'<p><a href="{_base_gestion}">{costes_extra_lbl}</a></p>')
        else:
            recepcion_html = (f'<p>📦 {_t("portal_emp2.pendiente_recepcion_almacen", "Pendiente de recepción en almacén (se recibe desde Logística, no desde este portal).")}</p>'
                              f'<p><a href="{_base_gestion}">{costes_extra_lbl}</a></p>')
    return _layout(_t("portal_emp2.pedido_titulo", "Pedido {ref}", ref=tx['id_tx'][:8]), f"""
<div class="card"><h1>{_t("portal_emp2.pedido_h1", "Pedido")} <code>{_e(tx['id_tx'])}</code></h1>
<p>{_t("portal_emp2.estado_lbl", "Estado:")} <span class="badge">{_e(_etiqueta_estado_t(tx['estado']))}</span> ·
{_t("portal_emp2.total_lbl2", "Total:")} <b>{tx['total']} €</b> · {_t("portal_emp2.fecha_lbl", "Fecha:")} {tx['creada']}</p>
{albaran_html}
{recepcion_html}
<table><tr><th>{_t("portal_emp2.col_articulo", "Artículo")}</th><th>{_t("portal_emp2.col_cantidad", "Cantidad")}</th><th>{_t("portal_emp2.col_precio", "Precio")}</th><th>{_t("portal_emp2.col_lote", "Lote")}</th>
<th>{_t("portal_emp2.col_caducidad", "Caducidad")}</th></tr>{filas_lineas}</table>
</div>
{rma_html}
<div class="card"><h2>{_t("portal_emp2.comunicacion_pedido_h2", "Comunicación sobre este pedido")}</h2>
{chat}
<form method="post" action="{base}/pedido/{tx['id_tx']}/mensaje" style="margin-top:12px">
<textarea name="cuerpo" rows="3" placeholder="{_t("portal_emp2.escribe_mensaje_ph", "Escribe un mensaje…")}" required></textarea>
<button type="submit" style="margin-top:8px">{_t("portal_emp2.enviar_btn", "Enviar")}</button>
</form></div>""", nav=_nav_html(token, "pedidos", no_leidos=no_leidos))


# ── Blueprint Flask (import perezoso) ────────────────────────────────────────
def crear_blueprint():
    from flask import Blueprint, redirect, request

    bp = Blueprint("portal_empresa_b2b", __name__, url_prefix="/portal/empresa")
    # Registrado SOLO aquí (no también en `portal_empresa_gestion.py`, que comparte el mismo
    # `url_prefix` y SIEMPRE se registra junto a este blueprint): evita una colisión de ruta por
    # registrar el mismo "/portal/empresa/idioma" dos veces en la misma app Flask.
    registrar_selector_idioma(bp, "")

    def _sesion_o_error(token):
        from src.services.compras import b2b_sesion_empresa as SES
        ses = SES.resolver_sesion(token)
        if not ses:
            return None, (_pagina_error(_t("portal_emp2.sesion_no_valida_titulo", "Sesión no válida"),
                          _t("portal_emp2.sesion_caducada_msg",
                             "Tu sesión ha caducado. Vuelve a entrar desde Smart Manager.")), 401)
        # `g.id_empresa`: resuelto UNA vez por request, para que `_layout()` pueda temizar cada
        # página con el color de esta empresa sin enhebrar `id_empresa` por cada punto de llamada
        # (decenas, repartidas entre este fichero y `portal_empresa_gestion.py`).
        try:
            from flask import g
            g.id_empresa = ses.get("id_empresa")
        except Exception:
            pass
        return ses, None

    def _no_leidos(ses):
        try:
            from src.services.compras import b2b_chat as CHAT
            return CHAT.no_leidos_totales_empresa(ses["id_empresa"])
        except Exception:
            return 0

    @bp.get("/<token>/dashboard")
    def dashboard(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_presupuesto as PRES, \
            b2b_carrito_abandono as ABANDONO
        abandonos = ABANDONO.listar_para_empresa(ses["id_empresa"])
        return pagina_dashboard(token, ses, n_carrito=len(CART.listar(token)),
                               limite_actual=PRES.obtener_limite(ses["id_empresa"]),
                               no_leidos=_no_leidos(ses),
                               abandono=abandonos[0] if abandonos else None)

    @bp.get("/<token>/consignacion")
    def consignacion(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT s.*, sm.razon_social FROM b2b_consignacion_saldo s "
                "LEFT JOIN suministradores sm ON sm.id=s.id_suministrador "
                "WHERE s.id_empresa=%s ORDER BY sm.razon_social, s.codigo_articulo", (ses["id_empresa"],))
            cols = [d[0] for d in cur.description]
            saldos = [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cur.fetchall()]
        por_proveedor = {}
        for s in saldos:
            nombre = s.get("razon_social") or f"Proveedor #{s['id_suministrador']}"
            por_proveedor.setdefault(nombre, []).append(s)
        bloques = list(por_proveedor.items())
        return pagina_consignacion_empresa(token, bloques, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/dashboard/limite-gasto")
    def dashboard_limite_gasto(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_presupuesto as PRES
        PRES.guardar_limite(ses["id_empresa"], request.form.get("limite", ""))
        return redirect(f"/portal/empresa/{token}/dashboard")

    @bp.post("/<token>/carrito/reanudar/<token_viejo>")
    def carrito_reanudar(token, token_viejo):
        """"Reanudar Pedido" del aviso de carrito abandonado: transfiere las líneas del carrito viejo
        (bajo una sesión ya caducada, ver `b2b_carrito.reasignar_token`) a la sesión ACTUAL y marca el
        registro de abandono como resuelto."""
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_carrito_abandono as ABANDONO
        abandono = ABANDONO.obtener(token_viejo)
        # Nunca se confía en el token de la URL por sí solo: solo se transfiere si el carrito
        # abandonado es REALMENTE de esta empresa (un token de otra empresa no puede moverse aquí).
        if abandono and str(abandono.get("id_empresa")) == str(ses["id_empresa"]):
            CART.reasignar_token(token_viejo, token)
            ABANDONO.marcar_resuelto(token_viejo)
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.get("/<token>/catalogo")
    def catalogo(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as CAT, sectores
        texto = request.args.get("q", "").strip()
        sector_ids = sectores.compatibles_de(ses["sector_id"])
        arts = CAT.buscar_para_empresa(sector_ids, texto=texto or None)
        for a in arts:
            CAT.registrar_evento(a["id"], ses["id_empresa"], "vista")
        mensaje = "Catálogo actualizado." if request.args.get("actualizar") else None
        return pagina_catalogo(token, arts, texto=texto, mensaje=mensaje, no_leidos=_no_leidos(ses))

    @bp.get("/<token>/catalogo/<int:id_catalogo>")
    def catalogo_producto(token, id_catalogo):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as CAT, b2b_bundles as BUN, sectores
        arts = CAT.buscar_para_empresa(sectores.compatibles_de(ses["sector_id"]))
        articulo = next((a for a in arts if str(a["id"]) == str(id_catalogo)), None)
        if not articulo:
            return _pagina_error(_t("portal_emp2.articulo_no_encontrado_titulo", "Artículo no encontrado"),
                                 _t("portal_emp2.articulo_no_disponible_sector",
                                   "Ese artículo no existe o no está disponible para tu sector.")), 404
        CAT.registrar_evento(articulo["id"], ses["id_empresa"], "vista")
        relacionados = CAT.productos_relacionados(articulo["codigo"], ses["id_empresa"])
        reglas = BUN.reglas_aplicables_a_producto(articulo["codigo"], ses["id_empresa"],
                                                  id_suministrador=articulo["id_suministrador"])
        return pagina_producto_detalle(token, articulo, relacionados=relacionados,
                                       reglas_bundle=reglas, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/catalogo/anadir")
    def catalogo_anadir(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_catalogo as CAT, b2b_carrito as CART, sectores
        id_catalogo = request.form.get("id_catalogo")
        cantidad = request.form.get("cantidad", 1)
        arts = CAT.buscar_para_empresa(sectores.compatibles_de(ses["sector_id"]))
        art = next((a for a in arts if str(a["id"]) == str(id_catalogo)), None)
        if not art:
            return redirect(f"/portal/empresa/{token}/catalogo")
        try:
            cantidad = int(cantidad)
        except (TypeError, ValueError):
            cantidad = art["moq"]
        if cantidad < art["moq"]:
            return pagina_catalogo(token, arts, mensaje=None, no_leidos=_no_leidos(ses)), 400

        # Detección de duplicados ANTES de tramitar el pedido (petición explícita): coincidencia
        # EXACTA simultánea de Nombre+Talla+Marca+Color (los que el proveedor haya rellenado) contra
        # el catálogo interno de la empresa — evita comprar como "nuevo" algo que ya se tiene con
        # otro código, y ofrece crear la equivalencia en vez de arriesgar un duplicado. Se salta si
        # el operario ya confirmó explícitamente que es un artículo DISTINTO (`confirmado=1`).
        if request.form.get("confirmado") != "1":
            from src.db import articulos as A
            dup = A.detectar_posible_duplicado(art["nombre"], talla=art.get("talla"),
                                               marca=art.get("marca"), color=art.get("color"),
                                               id_empresa=ses["id_empresa"])
            if dup:
                return pagina_confirmar_duplicado(token, art, dup, id_catalogo, cantidad)

        CAT.registrar_evento(art["id"], ses["id_empresa"], "click")
        r = CART.anadir(token, id_suministrador=art["id_suministrador"], codigo=art["codigo"],
                        nombre=art["nombre"], unidad_medida=art["unidad_medida"], cantidad=cantidad,
                        precio_unitario=CAT.precio_para_cantidad(art, cantidad), origen="catalogo")
        if not r.get("ok"):
            return pagina_catalogo(token, arts, mensaje=r.get("mensaje", "No se pudo añadir el "
                                   "artículo."), no_leidos=_no_leidos(ses)), 400
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.get("/<token>/reposicion")
    def reposicion(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import reabastecimiento as R
        R.generar_propuestas_tienda(ses["id_tienda"], ses["id_empresa"])
        props = R.listar_propuestas_tienda(ses["id_tienda"],
                                           estados=("pendiente", "en_carrito"),
                                           id_empresa=ses["id_empresa"])
        return pagina_reposicion(token, props, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/reposicion/anadir/<int:id_propuesta>")
    def reposicion_anadir(token, id_propuesta):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.db import reabastecimiento as R
        from src.services.compras import b2b_carrito as CART, b2b_catalogo as CAT, sectores
        prop = R.obtener_propuesta(id_propuesta)
        if not prop:
            return redirect(f"/portal/empresa/{token}/reposicion")
        # La sugerencia es de STOCK (umbral/objetivo), no de catálogo B2B: hace falta localizar QUÉ
        # proveedor del catálogo ofrece ese código antes de poder tramitarlo como pedido. Si hay
        # varios, se toma el más barato (criterio simple y explícito, no oculto).
        candidatos = [a for a in CAT.buscar_para_empresa(sectores.compatibles_de(ses["sector_id"]))
                     if a["codigo"] == prop["codigo"]]
        if not candidatos:
            props = R.listar_propuestas_tienda(ses["id_tienda"], estados=("pendiente", "en_carrito"),
                                               id_empresa=ses["id_empresa"])
            return pagina_reposicion(token, props, no_leidos=_no_leidos(ses)), 400
        mejor = min(candidatos, key=lambda a: float(a["precio_unitario"]))
        cantidad = max(prop["cantidad"], mejor["moq"])
        r = CART.anadir(token, id_suministrador=mejor["id_suministrador"], codigo=prop["codigo"],
                        nombre=prop["nombre"], unidad_medida=mejor["unidad_medida"], cantidad=cantidad,
                        precio_unitario=CAT.precio_para_cantidad(mejor, cantidad), origen="reposicion",
                        id_reab_propuesta=id_propuesta)
        if not r.get("ok"):
            props = R.listar_propuestas_tienda(ses["id_tienda"], estados=("pendiente", "en_carrito"),
                                               id_empresa=ses["id_empresa"])
            return pagina_reposicion(token, props, mensaje=r.get("mensaje", "No se pudo añadir el "
                                     "artículo."), no_leidos=_no_leidos(ses)), 400
        return redirect(f"/portal/empresa/{token}/reposicion")

    @bp.get("/<token>/carrito")
    def carrito(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_catalogo as CAT, \
            b2b_presupuesto as PRES, b2b_bundles as BUN
        lineas = CART.listar(token)
        total = CART.total(token)
        resumen = PRES.resumen_presupuesto(ses["id_empresa"], total_carrito=total)
        # Consignación (Fase 1): solo se ofrece la casilla si TODOS los artículos del carrito están
        # flageados `disponible_consignacion=1` por su proveedor (el carrito ya solo admite un
        # proveedor a la vez, ver `b2b_carrito.anadir`).
        consig_disp = False
        bundles_ganados = None
        progreso = None
        if lineas:
            id_sum = lineas[0]["id_suministrador"]
            codigos = {l["codigo"] for l in lineas}
            flageados = CAT.articulos_disponibles_consignacion(id_sum, list(codigos))
            consig_disp = codigos.issubset(flageados)
            reglas = BUN.listar_reglas(id_sum, solo_activas=True)
            bundles_ganados = BUN.calcular_descuento_bundle(lineas, reglas)
            progreso = BUN.progreso_mas_cercano(ses["id_empresa"], lineas)
        return pagina_carrito(token, lineas, total, resumen_presupuesto=resumen,
                              no_leidos=_no_leidos(ses), consignacion_disponible=consig_disp,
                              progreso_descuento=progreso, bundles_ganados=bundles_ganados)

    @bp.post("/<token>/carrito/quitar/<int:id_linea>")
    def carrito_quitar(token, id_linea):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART
        CART.quitar_linea(token, id_linea)
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.post("/<token>/carrito/guardar-plantilla")
    def carrito_guardar_plantilla(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_presupuesto as PRES, b2b_plantillas as PLANT
        r = PLANT.guardar_desde_carrito(ses["id_empresa"], request.form.get("nombre", ""), token)
        total = CART.total(token)
        resumen = PRES.resumen_presupuesto(ses["id_empresa"], total_carrito=total)
        if not r.get("ok"):
            return pagina_carrito(token, CART.listar(token), total, error=r.get("error"),
                                  resumen_presupuesto=resumen, no_leidos=_no_leidos(ses)), 400
        return pagina_carrito(token, CART.listar(token), total,
                              mensaje=_t("portal_emp2.plantilla_guardada", "Plantilla guardada."),
                              resumen_presupuesto=resumen, no_leidos=_no_leidos(ses))

    @bp.post("/<token>/carrito/tramitar")
    def carrito_tramitar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_carrito as CART, b2b_catalogo as CAT, b2b_pedidos as PED, \
            b2b_presupuesto as PRES
        # Casilla de consignación (Fase 1 — antes "plumbing" muerto desde la UI, ver `pagina_carrito`):
        # se lee el campo del formulario tal cual, pero NUNCA se confía en él por sí solo — `PED.
        # tramitar` revalida contra `b2b_catalogo.disponible_consignacion` antes de aplicar el flag
        # (un cliente API o un formulario manipulado no puede consignar un artículo no flageado).
        es_consignacion = request.form.get("es_consignacion") in ("1", "true", "on")
        r = PED.tramitar(token, es_consignacion=es_consignacion)
        if not r.get("ok"):
            lineas = CART.listar(token)
            total = CART.total(token)
            resumen = PRES.resumen_presupuesto(ses["id_empresa"], total_carrito=total)
            consig_disp = False
            if lineas:
                id_sum = lineas[0]["id_suministrador"]
                codigos = {l["codigo"] for l in lineas}
                consig_disp = codigos.issubset(
                    CAT.articulos_disponibles_consignacion(id_sum, list(codigos)))
            return pagina_carrito(token, lineas, total, error=r.get("error"),
                                  resumen_presupuesto=resumen, no_leidos=_no_leidos(ses),
                                  consignacion_disponible=consig_disp), 400
        return pagina_pedido_confirmado(token, r["pedidos"], no_leidos=_no_leidos(ses))

    @bp.get("/<token>/plantillas")
    def plantillas(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_plantillas as PLANT
        return pagina_plantillas(token, PLANT.listar(ses["id_empresa"]), no_leidos=_no_leidos(ses))

    @bp.post("/<token>/plantillas/<int:id_plantilla>/enviar")
    def plantillas_enviar(token, id_plantilla):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_plantillas as PLANT
        r = PLANT.enviar_a_carrito(token, ses["id_empresa"], id_plantilla)
        if r.get("ok") and r.get("omitidas"):
            mensaje = (f"{r['anadidas']} artículo(s) añadidos al carrito. Omitidos (ya no disponibles "
                      f"en el catálogo): {', '.join(r['omitidas'])}.")
            return pagina_plantillas(token, PLANT.listar(ses["id_empresa"]), mensaje=mensaje,
                                     no_leidos=_no_leidos(ses))
        return redirect(f"/portal/empresa/{token}/carrito")

    @bp.post("/<token>/plantillas/<int:id_plantilla>/eliminar")
    def plantillas_eliminar(token, id_plantilla):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.compras import b2b_plantillas as PLANT
        PLANT.eliminar(ses["id_empresa"], id_plantilla)
        return redirect(f"/portal/empresa/{token}/plantillas")

    @bp.get("/<token>/pedidos")
    def pedidos(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        peds = TX.listar(id_empresa=ses["id_empresa"], id_tienda=None, origen="b2b")
        return pagina_mis_pedidos(token, peds, no_leidos=_no_leidos(ses))

    @bp.get("/<token>/pedido/<id_tx>")
    def pedido_detalle(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        from src.services.compras import b2b_chat as CHAT
        tx = TX.obtener(id_tx, id_empresa=ses["id_empresa"])
        if not tx:
            return _pagina_error(_t("portal_emp2.pedido_no_encontrado_titulo", "Pedido no encontrado"),
                                 _t("portal_emp2.pedido_no_tuyo", "Ese pedido no existe o no es tuyo.")), 404
        CHAT.marcar_leido(id_tx, "empresa")
        from src.db.documentos import obtener_por_referencia
        from src.db import compras as C
        doc = obtener_por_referencia(f"B2B_TX:{id_tx}", id_empresa=ses["id_empresa"])
        rmas = C.listar_devoluciones_de_tx(id_tx, id_empresa=ses["id_empresa"])
        return pagina_pedido_detalle(token, tx, tx["lineas"], CHAT.listar_mensajes(id_tx),
                                     lado="empresa", no_leidos=_no_leidos(ses),
                                     tiene_albaran=bool(doc), rmas=rmas)

    @bp.post("/<token>/pedido/<id_tx>/rma")
    def pedido_rma_solicitar(token, id_tx):
        """Autoservicio del comprador (RMA): solo para pedidos ENTREGADA — ver `_rma_html`. Crea la
        devolución en 'pendiente_aprobacion' vía `b2b_disputas.solicitar_devolucion_autoservicio`;
        el efecto de stock/reembolso queda diferido a la aprobación del proveedor."""
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        tx = TX.obtener(id_tx, id_empresa=ses["id_empresa"])
        if not tx:
            return _pagina_error(_t("portal_emp2.pedido_no_encontrado_titulo", "Pedido no encontrado"),
                                 _t("portal_emp2.pedido_no_tuyo", "Ese pedido no existe o no es tuyo.")), 404
        if tx.get("estado") != "ENTREGADA":
            return _pagina_error(_t("portal_emp2.no_disponible_titulo", "No disponible"),
                                 _t("portal_emp2.rma_solo_entregado",
                                   "Solo se puede solicitar un RMA sobre un pedido ya entregado.")), 400

        lineas_rma = []
        for ln in tx.get("lineas", []):
            if request.form.get(f"linea_{ln['id']}") != "1":
                continue
            try:
                cant = int(request.form.get(f"cant_{ln['id']}") or 0)
            except ValueError:
                cant = 0
            cant = max(0, min(cant, int(ln.get("cantidad") or 0)))
            if cant <= 0:
                continue
            lineas_rma.append({"codigo": ln.get("codigo_articulo"), "cantidad": cant,
                               "lote": ln.get("lote"), "precio_unitario": ln.get("precio_unitario")})
        motivo = (request.form.get("motivo") or "").strip()
        if not lineas_rma or not motivo:
            return _pagina_error(_t("portal_emp2.datos_incompletos_titulo", "Datos incompletos"),
                                 _t("portal_emp2.rma_datos_incompletos",
                                   "Selecciona al menos una línea con cantidad y describe el motivo.")), 400

        fotos = request.files.getlist("fotos") if request.files else []
        fotos = [f for f in fotos if f and f.filename]
        from src.services.compras import b2b_disputas as DISP
        if len(fotos) > DISP.MAX_ADJUNTOS_RMA:
            return _pagina_error(_t("portal_emp2.demasiados_archivos_titulo", "Demasiados archivos"),
                                 _t("portal_emp2.max_archivos_solicitud",
                                   "Máximo {n} archivos por solicitud.", n=DISP.MAX_ADJUNTOS_RMA)), 400
        total_bytes = 0
        for f in fotos:
            f.stream.seek(0, 2)
            total_bytes += f.stream.tell()
            f.stream.seek(0)
        if total_bytes > DISP.MAX_BYTES_ADJUNTOS_RMA:
            return _pagina_error(_t("portal_emp2.archivos_grandes_titulo", "Archivos demasiado grandes"),
                                 _t("portal_emp2.adjuntos_superan_25mb",
                                   "Los adjuntos superan los 25 MB en total.")), 400

        r = DISP.solicitar_devolucion_autoservicio(id_tx, lineas_rma, motivo,
                                                   usuario=ses.get("nombre_usuario"), fotos=fotos)
        if not r.get("ok"):
            return _pagina_error(_t("portal_emp2.rma_no_solicitado_titulo", "No se pudo solicitar el RMA"),
                                 r.get("error") or ""), 400
        return redirect(f"/portal/empresa/{token}/pedido/{id_tx}")

    # NOTA (rearquitectura del flujo de recepción B2B): las rutas GET/POST
    # "/pedido/<id_tx>/recepcion" que confirmaban la recepción física de mercancía DESDE EL PORTAL se
    # han retirado — esa acción (mutación de stock) ahora vive exclusivamente en la pestaña
    # "Recepciones" de Logística (escritorio), unificada con los traspasos internos. El portal solo
    # muestra el estado (ver `recepcion_html` en `pagina_pedido_detalle`), nunca lo cambia.

    @bp.get("/<token>/pedido/<id_tx>/albaran")
    def pedido_albaran(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        import os
        from flask import send_file
        from src.db.documentos import obtener_por_referencia
        doc = obtener_por_referencia(f"B2B_TX:{id_tx}", id_empresa=ses["id_empresa"])
        if not doc or not doc.get("ruta") or not os.path.exists(doc["ruta"]):
            return _pagina_error(_t("portal_emp2.albaran_no_encontrado_titulo", "Albarán no encontrado"),
                                _t("portal_emp2.albaran_no_pertenece",
                                  "Ese albarán no existe o no pertenece a este pedido.")), 404
        return send_file(doc["ruta"])

    @bp.post("/<token>/pedido/<id_tx>/mensaje")
    def pedido_mensaje(token, id_tx):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.services.comercio_digital import transacciones as TX
        from src.services.compras import b2b_chat as CHAT
        tx = TX.obtener(id_tx, id_empresa=ses["id_empresa"])
        if not tx:
            return _pagina_error(_t("portal_emp2.pedido_no_encontrado_titulo", "Pedido no encontrado"),
                                 _t("portal_emp2.pedido_no_tuyo", "Ese pedido no existe o no es tuyo.")), 404
        CHAT.enviar_mensaje(id_tx, "empresa", ses.get("nombre_usuario"), request.form.get("cuerpo", ""))
        return redirect(f"/portal/empresa/{token}/pedido/{id_tx}")

    @bp.get("/<token>/colores")
    def colores(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from src.backend import portal_theming as _tema
        contenido = _tema.pagina_colores_html(
            titulo="Colores del portal", accion_guardar=f"/portal/empresa/{token}/colores/guardar",
            accion_volver=f"/portal/empresa/{token}/dashboard",
            accion_restablecer=f"/portal/empresa/{token}/colores/restablecer",
            id_empresa=ses["id_empresa"], mensaje=request.args.get("mensaje"),
            error=request.args.get("error"))
        return _layout("Personalización", contenido, nav=_nav_html(token, "colores"), id_empresa=ses["id_empresa"])

    @bp.post("/<token>/colores/guardar")
    def colores_guardar(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from urllib.parse import quote
        from src.backend import portal_theming as _tema
        res = _tema.guardar_tema(ses["id_empresa"],
                                 color_primario=request.form.get("color_primario"),
                                 color_secundario=request.form.get("color_secundario"),
                                 color_terciario=request.form.get("color_terciario"))
        url = f"/portal/empresa/{token}/colores"
        if res["ok"]:
            url += f"?mensaje={quote('Colores guardados.')}"
        else:
            url += f"?error={quote('No se pudieron guardar los colores.')}"
        return redirect(url)

    @bp.post("/<token>/colores/restablecer")
    def colores_restablecer(token):
        ses, err = _sesion_o_error(token)
        if err:
            return err
        from urllib.parse import quote
        from src.backend import portal_theming as _tema
        ok = _tema.restablecer_tema(ses["id_empresa"])
        url = f"/portal/empresa/{token}/colores"
        url += f"?mensaje={quote('Colores restablecidos.')}" if ok else f"?error={quote('No se pudo restablecer.')}"
        return redirect(url)

    return bp
