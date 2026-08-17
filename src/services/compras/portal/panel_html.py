"""Panel web UNIFICADO del suministrador (proveedor = vendedor de la Lonja), una sola página.

El proveedor entra con su token de portal (`X-Portal-Token`) y en un ÚNICO panel opera:
- Como PROVEEDOR (endpoints `portal-proveedor`): tarifas, stock, pedidos, mensajería.
- Como VENDEDOR de la Lonja (endpoints `lonja-vendedor`): tipo de comercio, divisa, cuenta bancaria y
  listados/subastas. El token de la Lonja se obtiene del puente `/portal-proveedor/lonja-token`.

No añade lógica de negocio: consume los endpoints REST existentes. Autocontenida; se sirve desde el
blueprint de la API, así funciona en local y por HTTP cuando el backend se despliegue.
"""

_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portal del Suministrador</title>
<style>
 :root{--bg:#0D1117;--pan:#161B22;--cy:#00FFC6;--tx:#E6EDF3;--dim:#8B949E;--bd:#30363D;--rojo:#F85149}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--tx);font-family:Segoe UI,Arial,sans-serif}
 header{display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--bd)}
 header h1{font-size:18px;margin:0;color:var(--cy)} .modo{color:var(--dim);font-size:12px}
 .wrap{max-width:940px;margin:0 auto;padding:18px}
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
 label.chk{display:inline-flex;gap:6px;align-items:center;font-size:13px;color:var(--dim)} b{color:var(--cy)}
</style></head><body>
<header><h1>🔗 Portal del Proveedor</h1><span class="modo" id="modo"></span></header>
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
     <button data-t="mercado" onclick="ir('mercado')">Mercado / Subastas</button>
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

   <div id="v-mercado" class="vista card hide">
     <h3>Mercado (Lonja) · vende y subasta a las empresas</h3>
     <div class="row"><b>Tipo de comercio:</b>
       <span id="mtc">
         <label class="chk"><input type="checkbox" value="SUPERMARKET"> Supermercado</label>
         <label class="chk"><input type="checkbox" value="RETAIL"> Retail</label>
         <label class="chk"><input type="checkbox" value="PHARMACY"> Farmacia</label>
         <label class="chk"><input type="checkbox" value="TEXTIL"> Textil</label>
         <label class="chk"><input type="checkbox" value="BAKERY"> Panadería</label>
       </span>
       <button onclick="guardarTipoL()">Guardar</button>
     </div>
     <div class="row"><b>Divisa:</b>
       <select id="mdiv"><option>EUR</option><option>USD</option><option>GBP</option><option>MXN</option><option>BRL</option></select>
       <button onclick="guardarDivisaL()">Guardar</button></div>
     <div class="row"><b>Cobros (KYB):</b>
       <button onclick="conectarCobros()">Conectar cobros</button>
       <span class="modo" id="mkyb">sin conectar</span></div>
     <div class="row"><a id="kyblink" href="#" target="_blank" style="display:none;color:var(--cy)">Abrir onboarding del PSP ↗</a></div>
     <h4>Publicar artículo / subasta</h4>
     <div class="row">
       <input id="l_cod" placeholder="Código" size="10"><input id="l_prec" placeholder="Precio" size="7">
       <input id="l_min" placeholder="Puja mín." size="7"><input id="l_cant" placeholder="Cantidad" size="6" value="1">
       <select id="l_uni"><option>unidad</option><option>caja</option><option>pale</option><option>kg</option></select>
     </div>
     <div class="row">
       <input id="l_dur" placeholder="Duración (h)" size="7" value="24"><input id="l_res" placeholder="Reserva (opc.)" size="8">
       <input id="l_inc" placeholder="Incremento" size="7" value="0"><button onclick="publicarL()">Publicar</button>
     </div>
     <div id="tbl_listados"></div>
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
const LBASE = BASE.replace("portal-proveedor", "lonja-vendedor");
let TOKEN = new URLSearchParams(location.search).get("token") || "";
let TAB0 = new URLSearchParams(location.search).get("tab") || "";   // deep-link opcional a una pestaña
let LTOKEN = "";
function H(){return {"X-Portal-Token":TOKEN,"Content-Type":"application/json"};}
function HL(){return {"X-Lonja-Token":LTOKEN,"Content-Type":"application/json"};}
async function api(m,p,b){const r=await fetch(BASE+p,{method:m,headers:H(),body:b?JSON.stringify(b):undefined});
  let j=null; try{j=await r.json()}catch(e){} return {ok:r.ok,status:r.status,j};}
async function apiL(m,p,b){if(!LTOKEN)return {ok:false,j:null};
  const r=await fetch(LBASE+p,{method:m,headers:HL(),body:b?JSON.stringify(b):undefined});
  let j=null; try{j=await r.json()}catch(e){} return {ok:r.ok,j};}
