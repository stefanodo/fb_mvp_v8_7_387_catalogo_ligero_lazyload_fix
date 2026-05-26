// core.js — F&B MVP
// Funciones globales, nav, stock, elaborados. Sin duplicados.

// --- Safe DOM helpers (avoid breaking whole UI if an element is missing)
function filterSelect(inputEl, selectEl){
  if(!selectEl) return;
  const q=(inputEl.value||'').toLowerCase();
  for(const opt of selectEl.options){
    if(!opt.value){ opt.hidden=false; continue; }
    const t=(opt.textContent||'').toLowerCase();
    opt.hidden = q && !t.includes(q);
  }
}

const $ = (id)=>document.getElementById(id);
const on = (id, ev, fn)=>{ const el=$(id); if(el) el.addEventListener(ev, fn); return el; };

const WAREHOUSES = Array.isArray(window.WAREHOUSES) ? window.WAREHOUSES : [];
const ITEMS = Array.isArray(window.ITEMS) ? window.ITEMS : [];
const SUPPLIERS = Array.isArray(window.SUPPLIERS) ? window.SUPPLIERS : [];
const SUPPLIER_PRICES = Array.isArray(window.SUPPLIER_PRICES) ? window.SUPPLIER_PRICES : [];
const CATEGORY_PREFIX = {"Entrantes":"ENT","Principales":"PRI","Postres":"POS","Ensaladas":"ENS","Guarniciones":"GUA","Salsas":"SAL","Bases":"BAS","Preelaborados":"PRE","Bebidas":"BEB","Otros":"OTR"};

// Blindaje de contexto global para helpers inline del admin.
// Algunos bloques leen window.ITEMS / window.SUPPLIER_PRICES; con const top-level
// esos nombres existen, pero no siempre quedan como propiedades de window.
try{
  window.WAREHOUSES = WAREHOUSES;
  window.ITEMS = ITEMS;
  window.SUPPLIERS = SUPPLIERS;
  window.SUPPLIER_PRICES = SUPPLIER_PRICES;
}catch(e){}

function unitOptionsFor(baseUnit){
  if(baseUnit==="g"){return ["g","kg"];}
    return [baseUnit];
}
function refreshMovementUnit(){
  const itemSel=document.getElementById('mv_item_id');
  const unitSel=document.getElementById('mv_unit');
  if(!itemSel || !unitSel) return;
  const itemId=parseInt(itemSel.value||'0',10);
  const item=ITEMS.find(x=>x.id===itemId);
  const opts=unitOptionsFor(item ? item.unit : "g");
  unitSel.innerHTML = opts.map(u=>`<option value="${u}">${u}</option>`).join("");
}

