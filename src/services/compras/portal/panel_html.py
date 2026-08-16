"""Panel web del proveedor (una sola página, autocontenida).

Es el front-end que el PROVEEDOR abre con su token el día del despliegue. No añade lógica de negocio:
consume los endpoints REST de `portal_proveedor` (`/api/v1/portal-proveedor/*`) con la cabecera
`X-Portal-Token`. Se sirve desde el propio blueprint de la API (misma raíz), así que funciona en local y,
cuando el backend se despliegue, quedará accesible por HTTP sin cambios.
"""

_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portal de Proveedor</title>
<style>
 :root{--bg:#0D1117;--pan:#161B22;--cy:#00FFC6;--tx:#E6EDF3;--dim:#8B949E;--bd:#30363D;--rojo:#F85149}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--tx);font-family:Segoe UI,Arial,sans-serif}
 header{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--bd)}
 header h1{font-size:18px;margin:0;color:var(--cy)} .modo{color:var(--dim);font-size:12px}
 .wrap{max-width:920px;margin:0 auto;padding:18px}
 input,select,button,textarea{font:inherit;border-radius:8px;border:2px solid var(--bd);background:#0D1117;color:var(--tx);padding:8px 10px}
 input:focus,select:focus,textarea:focus{border-color:var(--cy);outline:none}
 button{background:#161B22;color:var(--cy);border-color:var(--cy);font-weight:700;cursor:pointer}
 button:hover{background:var(--cy);color:#0D1117} button.rojo{color:var(--rojo);border-color:var(--rojo)}
 button.rojo:hover{background:var(--rojo);color:#0D1117}
 .tabs{display:flex;gap:6px;flex-wrap:wrap;margin:14px 0} .tabs button{border-color:var(--bd)}
 .tabs button.on{background:var(--cy);color:#0D1117}
 table{width:100%;border-collapse:collapse;border:2px solid var(--cy);border-radius:10px;overflow:hidden;margin-top:10px}
 th,td{padding:8px;border-bottom:1px solid var(--bd);text-align:left;font-size:13px}
 th{color:var(--cy);font-size:11px} .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}
 .card{background:var(--pan);border:1px solid var(--bd);border-radius:12px;padding:16px;margin-top:12px}
 .hide{display:none} .msg{padding:8px 10px;border-radius:8px;margin:8px 0;font-size:13px}
 .ok{background:#00FFC622;color:var(--cy)} .err{background:#F8514922;color:var(--rojo)}
 .hilo{background:#0D1117;border:2px solid var(--cy);border-radius:10px;padding:10px;min-height:120px;white-space:pre-wrap;font-size:13px}
</style></head><body>
<header><h1>🔗 Portal de Proveedor</h1><span class="modo" id="modo"></span></header>
<div class="wrap">
 <div id="login" class="card">
   <p>Introduce tu <b>token de acceso</b> (lo recibiste en el correo de invitación):</p>
   <div class="row"><input id="tok" style="flex:1" placeholder="Token de acceso"><button onclick="entrar()">Entrar</button></div>
   <div id="loginmsg"></div>
 </div>
 <div id="app" class="hide">
   <div class="tabs">
     <button data-t="tarifas" class="on" onclick="ir('tarifas')">Tarifas</button>
     <button data-t="stock" onclick="ir('stock')">Stock</button>
     <button data-t="pedidos" onclick="ir('pedidos')">Pedidos</button>
     <button data-t="rfq" onclick="ir('rfq')">RFQ</button>
     <button data-t="mensajes" onclick="ir('mensajes')">Mensajes</button>
     <button class="rojo" style="margin-left:auto" onclick="salir()">Salir</button>
   </div>
   <div id="out"></div>

   <div id="v-tarifas" class="vista card">
     <h3>Mis tarifas</h3>
     <div class="row">
       <input id="t_cod" placeholder="Código"><input id="t_prec" placeholder="Precio" size="6">
       <select id="t_uni"><option>unidad</option><option>caja</option><option>pale</option><option>kg</option></select>
       <input id="t_dto" placeholder="Dto %" size="4">
       <button onclick="subirTarifa()">Guardar precio</button>
     </div>
     <div id="tbl_tarifas"></div>
   </div>

   <div id="v-stock" class="vista card hide">
     <h3>Stock disponible</h3>
     <div class="row">
       <input id="s_cod" placeholder="Código"><input id="s_stk" placeholder="Stock" size="6">
       <select id="s_uni"><option>unidad</option><option>caja</option><option>pale</option><option>kg</option></select>
       <button onclick="subirStock()">Declarar stock</button>
     </div>
   </div>

   <div id="v-pedidos" class="vista card hide">
     <h3>Mis pedidos</h3><button onclick="cargarPedidos()">Actualizar</button>
     <div id="tbl_pedidos"></div>
   </div>

   <div id="v-rfq" class="vista card hide">
     <h3>Peticiones de precio (RFQ)</h3><button onclick="cargarRfq()">Actualizar</button>
     <div id="tbl_rfq"></div>
   </div>

   <div id="v-mensajes" class="vista card hide">
     <h3>Mensajes con la empresa</h3><button onclick="cargarMsg()">Actualizar</button>
     <div class="hilo" id="hilo"></div>
     <div class="row"><input id="m_txt" style="flex:1" placeholder="Escribe un mensaje…"><button onclick="enviarMsg()">Enviar</button></div>
   </div>
 </div>
</div>
<script>
const BASE = location.pathname.replace(/\/panel.*$/, "");
let TOKEN = new URLSearchParams(location.search).get("token") || "";
function H(){return {"X-Portal-Token":TOKEN,"Content-Type":"application/json"};}
async function api(m,p,b){const r=await fetch(BASE+p,{method:m,headers:H(),body:b?JSON.stringify(b):undefined});
  let j=null; try{j=await r.json()}catch(e){} return {ok:r.ok,status:r.status,j};}
function out(msg,err){document.getElementById("out").innerHTML=msg?('<div class="msg '+(err?'err':'ok')+'">'+msg+'</div>'):"";}
function esc(s){return (s==null?"":(""+s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

async function entrar(){
  TOKEN=document.getElementById("tok").value.trim()||TOKEN;
  const r=await api("GET","/me");
  if(!r.ok){document.getElementById("loginmsg").innerHTML='<div class="msg err">Token no válido.</div>';return;}
  document.getElementById("modo").textContent="· modo "+(r.j.modo||"");
  document.getElementById("login").classList.add("hide");
  document.getElementById("app").classList.remove("hide");
  ir("tarifas");
}
function salir(){TOKEN="";document.getElementById("app").classList.add("hide");document.getElementById("login").classList.remove("hide");}
function ir(t){
  document.querySelectorAll(".vista").forEach(v=>v.classList.add("hide"));
  document.getElementById("v-"+t).classList.remove("hide");
  document.querySelectorAll(".tabs button[data-t]").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
  out(""); if(t==="tarifas")cargarTarifas(); if(t==="pedidos")cargarPedidos();
  if(t==="rfq")cargarRfq(); if(t==="mensajes")cargarMsg();
}
function tabla(cols,filas){let h="<table><tr>"+cols.map(c=>"<th>"+c+"</th>").join("")+"</tr>";
  for(const f of filas){h+="<tr>"+f.map(c=>"<td>"+c+"</td>").join("")+"</tr>";} return h+"</table>";}

async function cargarTarifas(){const r=await api("GET","/tarifas");const d=(r.j&&r.j.data)||[];
  document.getElementById("tbl_tarifas").innerHTML=tabla(["Artículo","Precio","Dto %","Unidad"],
    d.map(x=>[esc(x.codigo_articulo),esc(x.precio),esc(x.descuento),esc(x.unidad_medida)]));}
async function subirTarifa(){const b={codigo:document.getElementById("t_cod").value.trim(),
  precio:parseFloat(document.getElementById("t_prec").value),unidad_medida:document.getElementById("t_uni").value,
  descuento:parseFloat(document.getElementById("t_dto").value)||0};
  const r=await api("PUT","/tarifas",b); out(r.ok?"Precio guardado.":"Error al guardar.",!r.ok); if(r.ok)cargarTarifas();}
async function subirStock(){const b={codigo:document.getElementById("s_cod").value.trim(),
  stock:parseFloat(document.getElementById("s_stk").value),unidad_medida:document.getElementById("s_uni").value};
  const r=await api("PUT","/stock",b); out(r.ok?"Stock declarado.":"Error.",!r.ok);}

async function cargarPedidos(){const r=await api("GET","/pedidos");const d=(r.j&&r.j.data)||[];
  let h="<table><tr><th>ID</th><th>Nº</th><th>Total</th><th>Estado</th><th>Acción</th></tr>";
  for(const p of d){h+="<tr><td>"+esc(p.id_pedido)+"</td><td>"+esc(p.numero)+"</td><td>"+esc(p.total)+"</td>"+
    "<td>"+esc(p.estado_proveedor)+"</td><td>"+
    '<select id="e'+p.id_pedido+'"><option>aceptado</option><option>en_reparto</option><option>no_disponible</option><option>rechazado</option></select> '+
    '<button onclick="estadoPedido('+p.id_pedido+')">Guardar</button></td></tr>';}
  document.getElementById("tbl_pedidos").innerHTML=h+"</table>";}
async function estadoPedido(id){const est=document.getElementById("e"+id).value;
  const r=await api("PUT","/pedidos/"+id+"/estado",{estado:est}); out(r.ok?"Estado actualizado.":"Error.",!r.ok); if(r.ok)cargarPedidos();}

async function cargarRfq(){const r=await api("GET","/rfq");const d=(r.j&&r.j.data)||[];
  let h="<table><tr><th>ID</th><th>Artículo</th><th>Cantidad</th><th>Unidad</th><th>Tu oferta</th></tr>";
  for(const q of d){h+="<tr><td>"+esc(q.id)+"</td><td>"+esc(q.codigo_articulo)+"</td><td>"+esc(q.cantidad)+"</td><td>"+esc(q.unidad_medida)+"</td>"+
    '<td><input id="o'+q.id+'" size="6" placeholder="precio"> <button onclick="ofertar('+q.id+')">Ofertar</button></td></tr>';}
  document.getElementById("tbl_rfq").innerHTML=h+"</table>";}
async function ofertar(id){const precio=parseFloat(document.getElementById("o"+id).value);
  if(!(precio>0)){out("Indica un precio.",true);return;}
  const r=await api("POST","/rfq/"+id+"/oferta",{precio}); out(r.ok?"Oferta enviada.":"Error.",!r.ok);}

async function cargarMsg(){const r=await api("GET","/mensajes");const d=(r.j&&r.j.data)||[];
  document.getElementById("hilo").textContent=d.map(m=>"["+((m.creado_en||"")+"").slice(0,16)+"] "+
    (m.autor==="proveedor"?"Tú":"Empresa")+": "+m.cuerpo).join("\n")||"(sin mensajes)";}
async function enviarMsg(){const cuerpo=document.getElementById("m_txt").value.trim();if(!cuerpo)return;
  const r=await api("POST","/mensajes",{cuerpo}); if(r.ok){document.getElementById("m_txt").value="";cargarMsg();} else out("Error al enviar.",true);}

if(TOKEN){document.getElementById("tok").value=TOKEN; entrar();}
</script></body></html>"""


def panel_html() -> str:
    return _HTML