function out(msg,err){document.getElementById("out").innerHTML=msg?('<div class="msg '+(err?'err':'ok')+'">'+msg+'</div>'):"";}
function esc(s){return (s==null?"":(""+s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

async function entrar(){
  TOKEN=document.getElementById("tok").value.trim()||TOKEN;
  const r=await api("GET","/me");
  if(!r.ok){document.getElementById("loginmsg").innerHTML='<div class="msg err">Token no válido.</div>';return;}
  document.getElementById("modo").textContent="· modo "+(r.j.modo||"");
  const lt=await api("GET","/lonja-token"); LTOKEN=(lt.j&&lt.j.token)||"";   // puente proveedor→vendedor
  document.getElementById("login").classList.add("hide");
  document.getElementById("app").classList.remove("hide");
  ir(TAB0 || "tarifas");
}
function salir(){TOKEN="";LTOKEN="";document.getElementById("app").classList.add("hide");document.getElementById("login").classList.remove("hide");}
function ir(t){
  document.querySelectorAll(".vista").forEach(v=>v.classList.add("hide"));
  document.getElementById("v-"+t).classList.remove("hide");
  document.querySelectorAll(".tabs button[data-t]").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
  out(""); if(t==="tarifas")cargarTarifas(); if(t==="pedidos")cargarPedidos();
  if(t==="mercado")cargarMercado(); if(t==="mensajes")cargarMsg();
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

// ── Mercado (Lonja) ──
async function cargarMercado(){
  if(!LTOKEN){out("El mercado no está disponible para esta cuenta.",true);return;}
  const me=await apiL("GET","/me");
  if(me.ok&&me.j){
    if(me.j.divisa)document.getElementById("mdiv").value=me.j.divisa;
    const tc=((me.j.tipo_comercio)||"").split(",");
    document.querySelectorAll("#mtc input").forEach(i=>{i.checked=tc.includes(i.value);});
  }
  estadoCobros();
  const r=await apiL("GET","/listados");const d=(r.j&&r.j.data)||[];
  let h="<table><tr><th>ID</th><th>Artículo</th><th>Precio</th><th>Divisa</th><th>Puja mín.</th><th>Disp.</th><th>Estado</th><th></th></tr>";
  for(const x of d){h+="<tr><td>"+esc(x.id)+"</td><td>"+esc(x.codigo_articulo)+"</td><td>"+esc(x.precio)+"</td><td>"+esc(x.divisa)+"</td>"+
    "<td>"+esc(x.puja_minima)+"</td><td>"+esc(x.cantidad_disponible)+"</td><td>"+esc(x.estado)+"</td>"+
    "<td>"+(x.estado==="activo"?('<button class="rojo" onclick="retirarL('+x.id+')">Retirar</button>'):"")+"</td></tr>";}
  document.getElementById("tbl_listados").innerHTML=h+"</table>";
}
function mtcMarcados(){return [...document.querySelectorAll("#mtc input:checked")].map(i=>i.value);}
async function guardarTipoL(){const r=await apiL("PUT","/tipo-comercio",{tipo_comercio:mtcMarcados()});out(r.ok?"Tipo de comercio guardado.":"Error.",!r.ok);}
async function guardarDivisaL(){const r=await apiL("PUT","/divisa",{divisa:document.getElementById("mdiv").value});out(r.ok?"Divisa guardada.":"Error.",!r.ok);}
async function estadoCobros(){const r=await apiL("GET","/cobros/estado");const e=r.j||{};
  const el=document.getElementById("mkyb");
  if(e&&e.account_id){el.textContent=(e.etiqueta||"cuenta")+" · "+(e.status||"pending")+(e.payouts_enabled?" · payouts ✓":"");}
  else{el.textContent="sin conectar";}
  const a=document.getElementById("kyblink");
  if(e&&e.onboarding_url){a.href=e.onboarding_url;a.style.display="";}else{a.style.display="none";}}
async function conectarCobros(){const r=await apiL("POST","/cobros/onboarding");
  if(!r.ok){out("No se pudo iniciar el onboarding de cobros.",true);return;}
  out((r.j&&r.j.onboarding_url)?"Onboarding creado: abre el enlace para completar el KYB.":"Cuenta creada en modo simulado (sin PSP configurado).",false);
  estadoCobros();}
async function publicarL(){const b={codigo:document.getElementById("l_cod").value.trim(),
  precio:parseFloat(document.getElementById("l_prec").value),puja_minima:parseFloat(document.getElementById("l_min").value)||0,
  cantidad:parseFloat(document.getElementById("l_cant").value)||1,unidad_medida:document.getElementById("l_uni").value,
  duracion_horas:parseFloat(document.getElementById("l_dur").value)||24,incremento_minimo:parseFloat(document.getElementById("l_inc").value)||0,
  precio_reserva:(document.getElementById("l_res").value!==""?parseFloat(document.getElementById("l_res").value):null)};
  if(!b.codigo||!(b.precio>0)){out("Indica código y precio.",true);return;}
  const r=await apiL("POST","/listados",b);out(r.ok?"Publicado en el mercado.":"Error al publicar.",!r.ok);
  if(r.ok){document.getElementById("l_cod").value="";document.getElementById("l_prec").value="";cargarMercado();}}
async function retirarL(id){const r=await apiL("DELETE","/listados/"+id);out(r.ok?"Listado retirado.":"Error.",!r.ok);if(r.ok)cargarMercado();}

async function cargarMsg(){const r=await api("GET","/mensajes");const d=(r.j&&r.j.data)||[];
  document.getElementById("hilo").textContent=d.map(m=>"["+((m.creado_en||"")+"").slice(0,16)+"] "+
    (m.autor==="proveedor"?"Tú":"Empresa")+": "+m.cuerpo).join("\n")||"(sin mensajes)";}
async function enviarMsg(){const cuerpo=document.getElementById("m_txt").value.trim();if(!cuerpo)return;
  const r=await api("POST","/mensajes",{cuerpo}); if(r.ok){document.getElementById("m_txt").value="";cargarMsg();} else out("Error al enviar.",true);}

if(TOKEN){document.getElementById("tok").value=TOKEN; entrar();}
</script></body></html>"""


def panel_html() -> str:
    return _HTML