function parseItemIdFromText(txt){
  const m = /\[#(\d+)\]/.exec(txt||'');
  if(m) return parseInt(m[1],10);
  // fallback exact match by name
  const t = (txt||'').trim().toLowerCase();
  const it = ITEMS.find(i=>String(i.name||'').trim().toLowerCase()===t);
  return it ? it.id : null;
}

function bindItemAutocomplete(){
  const text = document.getElementById('mv_item_text');
  const hid = document.getElementById('mv_item_id');
  if(!text || !hid) return;
  // default first item
  if(!text.value && hid.value){
    const it = ITEMS.find(i=>i.id===parseInt(hid.value,10));
    if(it) text.value = `${it.name} [#${it.id}]`;
  }
  text.addEventListener('change', ()=>{
    const id = parseItemIdFromText(text.value);
    if(id){ hid.value = id; refreshMovementUnit(); }
  });
}
function renderSuppliers(){
  const tb=document.querySelector('#suppliersTable tbody');
  if(tb){ tb.innerHTML = SUPPLIERS.map(s=>`<tr data-provider="${s.name}" data-article="${s.phone||""}"><td>${s.name}</td><td>${s.phone||""}</td><td>${s.email||""}</td></tr>`).join(""); }
  const spSel=document.getElementById('sp_supplier');
  if(spSel){ spSel.innerHTML = SUPPLIERS.map(s=>`<option value="${s.id}">${s.name}</option>`).join(""); }
}

function applyPricesFilter(){
  const inp = document.getElementById('pricesFilter');
  const q = ((inp && inp.value) || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#pricesTable tbody tr');
  rows.forEach(r=>{
    if(!q){ r.style.display=''; return; }
    const p = (r.getAttribute('data-provider')||'').toLowerCase();
    const a = (r.getAttribute('data-article')||'').toLowerCase();
    r.style.display = (p.includes(q) || a.includes(q)) ? '' : 'none';
  });
}


function applySuppliersFilter(){
  const inp = document.getElementById('suppliersFilter');
  const q = ((inp && inp.value) || '').trim().toLowerCase();
  const rows = document.querySelectorAll('#suppliersTable tbody tr');
  rows.forEach(r=>{
    if(!q){ r.style.display=''; return; }
    const n = (r.querySelector('input[name="name"]')?.value || '').toLowerCase();
    const p = (r.querySelector('input[name="phone"]')?.value || '').toLowerCase();
    const e = (r.querySelector('input[name="email"]')?.value || '').toLowerCase();
    r.style.display = (n.includes(q) || p.includes(q) || e.includes(q)) ? '' : 'none';
  });
}

function wireAdminQuickFilters(){
  const supplierInp = document.getElementById('suppliersFilter');
  const supplierSuggest = document.getElementById('suppliersFilterSuggestions');
  if(supplierInp && supplierSuggest){
    const render = ()=>{
      const q = String(supplierInp.value||'').trim().toLowerCase();
      applySuppliersFilter();
      if(q.length < 1){ supplierSuggest.style.display='none'; supplierSuggest.innerHTML=''; return; }
      const matches = SUPPLIERS.filter(s=>{
        const n = String(s.name||'').toLowerCase();
        const p = String(s.phone||'').toLowerCase();
        const e = String(s.email||'').toLowerCase();
        return n.includes(q) || p.includes(q) || e.includes(q);
      }).slice(0,10);
      supplierSuggest.innerHTML = matches.map(s=>`<button type="button" data-name="${String(s.name||'').replace(/"/g,'&quot;')}">${s.name}<small>${s.phone||s.email||''}</small></button>`).join('');
      supplierSuggest.style.display = matches.length ? 'block' : 'none';
    };
    supplierInp.addEventListener('input', render);
    supplierInp.addEventListener('focus', render);
    supplierSuggest.addEventListener('mousedown', e=>e.preventDefault());
    supplierSuggest.addEventListener('click', function(e){
      const b=e.target.closest('button[data-name]'); if(!b) return;
      supplierInp.value = b.dataset.name || '';
      supplierSuggest.style.display='none'; supplierSuggest.innerHTML='';
      applySuppliersFilter();
      const row = Array.from(document.querySelectorAll('#suppliersTable tbody tr')).find(tr=> (tr.querySelector('input[name="name"]')?.value||'') === supplierInp.value);
      if(row){ row.scrollIntoView({behavior:'smooth', block:'center'}); row.classList.add('row-flash'); setTimeout(()=>row.classList.remove('row-flash'), 1500); }
    });
    document.addEventListener('click', function(e){ if(e.target!==supplierInp && !supplierSuggest.contains(e.target)){ supplierSuggest.style.display='none'; } });
  }

  const pricesInp = document.getElementById('pricesFilter');
  const pricesSuggest = document.getElementById('pricesFilterSuggestions');
  if(pricesInp && pricesSuggest){
    function currentPriceRows(){
      const domRows = Array.from(document.querySelectorAll('#pricesTable tbody tr')).map(tr=>({
        provider: String(tr.getAttribute('data-provider') || tr.children[0]?.textContent || '').trim(),
        article: String(tr.getAttribute('data-article') || tr.children[1]?.textContent || '').trim(),
        row: tr
      })).filter(x=>x.provider || x.article);
      if(domRows.length) return domRows;
      return (SUPPLIER_PRICES || []).map(sp=>({
        provider: String(sp.supplier_name || '').trim(),
        article: String(sp.item_name || '').trim(),
        row: null
      }));
    }
    const render = ()=>{
      const q = String(pricesInp.value||'').trim().toLowerCase();
      applyPricesFilter();
      if(q.length < 1){ pricesSuggest.style.display='none'; pricesSuggest.innerHTML=''; return; }
      const seen = new Set();
      const matches = currentPriceRows().filter(x=>{
        const sp = x.provider.toLowerCase();
        const it = x.article.toLowerCase();
        return sp.includes(q) || it.includes(q);
      }).filter(x=>{
        const key = `${x.article}@@${x.provider}`;
        if(seen.has(key)) return false;
        seen.add(key);
        return true;
      }).sort((a,b)=>{
        const ax = a.article.toLowerCase(), bx = b.article.toLowerCase();
        const ap = a.provider.toLowerCase(), bp = b.provider.toLowerCase();
        const as = ax.startsWith(q) ? 0 : 1;
        const bs = bx.startsWith(q) ? 0 : 1;
        return as - bs || ax.localeCompare(bx) || ap.localeCompare(bp);
      }).slice(0,10);
      if(!matches.length){
        pricesSuggest.innerHTML = '<div class="search-empty">Sin coincidencias</div>';
        pricesSuggest.style.display = 'block';
        return;
      }
      pricesSuggest.innerHTML = matches.map(x=>`<button type="button" data-provider="${String(x.provider).replace(/"/g,'&quot;')}" data-article="${String(x.article).replace(/"/g,'&quot;')}"><span>${x.article}</span><small>${x.provider}</small></button>`).join('');
      pricesSuggest.style.display = 'block';
    };
    pricesInp.addEventListener('input', render);
    pricesInp.addEventListener('focus', render);
    pricesInp.addEventListener('keydown', function(e){
      if(e.key === 'Enter'){
        const first = pricesSuggest.querySelector('button[data-article]');
        if(first){ e.preventDefault(); first.click(); }
      }
    });
    pricesSuggest.addEventListener('mousedown', e=>e.preventDefault());
    pricesSuggest.addEventListener('click', function(e){
      const b=e.target.closest('button[data-article]'); if(!b) return;
      pricesInp.value = b.dataset.article || '';
      pricesSuggest.style.display='none'; pricesSuggest.innerHTML='';
      applyPricesFilter();
      const row = Array.from(document.querySelectorAll('#pricesTable tbody tr')).find(tr=> {
        const a = (tr.getAttribute('data-article')||'').trim();
        const p = (tr.getAttribute('data-provider')||'').trim();
        return a === (b.dataset.article||'') && p === (b.dataset.provider||'');
      });
      if(row){ row.scrollIntoView({behavior:'smooth', block:'center'}); row.classList.add('row-flash'); setTimeout(()=>row.classList.remove('row-flash'), 1500); }
    });
    document.addEventListener('click', function(e){ if(e.target!==pricesInp && !pricesSuggest.contains(e.target)){ pricesSuggest.style.display='none'; } });
  }
}
function renderSupplierPrices(){
  const tb=document.querySelector('#pricesTable tbody');
  if(!tb) return;
  tb.innerHTML = SUPPLIER_PRICES.map(p=>`<tr data-provider="${p.supplier_name}" data-article="${p.item_name}"><td>${p.supplier_name}</td><td>${p.item_name}</td><td>${Number(p.price_per_purchase).toFixed(4)}</td><td>${p.purchase_unit}</td><td>${p.purchase_to_base_factor}</td><td>${p.is_preferred? "Sí":"No"}</td></tr>`).join("");
  applyPricesFilter();
}
let currentRecipeId = null;

function goPage(id){
  // show/hide
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  const el=document.getElementById(id);
  if(el) el.classList.add('active');

  // nav active
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',(b.dataset.target||'')===id));

  // keep URL synced (no reload)
  try{const url=new URL(window.location.href);url.searchParams.set('page',id);history.replaceState({},'',url.toString());}catch(e){}

  // cargar elaborados al entrar a stock
  if(id === 'stock') loadElaborados();
}

document.querySelectorAll('.nav-btn').forEach(btn=>btn.addEventListener('click', ()=>goPage(btn.dataset.target)));

// preserve current page when changing center
on('globalCenterFilter','change',(e)=>{
  const url=new URL(window.location.href);
  if(e.target.value==='0') url.searchParams.delete('center_id'); else url.searchParams.set('center_id', e.target.value);
  if(!url.searchParams.get('page')) url.searchParams.set('page', document.querySelector('.nav-btn.active')?.dataset.target || 'inicio');
  window.location.href=url.toString();
});

// initial page from URL
try{const p=new URL(window.location.href).searchParams.get('page'); if(p) goPage(p);}catch(e){}

const mvCenter=document.getElementById('mv_center'); const mvWh=document.getElementById('mv_warehouse');
function refreshWarehouses(){const cid=Number(mvCenter.value); mvWh.innerHTML=''; WAREHOUSES.filter(w=>w.center_id===cid).forEach(w=>{const o=document.createElement('option');o.value=w.id;o.textContent=w.name;mvWh.appendChild(o);});}
if(mvCenter){ mvCenter.addEventListener('change', refreshWarehouses); refreshWarehouses(); }

async function saveMovement(andExit=false){
  const formEl=document.getElementById('movementForm'); const form=new FormData(formEl); const msg=document.getElementById('movementMsg');
  msg.className='msg'; msg.textContent='Guardando...';
  const res=await fetch('/api/movement',{method:'POST',body:form}); const data=await res.json().catch(()=>({ok:false,error:'Error inesperado'}));
  if(!data.ok){msg.className='msg err'; msg.textContent=data.error||'Error'; return;}
  msg.className='msg ok'; msg.textContent=andExit ? 'Movimiento guardado. Volviendo al inicio...' : 'Movimiento guardado. Puedes seguir cargando.';
  // limpiar solo cantidad y nota (nombres reales del formulario)
  const qtyInput=formEl.querySelector('[name="qty_value"]');
  const noteInput=formEl.querySelector('[name="note"]');
  if(qtyInput) qtyInput.value='';
  if(noteInput) noteInput.value='';
  // refrescar tabla sin salir de la pantalla
  try{
    const cid = document.getElementById('globalCenterFilter')?.value || '0';
    const url = cid==='0' ? '/api/stocks' : `/api/stocks?center_id=${cid}`;
    const rr = await fetch(url);
    const jj = await rr.json();
    if(jj.ok){
      window.__stocks_cache = jj.stocks;
      renderStocksTable(jj.stocks);
    }
  }catch(e){}
  if(andExit){ goPage('inicio'); }
}

on('movementForm','submit',(e)=>{e.preventDefault(); saveMovement(false);});
on('saveAndExitBtn','click',()=>saveMovement(true));
on('refreshBtn','click', async ()=>{
  const msg=document.getElementById('movementMsg'); msg.className='msg ok'; msg.textContent='Actualizando...';
  const cid = document.getElementById('globalCenterFilter')?.value || '0';
  const url = cid==='0' ? '/api/stocks' : `/api/stocks?center_id=${cid}`;
  const rr = await fetch(url); const jj = await rr.json();
  if(jj.ok){ renderStocksTable(jj.stocks); msg.textContent='Datos actualizados'; }
  else { msg.className='msg err'; msg.textContent = jj.error || 'Error'; }
});

function fmtQty(q, unit){
  const n = Number(q||0);
  if(unit==='g' || unit==='ud') return `${Math.round(n)} ${unit}`;
  if(unit==='ml') return `${Math.round(n)} g`;
  if(unit==='l') return `${Number(n).toFixed(2).replace(/\.00$/,'').replace('.',',')} kg`;
  return `${n.toFixed(2)} ${unit}`;
}

function renderStocksTable(stocks){
  const tb = document.querySelector('#stock tbody');
  // table is inside stock section; locate specifically
  const tbody = document.querySelector('#stock table tbody');
  if(!tbody) return;
  tbody.innerHTML = stocks.map(s=>{
    const status = (Number(s.stock_qty) < Number(s.min_qty)) ? '<span class="badge danger">Bajo mínimo</span>' : ((Number(s.max_qty)>0 && Number(s.stock_qty)>Number(s.max_qty)) ? '<span class="badge warn">Sobre stock</span>' : '<span class="badge ok">OK</span>');
    return `<tr data-provider="${s.center_name}" data-article="${s.warehouse_name}"><td>${s.center_name}</td><td>${s.warehouse_name}</td>
      <td>${s.item_name}</td>
      <td>${fmtQty(s.stock_qty, s.unit)}</td>
      <td>${fmtQty(s.min_qty, s.unit)}</td>
      <td>${fmtQty(s.max_qty, s.unit)}</td>
      <td>${status}</td>
      <td><button class="mini" onclick="openMinMax(${s.item_id}, '${(s.item_name||'').replace(/'/g,"&#39;")}', '${s.unit}', ${s.min_qty}, ${s.max_qty})">Min/Max</button></td>
    </tr>`;
  }).join('');
}

function renderRecipe(r){
  currentRecipeId = r.id;
  const panel=document.getElementById('recipePanel');
  panel.innerHTML = `
    <h3>${r.name}</h3>
    <div class="recipe-meta">
      <div><strong>Código:</strong> ${r.code || '-'}</div>
      <div><strong>Categoría:</strong> ${r.category || '-'} / ${r.subcategory || 'Sin definir'}</div>
      <div><strong>Merma:</strong> ${Number(r.waste_pct).toFixed(2)}%</div>
      <div><strong>Alérgenos:</strong> ${r.allergens || '-'}</div>
    </div>
    <div class="subpanel">
  <h4>Ingredientes</h4>
            <form method="get" action="/" class="mini-search">
              
              
              {% if selected_recipe %}{% endif %}
              <label class="mini-label">Buscar artículo</label>
              <input name="item_search" value="{{item_search}}" placeholder="Escribe para filtrar artículos...">
              <button type="submit">Buscar</button>
            </form>
  <div class="actions" style="justify-content:flex-start; gap:8px;">
    <button type="button" id="addIngToggle" class="gold">+ Añadir ingrediente</button>
    <div id="ingMsg" class="msg" style="margin:0;"></div>
  </div>

  <form id="addIngForm" style="display:none; margin-top:10px;">
    
    <div class="grid4">
      <div class="row full">
        <label>Ingrediente</label>
        <input id="ingSearch" placeholder="Escribe para buscar... (patata, huevo...)" autocomplete="off">
        <div id="ingSuggestions" class="suggestions" style="display:none;"></div>
      </div>
      <div class="row"><label>Cantidad</label><input type="number" step="0.001" name="qty" id="ingQty" required></div>
      <div class="row"><label>Unidad</label><select name="unit" id="ingUnit"></select></div>
      <div class="row"><label>Merma %</label><input type="number" step="0.01" name="waste_pct" id="ingWaste" value="0"></div>
    </div>
    <div class="actions">
      <button type="submit" class="gold">Guardar ingrediente</button>
      <button type="button" id="cancelIngBtn">Cancelar</button>
    </div>
  </form>

  <table class="mt" id="priceTable">
    <thead><tr><th>Ingrediente</th><th>Bruto</th><th>Neto</th><th>Ud</th><th></th></tr></thead>
    <tbody id="priceTableBody">
      ${r.ingredients.map(i=>`<tr data-provider="${i.item_name}" data-article="${Number(i.qty_gross).toFixed(3)}"><td>${i.item_name}</td><td>${Number(i.qty_gross).toFixed(3)}</td>
        <td>${(i.qty_net===null||i.qty_net===undefined)?'' : Number(i.qty_net).toFixed(3)}</td>
        <td>${i.unit}</td>
        <td><button type="button" class="link delIngBtn" data-ing="${i.id}">Eliminar</button></td>
      </tr>`).join('')}
    </tbody>
  </table>
</div>
    <div class="subpanel"><h4>Elaboración paso a paso</h4><pre>${r.prep_steps || ''}</pre></div>
    <div class="subpanel"><h4>Costes y venta</h4>
      <form id="pricingForm">
      <div class="grid3">
        <div class="row"><label>Coste base</label><input value="${r.calc.cost_base.toFixed(2)}" disabled></div>
        <div class="row"><label>Contingencia %</label><input type="number" step="0.01" name="contingency_pct" value="${r.contingency_pct ?? 0}"></div>
        <div class="row"><label>Coste ajustado</label><input value="${r.calc.cost_adjusted.toFixed(2)}" disabled></div>
        <div class="row"><label>Food cost objetivo %</label><input type="number" step="0.01" name="target_food_cost_pct" value="${r.target_food_cost_pct ?? 0}"></div>
        <div class="row"><label>Precio sugerido</label><input value="${r.calc.suggested_price_calc.toFixed(2)}" disabled></div>
        <div class="row"><label>Precio venta manual</label><input type="number" step="0.01" name="manual_price" value="${r.manual_price ?? 0}"></div>
        <div class="row"><label>Margen objetivo %</label><input type="number" step="0.01" name="target_margin_pct" value="${r.target_margin_pct ?? 0}"></div>
        <div class="row"><label>Margen real €</label><input value="${r.calc.margin_value.toFixed(2)}" disabled></div>
        <div class="row"><label>Margen real %</label><input value="${r.calc.margin_pct.toFixed(2)}" disabled></div>
      </div>
      <div class="actions"><button class="gold">Guardar costes/venta</button></div><div id="pricingMsg" class="msg"></div></form>
    </div>`;

  on('pricingForm','submit', async (e)=>{
    e.preventDefault();
    const fd=new FormData(e.target); const rid=fd.get('recipe_id'); fd.delete('recipe_id');
    const pmsg=document.getElementById('pricingMsg'); pmsg.textContent='Guardando...';
    const rr=await fetch(`/api/recipe/${rid}/pricing`, {method:'POST', body:fd});
    const dd=await rr.json();
    if(dd.ok){ pmsg.className='msg ok'; pmsg.textContent='Costes/venta actualizados'; renderRecipe(dd.recipe); }
    else { pmsg.className='msg err'; pmsg.textContent=dd.error || 'Error'; }
  });
  const editBtn = document.getElementById('editRecipeBtn');
const saveBtn = document.getElementById('saveRecipeBtn');
const hdrForm = document.getElementById('recipeHeaderForm');
if(editBtn && saveBtn && hdrForm){
  editBtn.onclick = ()=>{
    const show = hdrForm.style.display==='none' || hdrForm.style.display==='';
    hdrForm.style.display = show ? 'block' : 'none';
    saveBtn.style.display = show ? 'inline-block' : 'none';
  };
  saveBtn.onclick = async ()=>{
    const fd = new FormData(hdrForm);
    const res = await fetch(`/api/recipe/${r.id}/update`, {method:'POST', body: fd});
    const data = await res.json();
    if(data.ok) renderRecipe(data.recipe);
    else alert(data.error || 'Error guardando receta');
  };
}
initIngredientUI(r);
}

on('viewRecipeBtn','click', async ()=>{
  const id=document.getElementById('recipeSelect').value; const msg=document.getElementById('recipeMsg');
  if(!id){ msg.className='msg err'; msg.textContent='Selecciona una receta'; return; }
  msg.className='msg'; msg.textContent='Cargando...';
  const res=await fetch('/api/recipe/'+id); const data=await res.json();
  if(!data.ok){ msg.className='msg err'; msg.textContent=data.error||'Error'; return; }
  msg.className='msg ok'; msg.textContent='Ficha cargada'; renderRecipe(data.recipe);
});

on('newRecipeBtn','click', async ()=>{ await createDraftAndOpen(); });

function updateCodePreview(){ const c=document.getElementById('newCategory').value; document.getElementById('previewCode').value = `Automático (${CATEGORY_PREFIX[c] || 'REC'})`; }
on('newCategory','change', updateCodePreview); updateCodePreview();

function syncAllergens(){ const checked=[...document.querySelectorAll('#allergenGrid input:checked')].map(x=>x.value); document.getElementById('allergensHidden').value=checked.join(', '); }
document.querySelectorAll('#allergenGrid input').forEach(el=>el && el.addEventListener('change', syncAllergens));

on('newRecipeForm','submit', async (e)=>{
  e.preventDefault();
  const form=e.target;
  const msg=document.getElementById('newRecipeMsg');

  // recopila alérgenos
  const allergens=[...document.querySelectorAll('#allergenGrid input:checked')].map(x=>x.value);
  const fd=new FormData(form);

  const name=(fd.get('name')||'').toString().trim();
  if(!name){ msg.className='msg err'; msg.textContent='⚠️ Falta el nombre de la receta.'; return; }

  // backend espera allergens como string "A, B" (compatibilidad)
  fd.set('allergens', allergens.join(', '));

  msg.className='msg'; msg.textContent='Creando...';
  const res=await fetch('/api/recipe/create',{method:'POST', body:fd});
  const data=await res.json().catch(()=>({}));

  if(!res.ok || !data.ok){ msg.className='msg err'; msg.textContent=(data.error || data.detail || ('Error '+res.status)); return; }

  // añadir al desplegable inmediatamente
  const sel=document.getElementById('recipeSelect');
  if(sel){
    const opt=document.createElement('option');
    opt.value=String(data.recipe_id);
    opt.textContent=name;
    sel.appendChild(opt);
    sel.value=String(data.recipe_id);
  }

  // reset UI
  form.reset();
  document.querySelectorAll('#allergenGrid input').forEach(i=>i.checked=false);
  updateCodePreview();
  document.getElementById('newRecipePanel').style.display='none';
  msg.className='msg ok'; msg.textContent='✅ Receta creada y cargada.';

  // Abre la ficha y permite cargar ingredientes en el mismo paso
  if (data.recipe) {
    renderRecipe(data.recipe);
    // scroll al bloque de ingredientes
    setTimeout(()=>{
      const btn=document.getElementById('addIngredientBtn');
      if(btn) btn.scrollIntoView({behavior:'smooth', block:'start'});
    }, 50);
  } else {
    await loadRecipe(data.recipe_id);
  }
});

// Carga ficha por API y la renderiza (fallback / acceso directo)
async function loadRecipe(recipeId){
  const resp=await fetch(`/api/recipe/${recipeId}`);
  const data=await resp.json().catch(()=>({}));
  if(!resp.ok || !data.ok){
    showToast(data.error || data.detail || ('Error '+resp.status));
    return;
  }
  renderRecipe(data.recipe);
}

function openMinMax(itemId,itemName,unit,minQty,maxQty){
  document.getElementById('minmax_item_id').value=itemId;
  const titleEl = document.getElementById('minMaxTitle');
  titleEl.textContent=`${itemName} (${unit})`;
  titleEl.dataset.baseUnit = unit;
  document.getElementById('minmax_min').value=minQty;
  document.getElementById('minmax_max').value=maxQty;
  const unitSel=document.getElementById('minmax_unit');
  const u2=document.getElementById('minmax_unit_label_max');
  if(unitSel){
    const opts = unitOptionsFor(unit);
    unitSel.innerHTML = opts.map(u=>`<option value="${u}">${u}</option>`).join('');
    unitSel.value = unit;
  }
  if(u2) u2.textContent=unit;
  document.getElementById('minMaxMsg').textContent='';
  document.getElementById('minMaxModal').style.display='flex';
}
function closeMinMax(){ document.getElementById('minMaxModal').style.display='none'; }
on('minMaxForm','submit', async (e)=>{
  e.preventDefault(); const fd=new FormData(e.target); const itemId=fd.get('item_id');
  const unit = document.getElementById('minmax_unit')?.value || 'g';
  const baseUnit = document.getElementById('minMaxTitle').dataset.baseUnit || 'g';
  // convert to base
  const minV = Number(fd.get('min_qty')||0);
  const maxV = Number(fd.get('max_qty')||0);
  let factor = 1.0;
  if(baseUnit==='g' && unit==='kg') factor = 1000.0;
  if(baseUnit==='g' && unit==='kg') factor = 1000.0;
  fd.set('min_qty', String(minV * factor));
  fd.set('max_qty', String(maxV * factor));
  fd.delete('item_id');
  const msg=document.getElementById('minMaxMsg'); msg.textContent='Guardando...';
  const r=await fetch(`/api/item/${itemId}/minmax`,{method:'POST', body:fd}); const d=await r.json();
  if(d.ok){ msg.className='msg ok'; msg.textContent=d.message; closeMinMax();
    // refresh stocks
    const cid = document.getElementById('globalCenterFilter')?.value || '0';
    const url = cid==='0' ? '/api/stocks' : `/api/stocks?center_id=${cid}`;
    const rr = await fetch(url); const jj = await rr.json();
    if(jj.ok){ renderStocksTable(jj.stocks); }
  }
  else { msg.className='msg err'; msg.textContent=d.error||'Error'; }
});

function unitOptionsForBase(base){
  const b=(base||'').toLowerCase();
  if(b==='g') return ['g','kg'];
  
  if(b==='ud') return ['ud'];
  return [b || 'ud'];
}


async function openRecipeById(recipeId){
  const res = await fetch('/api/recipe/'+recipeId);
  const data = await res.json();
  if(data.ok){
    renderRecipe(data.recipe);
    window.scrollTo(0,0);
  } else {
    alert(data.error || 'No se pudo cargar la receta');
  }
}

function initIngredientUI(recipe){
  const toggle=document.getElementById('addIngToggle');
  const form=document.getElementById('addIngForm');
  const cancel=document.getElementById('cancelIngBtn');
  const search=document.getElementById('ingSearch');
  const suggestions=document.getElementById('ingSuggestions');
  const unitSel=document.getElementById('ingUnit');
  const itemIdHidden=document.getElementById('ingItemId');
  const msg=document.getElementById('ingMsg');

  if(!toggle || !form) return;

  toggle.onclick = ()=>{
    form.style.display = form.style.display==='none' ? 'block' : 'none';
    if(form.style.display==='block'){ search.focus(); }
  };
  if(cancel){
    cancel.onclick = ()=>{ form.style.display='none'; if(suggestions) suggestions.style.display='none'; };
  }

  search.oninput = ()=>{
    const q=(search.value||'').trim().toLowerCase();
    if(q.length<2){ suggestions.style.display='none'; return; }
    const starts = ITEMS.filter(it=>String(it.name||'').toLowerCase().startsWith(q));
      const contains = ITEMS.filter(it=>!String(it.name||'').toLowerCase().startsWith(q) && String(it.name||'').toLowerCase().includes(q));
      const list = starts.concat(contains).slice(0,15);
    suggestions.innerHTML = list.map(it=>(
      `<div class="sug" data-id="${it.id}" data-unit="${it.unit}">${it.name} <span class="muted">(${it.unit})</span></div>`
    )).join('');
    suggestions.style.display='block';
  };
  suggestions.onclick = (e)=>{
    const el=e.target.closest('.sug'); if(!el) return;
    const id=el.getAttribute('data-id');
    const u=el.getAttribute('data-unit');
    itemIdHidden.value = id;
    unitSel.innerHTML = unitOptionsForBase(u).map(x=>`<option value="${x}">${x}</option>`).join('');
    search.value = el.textContent.replace(/\(.*\)/,'').trim();
    suggestions.style.display='none';
  };

  form.onsubmit = async (e)=>{
    e.preventDefault();
    if(!itemIdHidden.value){ msg.className='msg err'; msg.textContent='Selecciona un ingrediente'; return; }
    msg.className='msg'; msg.textContent='Guardando...';
    const fd=new FormData(form);
    const res=await fetch(`/api/recipe/${recipe.id}/ingredient`, {method:'POST', body: fd});
    const data=await res.json();
    if(!data.ok){ msg.className='msg err'; msg.textContent=data.error||'Error'; return; }
    msg.className='msg ok'; msg.textContent='Ingrediente añadido';
    renderRecipe(data.recipe);
  };

  document.querySelectorAll('.delIngBtn').forEach(btn=>{
    btn.onclick = async ()=>{
      const ingId=btn.getAttribute('data-ing');
      if(!confirm('Eliminar ingrediente?')) return;
      const res=await fetch(`/api/recipe/${recipe.id}/ingredient/${ingId}`, {method:'DELETE'});
      const data=await res.json();
      if(data.ok) renderRecipe(data.recipe);
    };
  });
}

function initAdminPriceUI(){
  const provSel = document.getElementById('priceSupplier');
  const tbody = document.getElementById('priceTableBody') || document.querySelector('#pricesTable tbody');
  const search = document.getElementById('priceItemSearch');
  const sugg = document.getElementById('priceItemSuggestions');
  const hid = document.getElementById('priceItemId');
  const priceInput = document.getElementById('priceInput');
  const unitSel = document.getElementById('purchaseUnit');
  const factorInput = document.getElementById('purchaseFactor');
  const prefSel = document.getElementById('isPreferredSel');

  function ensureAllOption(){
    if(!provSel) return;
    if(!provSel.querySelector('option[value="ALL"]')){
      const opt=document.createElement('option');
      opt.value='ALL'; opt.textContent='Todos';
      provSel.insertBefore(opt, provSel.firstChild);
    }
    if(!provSel.value) provSel.value='ALL';
  }

  function filterTable(){
    if(!provSel || !tbody) return;
    const p = (provSel.value || '').trim();
    const rows = Array.from(tbody.querySelectorAll('tr'));
    if(p==='' || p==='ALL'){
      rows.forEach(tr=>tr.style.display='');
      return;
    }
    rows.forEach(tr=>{
      const tp = (tr.getAttribute('data-provider') || tr.children[0]?.textContent || '').trim();
      tr.style.display = (tp===p) ? '' : 'none';
    });
  }

  function addShowAllBtn(){
    if(!provSel) return;
    if(document.getElementById('priceShowAllBtn')) return;
    const btn=document.createElement('button');
    btn.type='button'; btn.id='priceShowAllBtn'; btn.textContent='Ver todos';
    btn.style.marginLeft='8px';
    provSel.parentElement.appendChild(btn);
    btn.addEventListener('click', ()=>{
      provSel.value='ALL';
      filterTable();
    });
  }

  function unitOptionsForBase(base){
    const b=(base||'').toLowerCase();
    if(b==='g' || b==='kg' || b==='ml' || b==='l') return ['kg','g'];
    if(b==='ud') return ['ud'];
    return [b || 'ud'];
  }

  function findRow(providerName, articleName){
    if(!tbody) return null;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    return rows.find(tr=>{
      const p=(tr.getAttribute('data-provider') || tr.children[0]?.textContent || '').trim();
      const a=(tr.getAttribute('data-article') || tr.children[1]?.textContent || '').trim();
      return p===providerName && a===articleName;
    }) || null;
  }

  function autofill(){
    if(!provSel || !search) return;
    const p = (provSel.value||'').trim();
    if(p==='' || p==='ALL') return;
    const a = (search.value||'').trim();
    if(!a) return;
    const row = findRow(p,a);
    if(!row) return;
    const cells = row.querySelectorAll('td');
    const priceTxt = cells[2]?.textContent?.trim() || '';
    const unitTxt = cells[3]?.textContent?.trim() || '';
    const factorTxt = cells[4]?.textContent?.trim() || '';
    if(priceInput && priceTxt) priceInput.value = priceTxt.replace(',','.');
    if(unitSel && unitTxt) unitSel.value = unitTxt;
    if(factorInput && factorTxt) factorInput.value = factorTxt.replace(',','.');
    if(prefSel){
      const pref = (cells[5]?.textContent||'').toLowerCase().includes('sí') || (cells[5]?.textContent||'').toLowerCase().includes('true');
      prefSel.value = pref ? '1' : '0';
    }
  }

  ensureAllOption();
  addShowAllBtn();
  filterTable();

  if(provSel){
    provSel.addEventListener('change', ()=>{
      filterTable();
      autofill();
    });
  }

  if(search && sugg && hid){
    const renderPriceItemSuggestions = ()=>{
      const q=(search.value||'').trim().toLowerCase();
      if(q.length<1){ sugg.style.display='none'; sugg.innerHTML=''; return; }
      const starts = ITEMS.filter(it=>String(it.name||'').toLowerCase().startsWith(q));
      const contains = ITEMS.filter(it=>!String(it.name||'').toLowerCase().startsWith(q) && String(it.name||'').toLowerCase().includes(q));
      const list = starts.concat(contains).slice(0,12);
      if(!list.length){ sugg.innerHTML=''; sugg.style.display='none'; return; }
      sugg.innerHTML = list.map(it=>(
        `<button type="button" class="sug" data-id="${it.id}" data-unit="${it.unit}" data-name="${String(it.name||'').replace(/"/g,'&quot;')}"><span>${it.name}</span><small>(${it.unit})</small></button>`
      )).join('');
      sugg.style.display='block';
    };
    search.addEventListener('input', renderPriceItemSuggestions);
    search.addEventListener('focus', renderPriceItemSuggestions);
    search.addEventListener('keydown', (e)=>{
      if(e.key==='Enter'){
        const first = sugg.querySelector('[data-id]');
        if(first){ e.preventDefault(); first.click(); }
      }
    });
    sugg.addEventListener('mousedown', e=>e.preventDefault());
    sugg.addEventListener('click', (e)=>{
      const el=e.target.closest('[data-id]'); if(!el) return;
      hid.value = el.getAttribute('data-id');
      const baseUnit = el.getAttribute('data-unit');
      search.value = el.getAttribute('data-name') || el.textContent.replace(/\(.*\)/,'').trim();
      sugg.style.display='none';
      sugg.innerHTML='';
      if(unitSel){
        const opts=unitOptionsForBase(baseUnit);
        unitSel.value = opts[0] || unitSel.value;
      }
      autofill();
    });
    document.addEventListener('click', function(e){ if(e.target!==search && !sugg.contains(e.target)){ sugg.style.display='none'; } });
  }
}

async function createDraftAndOpen(){
  const p=document.getElementById('newRecipePanel');
  if(p){ p.style.display='block'; p.scrollIntoView({behavior:'smooth', block:'start'}); }
}

// ServiceWorker desactivado temporalmente (evita que Safari sirva versiones antiguas)

// Init extra UI
initAdminPriceUI();
bindItemAutocomplete();
refreshMovementUnit();
renderSuppliers();
renderSupplierPrices();
wireAdminQuickFilters();

// Preserve Admin filters across auto-refresh
function saveAdminUIState(){
  try{
    const pf=document.getElementById('pricesFilter');
    if(pf) sessionStorage.setItem('admin_pricesFilter', pf.value||'');
    const itf=document.getElementById('itemsFilter');
    if(itf) sessionStorage.setItem('admin_itemsFilter', itf.value||'');
  }catch(e){}
}
function restoreAdminUIState(){
  try{
    const pf=document.getElementById('pricesFilter');
    const v=sessionStorage.getItem('admin_pricesFilter');
    if(pf && v!==null){
      pf.value=v;
      pf.dispatchEvent(new Event('input', {bubbles:true}));
      sessionStorage.removeItem('admin_pricesFilter');
    }

    const itf=document.getElementById('itemsFilter');
    const iv=sessionStorage.getItem('admin_itemsFilter');
    if(itf && iv!==null){
      itf.value=iv;
      itf.dispatchEvent(new Event('input', {bubbles:true}));
      // Si no hay "flash" pendiente, lo limpiamos igual (no queremos persistencia indefinida).
    }

    // Si venimos de guardar un artículo, lo hacemos visible y lo destacamos.
    const lastId=sessionStorage.getItem('admin_lastSavedItemId');
    if(lastId){
      const form = document.querySelector(`#itemsTable form[action="/item/${lastId}/update_form"]`);
      const tr = form ? form.closest('tr') : null;
      if(tr){
        tr.classList.add('row-flash');
        tr.scrollIntoView({behavior:'smooth', block:'center'});
        setTimeout(()=>tr.classList.remove('row-flash'), 1600);
      }
      sessionStorage.removeItem('admin_lastSavedItemId');
      sessionStorage.removeItem('admin_itemsFilter');
    }else{
      if(iv!==null) sessionStorage.removeItem('admin_itemsFilter');
    }
  }catch(e){}
}

function parseLocaleNum(v){
  const s=(v||'').toString().trim().replace(/\s+/g,'').replace(/\.(?=\d{3}(\D|$))/g,'').replace(',', '.');
  const n=parseFloat(s);
  return Number.isFinite(n)?n:NaN;
}
function formatHumanNum(n){
  if(!Number.isFinite(n)) return '';
  let s=(Math.round(n*100)/100).toFixed(2);
  s=s.replace(/\.00$/,'').replace(/(\.\d)0$/,'$1');
  return s.replace('.', ',');
}
function bindOcrAmountCalc(){
  document.querySelectorAll('[data-ocr-line-row]').forEach((row)=>{
    const qty=row.querySelector('[data-ocr-qty]');
    const price=row.querySelector('[data-ocr-price]');
    const amount=row.querySelector('[data-ocr-amount]');
    if(!qty || !price || !amount) return;
    const recalc=()=>{
      const q=parseLocaleNum(qty.value);
      const p=parseLocaleNum(price.value);
      if(Number.isFinite(q) && Number.isFinite(p)) amount.value=formatHumanNum(q*p);
    };
    qty.addEventListener('input', recalc);
    price.addEventListener('input', recalc);
  });
}
restoreAdminUIState();

const supplierFormEl = document.getElementById('supplierForm');
if(supplierFormEl) supplierFormEl.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const fd=new FormData(e.target);
  const res=await fetch('/api/suppliers',{method:'POST',body:fd});
  const j=await res.json();
  const msg=document.getElementById('supplierMsg');
  if(j.ok){
    msg.textContent = 'Proveedor creado.';
    saveAdminUIState();
    window.location.reload();
  } else {
    msg.textContent = (j.error||'Error');
  }
});
const supplierPriceFormEl = document.getElementById('supplierPriceForm');
if(supplierPriceFormEl) supplierPriceFormEl.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const fd=new FormData(e.target);
  const itemId=fd.get('item_id');
  const msg=document.getElementById('spMsg');
  if(!itemId){
    if(msg) msg.textContent = 'Selecciona un artículo del listado.';
    return;
  }
  const res=await fetch(`/api/item/${itemId}/supplier_price`,{method:'POST',body:fd});
  const j=await res.json();
  if(j.ok){
    msg.textContent = 'Precio guardado.';
    saveAdminUIState();
    window.location.reload();
  } else {
    msg.textContent = (j.error||'Error');
  }
});


