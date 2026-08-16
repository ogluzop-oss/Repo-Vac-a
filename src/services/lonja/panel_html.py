"""Panel web del VENDEDOR de la Lonja (una sola página, autocontenida).

Es el front-end que el vendedor abre con su token el día del despliegue. No añade lógica: consume los
endpoints REST de `lonja_vendedor` (`/api/v1/lonja-vendedor/*`) con la cabecera `X-Lonja-Token`. Permite
definir su DIVISA de referencia y publicar/retirar LISTADOS (precio de compra directa + puja mínima +
cantidad). Se sirve desde el propio blueprint de la API, así funciona en local y quedará accesible por HTTP
cuando el backend se despliegue.
"""

_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portal del Vendedor · Lonja</title>
<style>
 :root{--bg:#0D1117;--pan:#161B22;--cy:#00FFC6;--tx:#E6EDF3;--dim:#8B949E;--bd:#30363D;--rojo:#F85149}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--tx);font-family:Segoe UI,Arial,sans-serif}
 header{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--bd)}
 header h1{font-size:18px;margin:0;color:var(--cy)} .who{color:var(--dim);font-size:12px}
 .wrap{max-width:960px;margin:0 auto;padding:18px}
 input,select,button,textarea{font:inherit;border-radius:8px;border:2px solid var(--bd);background:#0D1117;color:var(--tx);padding:8px 10px}
 input:focus,select:focus{border-color:var(--cy);outline:none}
 button{background:#161B22;color:var(--cy);border-color:var(--cy);font-weight:700;cursor:pointer}
 button:hover{background:var(--cy);color:#0D1117} button.rojo{color:var(--rojo);border-color:var(--rojo)}
 button.rojo:hover{background:var(--rojo);color:#0D1117}
 table{width:100%;border-collapse:collapse;border:2px solid var(--cy);border-radius:10px;overflow:hidden;margin-top:12px}
 th,td{padding:8px;border-bottom:1px solid var(--bd);text-align:left;font-size:13px} th{color:var(--cy);font-size:11px}
 .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}
 .card{background:var(--pan);border:1px solid var(--bd);border-radius:12px;padding:16px;margin-top:12px}
 .hide{display:none} .msg{padding:8px 10px;border-radius:8px;margin:8px 0;font-size:13px}
 .ok{background:#00FFC622;color:var(--cy)} .err{background:#F8514922;color:var(--rojo)}
 label.chk{display:inline-flex;gap:6px;align-items:center;font-size:13px;color:var(--dim)}
</style></head><body>
<header><h1>🏷️ Portal del Vendedor · Lonja</h1><span class="who" id="who"></span></header>
<div class="wrap">
 <div id="login" class="card">
   <p>Introduce tu <b>token de vendedor</b> (lo recibiste al ser dado de alta en el mercado):</p>
   <div class="row"><input id="tok" style="flex:1" placeholder="Token de vendedor"><button onclick="entrar()">Entrar</button></div>
   <div id="loginmsg"></div>
 </div>
 <div id="app" class="hide">
   <div class="card">
     <h3>Mi divisa de referencia</h3>
     <div class="row">
       <select id="divisa"><option>EUR</option><option>USD</option><option>GBP</option><option>MXN</option><option>ARS</option><option>BRL</option><option>COP</option><option>CLP</option></select>
       <button onclick="guardarDivisa()">Guardar divisa</button>
       <span class="who">Con esta moneda publicas tus precios y pujas mínimas.</span>
     </div>
   </div>
   <div class="card">
     <h3>Publicar artículo en el mercado</h3>
     <div class="row">
       <input id="p_cod" placeholder="Código" size="10">
       <input id="p_precio" placeholder="Precio (compra directa)" size="10">
       <input id="p_min" placeholder="Puja mínima" size="8">
       <input id="p_cant" placeholder="Cantidad" size="6" value="1">
       <select id="p_uni"><option>unidad</option><option>caja</option><option>pale</option><option>kg</option></select>
     </div>
     <div class="row">
       <input id="p_dur" placeholder="Duración subasta (h)" size="8" value="24">
       <input id="p_res" placeholder="Precio de reserva (opc.)" size="10">
       <input id="p_inc" placeholder="Incremento mínimo" size="8" value="0">
     </div>
     <div class="row">
       <label class="chk"><input type="checkbox" id="p_cd" checked> Permitir compra directa</label>
       <label class="chk"><input type="checkbox" id="p_pj" checked> Permitir pujas</label>
       <button onclick="publicar()">Publicar</button>
       <button class="rojo" style="margin-left:auto" onclick="salir()">Salir</button>
     </div>
   </div>
   <div id="out"></div>
   <div class="card">
     <h3>Mis listados</h3><button onclick="cargar()">Actualizar</button>
     <div id="tbl"></div>
   </div>
 </div>
</div>
<script>
const BASE = location.pathname.replace(/\/panel.*$/, "");
let TOKEN = new URLSearchParams(location.search).get("token") || "";
function H(){return {"X-Lonja-Token":TOKEN,"Content-Type":"application/json"};}
async function api(m,p,b){const r=await fetch(BASE+p,{method:m,headers:H(),body:b?JSON.stringify(b):undefined});
  let j=null; try{j=await r.json()}catch(e){} return {ok:r.ok,status:r.status,j};}
function out(msg,err){document.getElementById("out").innerHTML=msg?('<div class="msg '+(err?'err':'ok')+'">'+msg+'</div>'):"";}
function esc(s){return (s==null?"":(""+s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

async function entrar(){
  TOKEN=document.getElementById("tok").value.trim()||TOKEN;
  const r=await api("GET","/me");
  if(!r.ok){document.getElementById("loginmsg").innerHTML='<div class="msg err">Token no válido.</div>';return;}
  document.getElementById("who").textContent="· "+(r.j.nombre||"")+" ("+(r.j.divisa||"")+")";
  if(r.j.divisa){document.getElementById("divisa").value=r.j.divisa;}
  document.getElementById("login").classList.add("hide");
  document.getElementById("app").classList.remove("hide");
  cargar();
}
function salir(){TOKEN="";document.getElementById("app").classList.add("hide");document.getElementById("login").classList.remove("hide");}

async function guardarDivisa(){const d=document.getElementById("divisa").value;
  const r=await api("PUT","/divisa",{divisa:d}); out(r.ok?"Divisa guardada.":"Error.",!r.ok);
  if(r.ok){const me=await api("GET","/me"); if(me.ok)document.getElementById("who").textContent="· "+(me.j.nombre||"")+" ("+(me.j.divisa||"")+")";}}

async function publicar(){
  const b={codigo:document.getElementById("p_cod").value.trim(),
    precio:parseFloat(document.getElementById("p_precio").value),
    puja_minima:parseFloat(document.getElementById("p_min").value)||0,
    cantidad:parseFloat(document.getElementById("p_cant").value)||1,
    unidad_medida:document.getElementById("p_uni").value,
    duracion_horas:parseFloat(document.getElementById("p_dur").value)||24,
    precio_reserva:(document.getElementById("p_res").value!==""?parseFloat(document.getElementById("p_res").value):null),
    incremento_minimo:parseFloat(document.getElementById("p_inc").value)||0,
    permite_compra_directa:document.getElementById("p_cd").checked,
    permite_puja:document.getElementById("p_pj").checked};
  if(!b.codigo||!(b.precio>0)){out("Indica código y precio.",true);return;}
  const r=await api("POST","/listados",b); out(r.ok?"Publicado en el mercado.":"Error al publicar.",!r.ok);
  if(r.ok){document.getElementById("p_cod").value="";document.getElementById("p_precio").value="";document.getElementById("p_min").value="";cargar();}}

async function retirar(id){const r=await api("DELETE","/listados/"+id); out(r.ok?"Listado retirado.":"Error.",!r.ok); if(r.ok)cargar();}

async function cargar(){const r=await api("GET","/listados");const d=(r.j&&r.j.data)||[];
  let h="<table><tr><th>ID</th><th>Artículo</th><th>Precio</th><th>Divisa</th><th>Puja mín.</th><th>Disp.</th><th>Estado</th><th></th></tr>";
  for(const x of d){h+="<tr><td>"+esc(x.id)+"</td><td>"+esc(x.codigo_articulo)+"</td><td>"+esc(x.precio)+"</td><td>"+esc(x.divisa)+"</td>"+
    "<td>"+esc(x.puja_minima)+"</td><td>"+esc(x.cantidad_disponible)+"</td><td>"+esc(x.estado)+"</td>"+
    "<td>"+(x.estado==="activo"?('<button class="rojo" onclick="retirar('+x.id+')">Retirar</button>'):"")+"</td></tr>";}
  document.getElementById("tbl").innerHTML=h+"</table>";}

if(TOKEN){document.getElementById("tok").value=TOKEN; entrar();}
</script></body></html>"""


def panel_html() -> str:
    return _HTML