function getAllergensString(){
  try{
    const checked = Array.from(document.querySelectorAll('input[name="allergens_list"]:checked'));
    return checked.map(el=>el.value).join(", ");
  }catch(e){ return ""; }
}

function attachRecipeDraft(form){
  try{
    const container = form.querySelector('#recipe_draft_fields') || form;
    const ensureHidden = (name)=>{
      let el = form.querySelector('input[name="'+name+'"]');
      if(!el){
        el = document.createElement('input');
        el.type='hidden';
        el.name=name;
        container.appendChild(el);
      }
      return el;
    };
    const getVal = (id)=>{ const el=document.getElementById(id); return el? (el.value||""):""; };
    ensureHidden('draft_name').value = getVal('recipe_name');
    ensureHidden('draft_category').value = getVal('recipe_category');
    ensureHidden('draft_subcategory').value = getVal('recipe_subcategory');
    ensureHidden('draft_yield_portions').value = getVal('recipe_yield');
    ensureHidden('draft_yield_final_qty').value = getVal('recipe_yield_final_qty');
    ensureHidden('draft_yield_final_unit').value = getVal('recipe_yield_final_unit');
    ensureHidden('draft_waste_pct').value = getVal('recipe_waste');
    ensureHidden('draft_contingency_pct').value = getVal('recipe_contingency');
    // Backend espera draft_prep_steps (acepta también draft_steps por compatibilidad)
    ensureHidden('draft_prep_steps').value = getVal('recipe_steps');
    ensureHidden('draft_steps').value = getVal('recipe_steps');
    ensureHidden('draft_allergens').value = getAllergensString();
    // Backend usa draft_target_food_cost_pct / draft_target_margin_pct / draft_manual_price
    ensureHidden('draft_target_food_cost_pct').value = getVal('recipe_tfc');
    ensureHidden('draft_food_cost_target_pct').value = getVal('recipe_tfc');
    ensureHidden('draft_target_margin_pct').value = getVal('recipe_tm');
    ensureHidden('draft_margin_target_pct').value = getVal('recipe_tm');
    ensureHidden('draft_manual_price').value = getVal('recipe_price');
    ensureHidden('draft_price_manual').value = getVal('recipe_price');
    ensureHidden('draft_is_subrecipe').value = getVal('recipe_type');
    return true;
  }catch(e){ console.log(e); return true; }
}


function initFlowPreserver(){
  try{
    const forms = document.querySelectorAll('form.preserve-flow');
    forms.forEach(form=>{
      if(form.dataset.flowBound==='1') return;
      form.dataset.flowBound='1';
      form.addEventListener('submit', ()=>{
        try{
          const targetId = form.getAttribute('data-flow-target') || '';
          const active = document.activeElement;
          const focusName = active && form.contains(active) ? (active.name || active.id || '') : '';
          const row = form.closest('[data-flow-row-id],[data-ocr-line-row],[data-recipe-line-row],tr.recipe-ing-row');
          const payload = {
            page: document.body.getAttribute('data-page') || '',
            targetId,
            scrollY: window.scrollY || 0,
            focusName,
            rowId: form.getAttribute('data-flow-row-id') || (row ? row.getAttribute('id') : ''),
            at: Date.now()
          };
          sessionStorage.setItem('flow_preserve', JSON.stringify(payload));
        }catch(e){}
      });
    });

    const raw = sessionStorage.getItem('flow_preserve');
    if(!raw) return;
    const info = JSON.parse(raw || '{}');
    if(!info || (Date.now() - (info.at||0) > 15000)) { sessionStorage.removeItem('flow_preserve'); return; }
    sessionStorage.removeItem('flow_preserve');
    const restoreFlow = ()=>{
      if(info.rowId){
        const row = document.getElementById(info.rowId);
        if(row){
          const y = Math.max(0, row.getBoundingClientRect().top + window.scrollY - 140);
          window.scrollTo(0, y);
        } else if(Number.isFinite(info.scrollY)){
          window.scrollTo(0, Number(info.scrollY)||0);
        }
      } else if(Number.isFinite(info.scrollY)){
        window.scrollTo(0, Number(info.scrollY)||0);
      }
      if(info.focusName){
        const selector = `[name="${CSS.escape(info.focusName)}"], #${CSS.escape(info.focusName)}`;
        const tgt = document.querySelector(selector);
        if(tgt){ try{ tgt.focus(); tgt.select && tgt.select(); }catch(e){} }
      }
    };
    requestAnimationFrame(restoreFlow);
    setTimeout(restoreFlow, 90);
    setTimeout(restoreFlow, 220);
    setTimeout(restoreFlow, 420);
    setTimeout(restoreFlow, 700);
  }catch(e){}
}

document.addEventListener('DOMContentLoaded', ()=>{ initFlowPreserver(); bindOcrAmountCalc(); });

document.addEventListener('DOMContentLoaded', ()=>{
  const pf=document.getElementById('pricesFilter');
  if(pf){ pf.addEventListener('input', applyPricesFilter); }
});

document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('[data-scope-global="1"]').forEach((box)=>{
    const wrap=box.closest('form') || document;
    const refresh=()=>{
      wrap.querySelectorAll('[data-scope-centers="1"] input[type="checkbox"]').forEach(cb=>{
        cb.disabled = box.checked;
        if(box.checked){ cb.checked = false; }
        const line = cb.closest('.checkline');
        if(line){ line.classList.toggle('is-disabled', box.checked); }
      });
    };
    box.addEventListener('change', refresh);
    refresh();
  });
});

function toggleRecipeComponentType(sel){
  const form = sel.closest('form');
  if(!form) return;
  const item = form.querySelector('[data-component-item="1"]');
  const sub = form.querySelector('[data-component-subrecipe="1"]');
  const isSub = (sel.value||'item') === 'subrecipe';
  if(item) item.style.display = isSub ? 'none' : '';
  if(sub) sub.style.display = isSub ? '' : '';
  if(sub) sub.style.display = isSub ? '' : 'none';
  try{
    const unitSel = form.querySelector('select[name="qty_unit"]');
    if(!unitSel) return;
    if(isSub){
      const subSel = form.querySelector('select[name="subrecipe_id"] option:checked');
      const yu = ((subSel && subSel.dataset && subSel.dataset.yieldUnit) || 'g').toLowerCase();
      if(yu==='ud') applySelectOptions(unitSel, 'ud');
      else applySelectOptions(unitSel, 'g');
    }
  }catch(_e){}
}
(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

// ---- Smart item picker ----
// Smart item picker: works even when iOS/Safari datalist suggestions are unreliable.
(function(){
  const MIN_CHARS = 1;
  const DEBOUNCE_MS = 120;
  const MAX_ITEMS = 20;
  function debounce(fn, ms){ let t=null; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); }; }

  function mkBox(){
    const box = document.createElement('div');
    box.className = 'smartbox';
    box.style.position = 'absolute';
    box.style.zIndex = '9999';
    box.style.display = 'none';
    box.style.background = 'var(--panel, #111)';
    box.style.border = '1px solid rgba(255,255,255,0.12)';
    box.style.borderRadius = '10px';
    box.style.maxHeight = '240px';
    box.style.overflow = 'auto';
    box.style.boxShadow = '0 10px 24px rgba(0,0,0,0.35)';
    document.body.appendChild(box);
    return box;
  }

  const box = mkBox();
  let activeInput = null;

  function positionBox(input){
    const r = input.getBoundingClientRect();
    box.style.left = (window.scrollX + r.left) + 'px';
    box.style.top = (window.scrollY + r.bottom + 6) + 'px';
    box.style.width = r.width + 'px';
  }

  function hide(){ box.style.display='none'; box.innerHTML=''; activeInput=null; }

  async function fetchItems(q){
    const url = '/api/items?q=' + encodeURIComponent(q) + '&limit=' + MAX_ITEMS;
    const res = await fetch(url, {headers:{'Accept':'application/json'}});
    const js = await res.json();
    return (js && js.items) ? js.items : [];
  }

  function render(items){
    if(!activeInput) return;
    box.innerHTML='';
    if(!items.length){ hide(); return; }
    for(const it of items){
      const row = document.createElement('div');
      row.className = 'smartrow';
      row.style.padding = '10px 12px';
      row.style.cursor = 'pointer';
      row.style.borderBottom = '1px solid rgba(255,255,255,0.08)';
      row.textContent = it.name + ' [' + it.unit + ']';
      row.addEventListener('mousedown', (e)=>{ e.preventDefault(); });
      row.addEventListener('click', ()=>{
        activeInput.value = it.name + ' [#' + it.id + ']';
        try{
          const form = activeInput.closest('form');
          if(form){
            const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
            if(hid) hid.value = String(it.id);
            const sel = form.querySelector('select[name="qty_unit"][data-smart-unit]');
            if(sel){
              const u = (it.unit||'').toLowerCase();
              if(u==='g'){
                sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>';
                sel.value = 'g';
              }else if(u==='ml'){
                sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>';
                sel.value = 'g';
              }else{
                sel.innerHTML = `<option value="${u}">${u}</option>`;
                sel.value = u || 'ud';
              }
            }
          }
        }catch(_){ /* silent */ }
        hide();
      });
      box.appendChild(row);
    }
    box.style.display='block';
    positionBox(activeInput);
  }

  const onInput = debounce(async (e)=>{
    const input = e.target;
    activeInput = input;
    const q = (input.value||'').trim();
    if(q.length < MIN_CHARS){ hide(); return; }
    try{
      const items = await fetchItems(q);
      render(items);
    }catch(_){ /* silent */ }
  }, DEBOUNCE_MS);

  function hook(input){
    input.addEventListener('input', (e)=>{
      try{
        const form = e.target.closest('form');
        if(form){
          const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
          if(hid) hid.value = '';
        }
      }catch(_){}
      onInput(e);
    });
    input.addEventListener('change', (e)=>{
      try{
        const form = e.target.closest('form');
        const parsed = parseItemIdFromText(e.target.value||'');
        if(form){
          const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
          if(hid) hid.value = parsed ? String(parsed) : '';
        }
      }catch(_){}
    });
    input.addEventListener('focus', (e)=>{ activeInput=e.target; positionBox(activeInput); });
    input.addEventListener('blur', ()=>{ setTimeout(hide, 120); });
  }

  document.querySelectorAll('input.smart-item').forEach(hook);
  window.addEventListener('scroll', ()=>{ if(activeInput) positionBox(activeInput); }, {passive:true});
  window.addEventListener('resize', ()=>{ if(activeInput) positionBox(activeInput); });

  // Event delegation — captura .smart-item añadidos dinámicamente (ej: producción con detail)
  const _hooked = new WeakSet();
  document.addEventListener('focusin', function(e){
    const inp = e.target;
    if(!inp || !inp.classList || !inp.classList.contains('smart-item')) return;
    if(_hooked.has(inp)) return;
    _hooked.add(inp);
    hook(inp);
    if((inp.value||'').trim().length >= MIN_CHARS){
      activeInput = inp;
      positionBox(inp);
      fetchItems(inp.value.trim()).then(render).catch(()=>{});
    }
  });
})();

// Admin items filter (Artículos precio actual)
(function(){
  function applyAdminItemsFilter(){
    const f = document.getElementById('itemsFilter');
    const tbl = document.getElementById('itemsTable');
    if(!f || !tbl) return;
    const q = (f.value || '').toLowerCase().trim();
    const rows = tbl.querySelectorAll('tbody tr');
    rows.forEach(tr=>{
      const inp = tr.querySelector('input[name="name"]');
      const txt = (inp && inp.value ? inp.value : '').toLowerCase();
      tr.style.display = (!q || txt.includes(q)) ? '' : 'none';
    });
  }
  document.addEventListener('input', function(e){
    if(e.target && e.target.id === 'itemsFilter') applyAdminItemsFilter();
  });
  document.addEventListener('focusin', function(e){
    if(e.target && e.target.id === 'itemsFilter') applyAdminItemsFilter();
  });
  window.addEventListener('load', applyAdminItemsFilter);
})();

// Admin Artículos: al guardar una fila, conservar filtro y hacer "flash" + scroll a la fila guardada.
(function(){
  const tbl = document.getElementById('itemsTable');
  if(!tbl) return;
  tbl.querySelectorAll('form[action^="/item/"][action$="/update_form"]').forEach(form=>{
    form.addEventListener('submit', ()=>{
      try{
        const m = (form.getAttribute('action')||'').match(/\/item\/(\d+)\/update_form/);
        if(m && m[1]) sessionStorage.setItem('admin_lastSavedItemId', m[1]);
        // Guarda filtro actual (si existe)
        const itf=document.getElementById('itemsFilter');
        if(itf) sessionStorage.setItem('admin_itemsFilter', itf.value||'');
      }catch(e){}
    });
  });
})();


(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

// ---- Photo viewer ----
function openPhoto(src){
    const m=document.getElementById('photoModal');
    const img=document.getElementById('modalImg');
    if(!m||!img) return;
    img.src=src;
    m.style.display='block';
    document.body.style.overflow='hidden';
  }
  function closePhoto(){
    const m=document.getElementById('photoModal');
    const img=document.getElementById('modalImg');
    if(!m||!img) return;
    m.style.display='none';
    img.src='';
    document.body.style.overflow='';
  }

  // Stock search (client-side)
  function filterStock(){
    const q = (document.getElementById('stockSearch')?.value || '').toLowerCase().trim();
    const rows = document.querySelectorAll('#stock table tbody tr');
    rows.forEach(r=>{
      const a = (r.getAttribute('data-article')||'') + ' ' + (r.getAttribute('data-warehouse')||'') + ' ' + (r.getAttribute('data-center')||'');
      r.style.display = (!q || a.includes(q)) ? '' : 'none';
    });
  }
  document.addEventListener('input', (e)=>{
    if(e.target && e.target.id==='stockSearch') filterStock();
  });

  // Live recipe pricing preview (no save needed). Updates only the PVP fields.
  (function(){
    const calc = document.getElementById('recipeCalc');
    if(!calc) return;
    const costAdj = parseFloat(calc.dataset.costAdjusted || '0') || 0;
    const vatRateRaw = parseFloat(calc.dataset.vatRate || '0.10');
    const vatRate = (isFinite(vatRateRaw) ? (vatRateRaw > 1 ? vatRateRaw/100 : vatRateRaw) : 0.10) || 0.10;

    let t=null;
    function update(){
      const tfc = parseFloat(document.getElementById('recipe_tfc')?.value || '0') || 0;
      const manual = parseFloat(document.getElementById('recipe_price')?.value || '0') || 0;
      let priceEx = 0;
      if(manual > 0){
        priceEx = manual;
      } else if(tfc > 0){
        priceEx = costAdj / (tfc/100);
      }
      const priceVat = priceEx * vatRate;
      const priceInc = priceEx + priceVat;
      const set = (id, v)=>{
        const el=document.getElementById(id);
        if(el) el.textContent = ((isFinite(v) ? v : 0).toFixed(2) + ' €');
      };
      set('calc_price_ex', priceEx);
      set('calc_price_vat', priceVat);
      set('calc_price_inc', priceInc);
    }
    function schedule(){
      if(t) clearTimeout(t);
      t=setTimeout(update, 150);
    }
    document.addEventListener('input', (e)=>{
      if(!e.target) return;
      if(e.target.id==='recipe_tfc' || e.target.id==='recipe_price') schedule();
    });
    update();
  })();

(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

// ---- Elaborados en stock ----
// ELABORADOS — stock de producciones con porciones
// ============================================================
// ELABORADOS — carga y renderiza el panel de stock de producciones
// ============================================================
function loadElaborados() {
  const panel = document.getElementById('elaboradosContent');
  if (!panel) return;

  const url = new URL(window.location.href);
  const centerId = url.searchParams.get('center_id') || '0';

  panel.innerHTML = '<div class="muted" style="padding:8px 0;">Cargando elaborados...</div>';

  fetch(`/api/elaborados?center_id=${centerId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok || !data.elaborados || data.elaborados.length === 0) {
        panel.innerHTML = '<div class="muted" style="padding:12px 0;font-size:13px;">No hay elaborados en stock. Cuando confirmes producciones aparecerán aquí automáticamente.</div>';
        return;
      }

      const rows = data.elaborados.map(e => {
        const stockFmt = formatElabQty(e.stock_qty, e.unit);

        // Porciones: si el artículo está en ud/raciones usa el stock directamente
        // Si está en g/ml usa la receta para calcular
        let porcionesFmt = '—';
        if (e.porciones_disponibles != null) {
          const n = Number(e.porciones_disponibles);
          porcionesFmt = `<strong style="font-size:15px;color:var(--gold-3);">${n % 1 === 0 ? n : n.toFixed(1)}</strong> <span class="muted" style="font-size:11px;">raciones</span>`;
        }

        // Gramaje por ración
        let gramajeFmt = '';
        if (e.gramaje_porcion != null && e.gramaje_porcion > 0) {
          gramajeFmt = `<div class="muted" style="font-size:11px;margin-top:2px;">${formatElabQty(e.gramaje_porcion, e.unit)}/ración</div>`;
        }

        // Valor económico
        let valorFmt = '';
        if (e.stock_value && e.stock_value > 0) {
          valorFmt = `<div class="muted" style="font-size:11px;margin-top:2px;">Valor: ${e.stock_value.toFixed(2)} €</div>`;
        }

        // Receta con link
        const receta = e.recipe_name
          ? `<a class="mini" href="/?page=recetas&recipe_search=${encodeURIComponent(e.recipe_name)}">${e.recipe_name}</a>`
          : '<span class="muted" style="font-size:11px;">Sin receta asociada</span>';

        // Producción origen con link
        const prodId   = e.last_prod_id;
        const prodDate = (e.last_production_at || e.last_prod_at || '').slice(0, 10);
        const prodNote = e.last_prod_note || '';
        const prodFmt  = prodId
          ? `<a class="mini" href="/?page=producciones&pid=${prodId}">Prod. #${prodId}</a><div class="muted" style="font-size:11px;margin-top:2px;">${prodDate}${prodNote ? '<br>' + prodNote.slice(0,40) : ''}</div>`
          : '<span class="muted" style="font-size:11px;">—</span>';

        return `<tr>
          <td>
            <strong style="font-size:13px;">${e.item_name}</strong>
            <div class="muted" style="font-size:11px;">${e.center_name} · ${e.warehouse_name}</div>
          </td>
          <td>
            <strong>${stockFmt}</strong>
            ${valorFmt}
          </td>
          <td>
            ${porcionesFmt}
            ${gramajeFmt}
          </td>
          <td>${receta}</td>
          <td>${prodFmt}</td>
        </tr>`;
      }).join('');

      // Totales resumidos
      const totalElabs = data.elaborados.length;
      const totalPorciones = data.elaborados.reduce((acc, e) => acc + (e.porciones_disponibles || 0), 0);
      const totalValor = data.elaborados.reduce((acc, e) => acc + (e.stock_value || 0), 0);
      const resumen = [
        `${totalElabs} elaborado${totalElabs !== 1 ? 's' : ''}`,
        totalPorciones > 0 ? `${Math.round(totalPorciones)} raciones totales` : '',
        totalValor > 0 ? `Valor aprox: ${totalValor.toFixed(2)} €` : '',
      ].filter(Boolean).join(' · ');

      panel.innerHTML = `
        <div class="muted" style="font-size:12px;margin-bottom:10px;">${resumen}</div>
        <div class="table-wrap" style="max-height:480px;">
          <table>
            <thead>
              <tr>
                <th>Elaborado</th>
                <th>Stock actual</th>
                <th>Porciones</th>
                <th>Receta</th>
                <th>Producción origen</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div style="text-align:right;margin-top:8px;">
          <button class="mini" onclick="loadElaborados()" style="opacity:.7;">↺ Actualizar</button>
        </div>`;
    })
    .catch(() => {
      panel.innerHTML = '<div class="notice warn mt"><span class="notice-icon">⚠</span><span class="notice-text">No se pudieron cargar los elaborados.</span></div>';
    });
}


function formatElabQty(qty, unit) {
  if (qty == null) return '—';
  const n = Number(qty);
  if (unit === 'g' && n >= 1000) return (n / 1000).toFixed(2) + ' kg';
  if (unit === 'g' && n >= 1000) return (n / 1000).toFixed(2) + ' kg';
  if (unit === 'g') return n.toFixed(0) + ' ' + unit;
  return n.toFixed(2) + ' ' + (unit || '');
}

// Cargar elaborados cuando se entra a Stock
document.addEventListener('DOMContentLoaded', function() {
  if (document.body.dataset.page === 'stock') {
    loadElaborados();
  }
});

on('viewRecipeBtn','click', async ()=>{
  const id=document.getElementById('recipeSelect').value; const msg=document.getElementById('recipeMsg');
  if(!id){ msg.className='msg err'; msg.textContent='Selecciona una receta'; return; }
  msg.className='msg'; msg.textContent='Cargando...';
  const res=await fetch('/api/recipe/'+id); const data=await res.json();
  if(!data.ok){ msg.className='msg err'; msg.textContent=data.error||'Error'; return; }
  msg.className='msg ok'; msg.textContent='Ficha cargada'; renderRecipe(data.recipe);
});

on('newRecipeBtn','click', async ()=>{ await createDraftAndOpen(); });

on('newRecipeForm','submit', async (e)=>{
  e.preventDefault();
  const form=e.target;
  const msg=document.getElementById('newRecipeMsg');

  // recopila alérgenos
  const allergens=[...document.querySelectorAll('#allergenGrid input:checked')].map(x=>x.value);
  const fd=new FormData(form);

  const name=(fd.get('name')||'').toString().trim();
  if(!name){ msg.className='msg err'; msg.textContent='⚠️ Falta el nombre de la receta.'; return; }

  // backend espera allergens como string "A, B" (compatibilidad)
  fd.set('allergens', allergens.join(', '));

  msg.className='msg'; msg.textContent='Creando...';
  const res=await fetch('/api/recipe/create',{method:'POST', body:fd});
  const data=await res.json().catch(()=>({}));

  if(!res.ok || !data.ok){ msg.className='msg err'; msg.textContent=(data.error || data.detail || ('Error '+res.status)); return; }

  // añadir al desplegable inmediatamente
  const sel=document.getElementById('recipeSelect');
  if(sel){
    const opt=document.createElement('option');
    opt.value=String(data.recipe_id);
    opt.textContent=name;
    sel.appendChild(opt);
    sel.value=String(data.recipe_id);
  }

  // reset UI
  form.reset();
  document.querySelectorAll('#allergenGrid input').forEach(i=>i.checked=false);
  updateCodePreview();
  document.getElementById('newRecipePanel').style.display='none';
  msg.className='msg ok'; msg.textContent='✅ Receta creada y cargada.';

  // Abre la ficha y permite cargar ingredientes en el mismo paso
  if (data.recipe) {
    renderRecipe(data.recipe);
    // scroll al bloque de ingredientes
    setTimeout(()=>{
      const btn=document.getElementById('addIngredientBtn');
      if(btn) btn.scrollIntoView({behavior:'smooth', block:'start'});
    }, 50);
  } else {
    await loadRecipe(data.recipe_id);
  }
});

// Carga ficha por API y la renderiza (fallback / acceso directo)
// ServiceWorker desactivado temporalmente (evita que Safari sirva versiones antiguas)

// Init extra UI
initAdminPriceUI();
bindItemAutocomplete();
refreshMovementUnit();
renderSuppliers();
renderSupplierPrices();

// Preserve Admin filters across auto-refresh
restoreAdminUIState();

// v8_7_381: bloque duplicado de supplierForm/supplierPrice eliminado; se mantiene el binding original anterior.


document.addEventListener('DOMContentLoaded', ()=>{ initFlowPreserver(); bindOcrAmountCalc(); });

document.addEventListener('DOMContentLoaded', ()=>{
  const pf=document.getElementById('pricesFilter');
  if(pf){ pf.addEventListener('input', applyPricesFilter); }
});

document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('[data-scope-global="1"]').forEach((box)=>{
    const wrap=box.closest('form') || document;
    const refresh=()=>{
      wrap.querySelectorAll('[data-scope-centers="1"] input[type="checkbox"]').forEach(cb=>{
        cb.disabled = box.checked;
        if(box.checked){ cb.checked = false; }
        const line = cb.closest('.checkline');
        if(line){ line.classList.toggle('is-disabled', box.checked); }
      });
    };
    box.addEventListener('change', refresh);
    refresh();
  });
});

(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

// ---- Block 3: Smart item picker ----
// Smart item picker: works even when iOS/Safari datalist suggestions are unreliable.
(function(){
  const MIN_CHARS = 1;
  const DEBOUNCE_MS = 120;
  const MAX_ITEMS = 20;
  function debounce(fn, ms){ let t=null; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); }; }

  function mkBox(){
    const box = document.createElement('div');
    box.className = 'smartbox';
    box.style.position = 'absolute';
    box.style.zIndex = '9999';
    box.style.display = 'none';
    box.style.background = 'var(--panel, #111)';
    box.style.border = '1px solid rgba(255,255,255,0.12)';
    box.style.borderRadius = '10px';
    box.style.maxHeight = '240px';
    box.style.overflow = 'auto';
    box.style.boxShadow = '0 10px 24px rgba(0,0,0,0.35)';
    document.body.appendChild(box);
    return box;
  }

  const box = mkBox();
  let activeInput = null;

  function positionBox(input){
    const r = input.getBoundingClientRect();
    box.style.left = (window.scrollX + r.left) + 'px';
    box.style.top = (window.scrollY + r.bottom + 6) + 'px';
    box.style.width = r.width + 'px';
  }

  function hide(){ box.style.display='none'; box.innerHTML=''; activeInput=null; }

  async function fetchItems(q){
    const url = '/api/items?q=' + encodeURIComponent(q) + '&limit=' + MAX_ITEMS;
    const res = await fetch(url, {headers:{'Accept':'application/json'}});
    const js = await res.json();
    return (js && js.items) ? js.items : [];
  }

  function render(items){
    if(!activeInput) return;
    box.innerHTML='';
    if(!items.length){ hide(); return; }
    for(const it of items){
      const row = document.createElement('div');
      row.className = 'smartrow';
      row.style.padding = '10px 12px';
      row.style.cursor = 'pointer';
      row.style.borderBottom = '1px solid rgba(255,255,255,0.08)';
      row.textContent = it.name + ' [' + it.unit + ']';
      row.addEventListener('mousedown', (e)=>{ e.preventDefault(); });
      row.addEventListener('click', ()=>{
        activeInput.value = it.name + ' [#' + it.id + ']';
        try{
          const form = activeInput.closest('form');
          if(form){
            const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
            if(hid) hid.value = String(it.id);
            const sel = form.querySelector('select[name="qty_unit"][data-smart-unit]');
            if(sel){
              const u = (it.unit||'').toLowerCase();
              if(u==='g'){
                sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>';
                sel.value = 'g';
              }else if(u==='ml'){
                sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>';
                sel.value = 'g';
              }else{
                sel.innerHTML = `<option value="${u}">${u}</option>`;
                sel.value = u || 'ud';
              }
            }
          }
        }catch(_){ /* silent */ }
        hide();
      });
      box.appendChild(row);
    }
    box.style.display='block';
    positionBox(activeInput);
  }

  const onInput = debounce(async (e)=>{
    const input = e.target;
    activeInput = input;
    const q = (input.value||'').trim();
    if(q.length < MIN_CHARS){ hide(); return; }
    try{
      const items = await fetchItems(q);
      render(items);
    }catch(_){ /* silent */ }
  }, DEBOUNCE_MS);

  function hook(input){
    input.addEventListener('input', (e)=>{
      try{
        const form = e.target.closest('form');
        if(form){
          const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
          if(hid) hid.value = '';
        }
      }catch(_){}
      onInput(e);
    });
    input.addEventListener('change', (e)=>{
      try{
        const form = e.target.closest('form');
        const parsed = parseItemIdFromText(e.target.value||'');
        if(form){
          const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
          if(hid) hid.value = parsed ? String(parsed) : '';
        }
      }catch(_){}
    });
    input.addEventListener('focus', (e)=>{ activeInput=e.target; positionBox(activeInput); });
    input.addEventListener('blur', ()=>{ setTimeout(hide, 120); });
  }

  document.querySelectorAll('input.smart-item').forEach(hook);
  window.addEventListener('scroll', ()=>{ if(activeInput) positionBox(activeInput); }, {passive:true});
  window.addEventListener('resize', ()=>{ if(activeInput) positionBox(activeInput); });
})();

// Admin items filter (Artículos precio actual)
(function(){
  const f = document.getElementById('itemsFilter');
  const tbl = document.getElementById('itemsTable');
  if(!f || !tbl) return;
  function apply(){
    const q = (f.value || '').toLowerCase().trim();
    const rows = tbl.querySelectorAll('tbody tr');
    rows.forEach(tr=>{
      const inp = tr.querySelector('input[name="name"]');
      const txt = (inp && inp.value ? inp.value : '').toLowerCase();
      tr.style.display = (!q || txt.includes(q)) ? '' : 'none';
    });
  }
  f.addEventListener('input', apply);
  // Aplica al cargar (por si venimos con filtro restaurado)
  apply();
})();

// Admin Artículos: al guardar una fila, conservar filtro y hacer "flash" + scroll a la fila guardada.
(function(){
  const tbl = document.getElementById('itemsTable');
  if(!tbl) return;
  tbl.querySelectorAll('form[action^="/item/"][action$="/update_form"]').forEach(form=>{
    form.addEventListener('submit', ()=>{
      try{
        const m = (form.getAttribute('action')||'').match(/\/item\/(\d+)\/update_form/);
        if(m && m[1]) sessionStorage.setItem('admin_lastSavedItemId', m[1]);
        // Guarda filtro actual (si existe)
        const itf=document.getElementById('itemsFilter');
        if(itf) sessionStorage.setItem('admin_itemsFilter', itf.value||'');
      }catch(e){}
    });
  });
})();


(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

// ---- Block 4: Photo modal ----
  function closePhoto(){
    const m=document.getElementById('photoModal');
    const img=document.getElementById('modalImg');
    if(!m||!img) return;
    m.style.display='none';
    img.src='';
    document.body.style.overflow='';
  }

  // Stock search (client-side)
  function filterStock(){
    const q = (document.getElementById('stockSearch')?.value || '').toLowerCase().trim();
    const rows = document.querySelectorAll('#stock table tbody tr');
    rows.forEach(r=>{
      const a = (r.getAttribute('data-article')||'') + ' ' + (r.getAttribute('data-warehouse')||'') + ' ' + (r.getAttribute('data-center')||'');
      r.style.display = (!q || a.includes(q)) ? '' : 'none';
    });
  }
  document.addEventListener('input', (e)=>{
    if(e.target && e.target.id==='stockSearch') filterStock();
  });

  // Live recipe pricing preview (no save needed). Updates only the PVP fields.
  (function(){
    const calc = document.getElementById('recipeCalc');
    if(!calc) return;
    const costAdj = parseFloat(calc.dataset.costAdjusted || '0') || 0;
    const vatRateRaw = parseFloat(calc.dataset.vatRate || '0.10');
    const vatRate = (isFinite(vatRateRaw) ? (vatRateRaw > 1 ? vatRateRaw/100 : vatRateRaw) : 0.10) || 0.10;

    let t=null;
    function update(){
      const tfc = parseFloat(document.getElementById('recipe_tfc')?.value || '0') || 0;
      const manual = parseFloat(document.getElementById('recipe_price')?.value || '0') || 0;
      let priceEx = 0;
      if(manual > 0){
        priceEx = manual;
      } else if(tfc > 0){
        priceEx = costAdj / (tfc/100);
      }
      const priceVat = priceEx * vatRate;
      const priceInc = priceEx + priceVat;
      const set = (id, v)=>{
        const el=document.getElementById(id);
        if(el) el.textContent = ((isFinite(v) ? v : 0).toFixed(2) + ' €');
      };
      set('calc_price_ex', priceEx);
      set('calc_price_vat', priceVat);
      set('calc_price_inc', priceInc);
    }
    function schedule(){
      if(t) clearTimeout(t);
      t=setTimeout(update, 150);
    }
    document.addEventListener('input', (e)=>{
      if(!e.target) return;
      if(e.target.id==='recipe_tfc' || e.target.id==='recipe_price') schedule();
    });
    update();
  })();

(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

// ---- Block 5: Unit options helper ----
(function(){
  function unitOptionsForBase(baseUnit){
    if(baseUnit==='g' || baseUnit==='kg') return ['g','kg'];
    if(baseUnit==='ud') return ['ud'];
    
    return [baseUnit||'ud'];
  }
  function applySelectOptions(sel, baseUnit){
    if(!sel) return;
    const cur = sel.value;
    const opts = unitOptionsForBase((baseUnit||sel.dataset.baseUnit||'ud').toLowerCase());
    sel.innerHTML = opts.map(u=>`<option value="${u}">${u}</option>`).join('');
    sel.value = opts.includes(cur) ? cur : opts[0];
  }
  function bindSmartUnitNear(input){
    if(!input) return;
    const wrap = input.closest('form, .row, td, .panel');
    if(!wrap) return;
    const sel = wrap.querySelector('select[data-smart-unit]');
    if(!sel) return;
    const itemId = parseItemIdFromText(input.value||'');
    const item = ITEMS.find(i=>i.id===itemId);
    if(item && item.unit){ applySelectOptions(sel, item.unit); }
  }
  document.querySelectorAll('select[data-base-unit]').forEach(sel=>applySelectOptions(sel, sel.dataset.baseUnit));
  document.addEventListener('change', function(e){ if(e.target && e.target.classList && e.target.classList.contains('smart-item')) bindSmartUnitNear(e.target); });
  document.querySelectorAll('.smart-item').forEach(inp=>bindSmartUnitNear(inp));
})();
(function(){
  document.querySelectorAll('form[action$="/ingredient/add_form"]').forEach(form=>{
    const typeSel = form.querySelector('select[name="component_type"]');
    const subTxt = form.querySelector('input[name="subrecipe_query"]');
    const subId = form.querySelector('input[name="subrecipe_id"][data-subrecipe-id]');
    function syncSubrecipeForSubmit(){
      if(!subTxt || !subId) return;
      const q = String(subTxt.value||'').trim().toUpperCase();
      const list = document.getElementById('subrecipes_datalist');
      if(!list){ return; }
      const hit = Array.from(list.querySelectorAll('option')).find(o => String(o.value||'').trim().toUpperCase() === q);
      subId.value = hit ? String(hit.dataset.id||'').trim() : '';
    }
    if(typeSel){ toggleRecipeComponentType(typeSel); typeSel.addEventListener('change', ()=>toggleRecipeComponentType(typeSel)); }
    if(subTxt){
      subTxt.addEventListener('input', ()=>{ syncSubrecipeForSubmit(); if(typeSel && (typeSel.value||'item')==='subrecipe'){ toggleRecipeComponentType(typeSel); } });
      subTxt.addEventListener('change', ()=>{ syncSubrecipeForSubmit(); if(typeSel && (typeSel.value||'item')==='subrecipe'){ toggleRecipeComponentType(typeSel); } });
    }
    form.addEventListener('submit', function(e){
      try{
        const typeSel = form.querySelector('select[name="component_type"]');
        const componentType = ((typeSel && typeSel.value) || 'item').toLowerCase();
        if(componentType === 'subrecipe'){
          syncSubrecipeForSubmit();
          const subId = form.querySelector('input[name="subrecipe_id"][data-subrecipe-id]');
          const subTxt = form.querySelector('input[name="subrecipe_query"]');
          if(!subId || !String(subId.value||'').trim()){
            e.preventDefault();
            alert('Selecciona una sub-receta antes de añadir el ingrediente.');
            if(subTxt) subTxt.focus();
            return false;
          }
          return true;
        }
        const txt = form.querySelector('input[name="item_query"]');
        const hid = form.querySelector('input[name="item_id"][data-smart-item-id]');
        const parsed = txt ? parseItemIdFromText(txt.value||'') : null;
        if(hid && !hid.value && parsed){ hid.value = String(parsed); }
        if(hid && !hid.value){
          e.preventDefault();
          alert('Selecciona un artículo de la lista antes de añadir el ingrediente.');
          if(txt) txt.focus();
          return false;
        }
      }catch(_){}
    });
  });
})();



(function(){
  document.addEventListener('submit', function(e){
    const f=e.target;
    if(f && f.matches('form[data-ocr-line-form="1"]')){
      try{ sessionStorage.setItem('ocrScrollY', String(window.scrollY||0)); }catch(_e){}
    }
  });
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(location.search);
      if(params.get('ocr_line_ok')==='1'){
        const y = parseFloat(sessionStorage.getItem('ocrScrollY')||'0');
        if(!isNaN(y) && y>0){ setTimeout(()=>window.scrollTo({top:y, behavior:'auto'}), 40); }
      }
    }catch(_e){}
  });
})();

window.initRecipeScopeLocks = function(root){
  const scopeRoot = root || document;
  scopeRoot.querySelectorAll('[data-scope-global="1"]').forEach((box)=>{
    const wrap = box.closest('form') || scopeRoot;
    const centerInputs = Array.from(wrap.querySelectorAll('[data-scope-centers="1"] input[type="checkbox"]'));
    const refresh = ()=>{
      const lock = !!box.checked;
      centerInputs.forEach(cb=>{
        if(lock){ cb.checked = false; }
        cb.disabled = lock;
        const line = cb.closest('.checkline');
        if(line){ line.classList.toggle('is-disabled', lock); }
      });
    };
    box.removeEventListener?.('change', refresh);
    box.addEventListener('change', refresh);
    centerInputs.forEach(cb=>{
      cb.addEventListener('change', ()=>{
        if(cb.checked){ box.checked = false; refresh(); }
      });
    });
    refresh();
  });
};

document.addEventListener('DOMContentLoaded', ()=>{ try{ window.initRecipeScopeLocks(document); }catch(_e){} });

// Admin Artículos: guardar sin saltar al inicio de la página.
(function(){
  async function parseJsonSafe(r){ try{return await r.json();}catch(_){return null;} }
  document.addEventListener('submit', async function(e){
    const form = e.target;
    if(!form || !form.matches('form.admin-item-update-form')) return;
    e.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    const row = form.closest('tr');
    const before = window.scrollY || 0;
    if(btn){ btn.disabled = true; btn.dataset.oldText = btn.textContent; btn.textContent = 'Guardando…'; }
    try{
      const fd = new FormData(form);
      fd.set('ajax','1');
      const res = await fetch(form.action, {method:'POST', body:fd, headers:{'Accept':'application/json'}});
      const js = await parseJsonSafe(res);
      if(!res.ok || !js || !js.ok) throw new Error((js&&js.error)||'save_failed');
      if(row){
        row.classList.add('row-flash');
        setTimeout(()=>row.classList.remove('row-flash'), 1500);
      }
      window.scrollTo({top: before, behavior:'auto'});
    }catch(err){
      alert(err && err.message === 'item_dup' ? 'Ese artículo ya existe con la misma unidad.' : 'No se pudo guardar el artículo.');
    }finally{
      if(btn){ btn.disabled = false; btn.textContent = btn.dataset.oldText || 'Guardar'; }
    }
  });
})();

// Stock lookup with intuitive autocomplete and direct open/filter in stock.
(function(){
  const input = document.getElementById('stockLookup');
  const suggest = document.getElementById('stockLookupSuggest');
  const clearBtn = document.getElementById('stockLookupClear');
  if(!input || !suggest) return;
  let t = null;
  let items = [];
  let selected = -1;
  function esc(s){ return String(s||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
  function buildUrl(q, itemId, whId){
    const centerId = input.dataset.centerId || '0';
    const url = new URL(window.location.origin + '/');
    url.searchParams.set('page', 'stock');
    url.searchParams.set('center_id', centerId);
    url.searchParams.set('stock_section', 'current_all');
    if(String(q||'').trim()) url.searchParams.set('stock_q', String(q).trim());
    if(itemId) url.searchParams.set('stock_item_id', String(itemId));
    if(whId) url.searchParams.set('stock_wh_id', String(whId));
    return url.toString();
  }
  function visibleRows(){ return Array.from(document.querySelectorAll('.stock-table tbody tr')); }
  function filterCurrentRows(q){
    const qq = String(q||'').trim().toLowerCase();
    const rows = visibleRows();
    let shown = 0;
    rows.forEach(tr=>{
      const hay = (tr.getAttribute('data-article') || tr.textContent || '').toLowerCase();
      const on = !qq || hay.includes(qq);
      tr.classList.toggle('stock-row-hidden', !on);
      if(on) shown++;
    });
    return shown;
  }
  function flashCurrentRow(itemId, q){
    const qq = String(q||'').trim().toLowerCase();
    const iid = String(itemId||'').trim();
    const rows = visibleRows();
    const first = rows.find(tr => {
      const rowId = String(tr.getAttribute('data-item-id') || '').trim();
      const hay = (tr.getAttribute('data-article')||tr.textContent||'').toLowerCase();
      return (iid && rowId===iid) || (!iid && qq && hay.includes(qq));
    });
    if(first){
      first.classList.remove('stock-row-hidden');
      first.classList.add('row-flash');
      first.scrollIntoView({behavior:'smooth', block:'center'});
      setTimeout(()=>first.classList.remove('row-flash'), 1600);
      return true;
    }
    return false;
  }
  function hideSuggest(){ suggest.style.display='none'; suggest.innerHTML=''; selected=-1; }
  function updateClearBtn(){
    if(!clearBtn) return;
    clearBtn.classList.toggle('stock-search-clear-hidden', !String(input.value||'').trim());
  }
  function renderSuggest(list, q){
    const qq = String(q||'').trim();
    if(!qq){ hideSuggest(); return; }
    if(!list.length){
      suggest.innerHTML = '<div class="empty">Sin coincidencias</div>';
      suggest.style.display='block';
      selected=-1;
      return;
    }
    suggest.innerHTML = list.map((it, idx) => `
      <button type="button" data-id="${esc(it.id)}" data-name="${esc(it.name)}" data-idx="${idx}">
        <span>${esc(it.name)}</span>
        <small>${esc(it.stock_area || it.unit || '')}</small>
      </button>`).join('');
    suggest.style.display='block';
    selected=-1;
  }
  async function search(){
    const q = String(input.value||'').trim();
    updateClearBtn();
    filterCurrentRows(q);
    if(q.length < 1){ items=[]; hideSuggest(); return; }
    const local = ITEMS.filter(it => String(it.name||'').toLowerCase().includes(q.toLowerCase())).slice(0,12);
    items = local;
    renderSuggest(items, q);
    try{
      const res = await fetch('/api/items/search?q='+encodeURIComponent(q)+'&limit=12', {headers:{'Accept':'application/json'}});
      const js = await res.json();
      const remote = (js&&js.items)||[];
      if(remote.length){ items = remote; renderSuggest(items, q); }
    }catch(_){ /* fallback local */ }
  }
  function apply(item){
    const q = item && item.name ? String(item.name) : String(input.value||'').trim();
    const itemId = item && item.id ? item.id : '';
    const url = new URL(window.location.href);
    const onStockPage = url.searchParams.get('page') === 'stock';
    const currentSection = url.searchParams.get('stock_section') || '';
    if(onStockPage){
      filterCurrentRows(q);
      if(flashCurrentRow(itemId, q)){
        const next = new URL(window.location.href);
        next.searchParams.set('stock_q', q);
        if(itemId) next.searchParams.set('stock_item_id', String(itemId));
        history.replaceState({},'',next.toString());
        hideSuggest();
        return;
      }
    }
    window.location.href = buildUrl(q, itemId, '');
  }
  function buttons(){ return Array.from(suggest.querySelectorAll('button[data-id]')); }
  function markSelected(){
    buttons().forEach((b, idx)=> b.style.background = (idx===selected ? 'rgba(255,255,255,.08)' : 'transparent'));
  }
  input.addEventListener('input', ()=>{ clearTimeout(t); t=setTimeout(search, 120); });
  input.addEventListener('focus', ()=>{ if(String(input.value||'').trim()) search(); });
  input.addEventListener('keydown', function(e){
    const btns = buttons();
    if(e.key==='ArrowDown'){ e.preventDefault(); if(!btns.length) return; selected = Math.min(selected+1, btns.length-1); markSelected(); return; }
    if(e.key==='ArrowUp'){ e.preventDefault(); if(!btns.length) return; selected = Math.max(selected-1, 0); markSelected(); return; }
    if(e.key==='Enter'){ e.preventDefault(); if(selected>=0 && btns[selected]){ btns[selected].click(); return; } const exact = items.find(it => String(it.name||'').toLowerCase()===String(input.value||'').trim().toLowerCase()); apply(exact||items[0]||null); return; }
    if(e.key==='Escape'){ hideSuggest(); }
  });
  suggest.addEventListener('click', function(e){
    const btn = e.target.closest('button[data-id]');
    if(!btn) return;
    const it = {id: btn.getAttribute('data-id'), name: btn.getAttribute('data-name')};
    input.value = it.name;
    updateClearBtn();
    apply(it);
  });
  if(clearBtn){ clearBtn.addEventListener('click', function(e){ if(String(input.value||'').trim()){ input.value=''; updateClearBtn(); hideSuggest(); } }); }
  document.addEventListener('click', function(e){ if(e.target!==input && !suggest.contains(e.target) && e.target!==clearBtn) hideSuggest(); });
  window.addEventListener('DOMContentLoaded', ()=>{
    const params = new URL(window.location.href).searchParams;
    const q = params.get('stock_q') || input.value || '';
    const iid = params.get('stock_item_id') || '';
    updateClearBtn();
    if(q){ filterCurrentRows(q); setTimeout(()=>flashCurrentRow(iid,q), 120); }
  });
})();;;;


// Order block picker mapping for mobile-friendly pedidos.
(function(){
  const mapEl = document.getElementById('orderWarehouseMap');
  if(!mapEl) return;
  const map = {
    fresh: mapEl.dataset.fresh || mapEl.dataset.fallback || '',
    dry: mapEl.dataset.dry || mapEl.dataset.fallback || '',
    clean: mapEl.dataset.clean || mapEl.dataset.fallback || '',
  };
  function sync(kind){
    const checked = document.querySelector(`[name="order_block_ui_${kind}"]:checked`);
    const hidden = document.querySelector(`[data-order-warehouse-hidden="${kind}"]`);
    if(!hidden) return;
    const val = checked ? checked.value : '';
    hidden.value = map[val] || map.fresh || map.dry || map.clean || '';
  }
  ['manual','suggestions'].forEach(kind=>{
    document.querySelectorAll(`[name="order_block_ui_${kind}"]`).forEach(el=>el.addEventListener('change', ()=>sync(kind)));
    sync(kind);
  });
})();


document.addEventListener('DOMContentLoaded', function(){
  document.querySelectorAll('[data-order-block-picker]').forEach(function(wrap){
    const radios = Array.from(wrap.querySelectorAll('input[type="radio"]'));
    if(radios.length && !radios.some(r=>r.checked)) radios[0].checked = true;
  });
  document.querySelectorAll('[data-order-block-picker]').forEach(function(wrap){
    const kind = wrap.getAttribute('data-order-block-picker');
    const hidden = document.querySelector('[data-order-warehouse-hidden="' + kind + '"]');
    const map = document.getElementById('orderWarehouseMap');
    function sync(){
      if(!hidden || !map) return;
      const checked = wrap.querySelector('input[type="radio"]:checked');
      const key = checked ? checked.value : 'fresh';
      hidden.value = map.dataset[key] || map.dataset.fallback || hidden.value || '';
    }
    wrap.querySelectorAll('input[type="radio"]').forEach(r=>r.addEventListener('change', sync));
    sync();
  });
});
