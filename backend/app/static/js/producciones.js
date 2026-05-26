// producciones.js — F&B MVP v8.7.198
// Lógica de batch, tabs de categorías y filtros de producciones

// ============================================================
// TABS DE CATEGORÍAS (prod-cat-btn / prod-cat-panel)
// ============================================================
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.prod-cat-btn');
  if (!btn) return;
  const container = btn.closest('[data-production-tabs]');
  if (!container) return;
  const target = btn.dataset.prodTarget;
  if (!target) return;

  // Desactivar todos los botones y paneles del contenedor
  container.querySelectorAll('.prod-cat-btn').forEach(b => b.classList.remove('active'));
  container.parentElement.querySelectorAll('.prod-cat-panel').forEach(p => p.classList.remove('active'));

  // Activar el seleccionado
  btn.classList.add('active');
  const panel = document.getElementById(target);
  if (panel) panel.classList.add('active');
});

// ============================================================
// BATCH FORM — serializar filas seleccionadas a JSON
// ============================================================
document.addEventListener('change', function(e) {
  if (!e.target || !e.target.matches) return;
  const isBatchCb = e.target.matches('.prod-row input[type="checkbox"][name="recipe_ids"]');
  if (isBatchCb) {
    const row = e.target.closest('.prod-row');
    if (row) row.classList.toggle('active', !!e.target.checked);
  }
});

document.addEventListener('submit', function(e){
  const form = e.target && e.target.closest ? e.target.closest('#productionBatchForm') : null;
  if (!form) return;
  const rows = Array.from(form.querySelectorAll('.prod-row'));
  const out = [];
  rows.forEach(function(row) {
    const cb = row.querySelector('input[type="checkbox"][name="recipe_ids"]');
    if (!cb || !cb.checked) return;
    const rid = parseInt(cb.value || '0', 10);
    if (!rid) return;
    const qtyEl  = row.querySelector('[data-batch-qty="' + rid + '"]');
    const unitEl = row.querySelector('[data-batch-unit="' + rid + '"]');
    out.push({
      recipe_id: rid,
      qty:   qtyEl  ? qtyEl.value  : '1',
      unit:  unitEl ? unitEl.value : 'lotes',
      group: row.getAttribute('data-group') || 'Otros'
    });
  });
  if (!out.length) {
    e.preventDefault();
    const detail = document.getElementById('productionDetailPanel') || form.closest('.subpanel') || form;
    let box = detail.querySelector('.batch-inline-warning');
    if(!box){
      box = document.createElement('div');
      box.className = 'notice warn mt batch-inline-warning';
      box.innerHTML = '<span class="notice-icon">!</span><span class="notice-text">Selecciona al menos una receta o subreceta antes de crear borradores.</span>';
      detail.prepend(box);
    }
    return;
  }
  const payload = form.querySelector('#productionBatchPayload') || document.getElementById('productionBatchPayload');
  if (payload) payload.value = JSON.stringify(out);

  const appendInput = form.querySelector('input[name="append_production_id"]');
  if (appendInput && (!appendInput.value || appendInput.value === '0')) {
    try {
      const url = new URL(window.location.href);
      const pid = parseInt(url.searchParams.get('pid') || '0', 10);
      if (pid > 0) appendInput.value = String(pid);
    } catch (_) {}
  }
});


// ============================================================
// MANUAL ITEM SEARCH FALLBACK — datalist + sugerencias clicables
// ============================================================
(function(){
  const inputSelector = '.production-item-query';
  const datalistId = 'productionManualItemsDatalist';
  const suggestId = 'productionManualSuggest';
  let timer = null;
  let latest = '';

  async function fetchItems(q){
    const res = await fetch('/api/items/search?q=' + encodeURIComponent(q || ''), {headers:{'Accept':'application/json'}});
    if(!res.ok) return [];
    const js = await res.json();
    return (js && js.items) ? js.items : [];
  }

  function getSuggestBox(input){
    const row = input.closest('.row');
    return (row && row.querySelector('#' + suggestId)) || document.getElementById(suggestId);
  }

  function setItem(form, item){
    const hid = form && form.querySelector('input[name="item_id"][data-smart-item-id]');
    const inp = form && form.querySelector(inputSelector);
    if(hid) hid.value = item ? String(item.id) : '';
    if(inp && item) inp.value = String(item.name || '');
  }

  function renderDatalist(items){
    const dl = document.getElementById(datalistId);
    if(!dl) return;
    dl.innerHTML = (items || []).map(it => `<option value="${String(it.name||'').replace(/"/g,'&quot;')} [#${it.id}]">${it.unit||''}</option>`).join('');
  }

  function renderSuggest(input, items){
    const box = getSuggestBox(input);
    if(!box) return;
    if(!items || !items.length){ box.innerHTML=''; box.style.display='none'; return; }
    box.innerHTML = items.map(it => `<button type="button" class="smart-suggest-item" data-item-id="${it.id}" data-item-name="${String(it.name||'').replace(/"/g,'&quot;')}">${it.name} <span class="muted">${it.unit||''}</span></button>`).join('');
    box.style.display = 'block';
  }

  function syncHiddenId(input){
    const form = input.closest('form'); if(!form) return;
    const hid = form.querySelector('input[name="item_id"][data-smart-item-id]'); if(!hid) return;
    const raw = String(input.value || '').trim();
    const m = raw.match(/\[#(\d+)\]$/);
    if(m){ hid.value = m[1]; input.value = raw.replace(/\s*\[#\d+\]$/, ''); return; }
    const dl = document.getElementById(datalistId);
    const opt = dl ? Array.from(dl.options).find(o => (o.value || '').trim().toLowerCase() === raw.toLowerCase() || String(o.value||'').split(' [#')[0].trim().toLowerCase() === raw.toLowerCase()) : null;
    if(opt){
      const m2 = String(opt.value || '').match(/\[#(\d+)\]$/);
      hid.value = m2 ? m2[1] : '';
      input.value = String(opt.value || '').split(' [#')[0];
    } else {
      hid.value = '';
    }
  }

  async function updateInput(input){
    const q = (input.value || '').trim();
    latest = q;
    if(q.length < 1){ renderDatalist([]); renderSuggest(input, []); syncHiddenId(input); return; }
    const items = await fetchItems(q);
    if(latest !== q) return;
    renderDatalist(items);
    renderSuggest(input, items.slice(0,8));
    if(items.length === 1 && String(items[0].name||'').trim().toLowerCase() === q.toLowerCase()) {
      setItem(input.closest('form'), items[0]);
    } else {
      syncHiddenId(input);
    }
  }

  document.addEventListener('input', function(e){
    const inp = e.target;
    if(!inp || !inp.matches || !inp.matches(inputSelector)) return;
    clearTimeout(timer);
    timer = setTimeout(() => { updateInput(inp).catch(()=>{}); }, 140);
  });
  document.addEventListener('focusin', function(e){
    const inp = e.target;
    if(!inp || !inp.matches || !inp.matches(inputSelector)) return;
    updateInput(inp).catch(()=>{});
  });
  document.addEventListener('change', function(e){
    const inp = e.target;
    if(!inp || !inp.matches || !inp.matches(inputSelector)) return;
    syncHiddenId(inp);
  });
  document.addEventListener('blur', function(e){
    const inp = e.target;
    if(!inp || !inp.matches || !inp.matches(inputSelector)) return;
    setTimeout(() => syncHiddenId(inp), 100);
  }, true);
  document.addEventListener('click', function(e){
    const btn = e.target.closest('.smart-suggest-item');
    if(!btn) return;
    const box = btn.parentElement;
    const form = btn.closest('form');
    const item = {id: btn.getAttribute('data-item-id'), name: btn.getAttribute('data-item-name')};
    setItem(form, item);
    if(box){ box.innerHTML=''; box.style.display='none'; }
  });
})();


// v8_7_278 · Buscador tolerante de recetas/base para cargar producciones
(function(){
  const selector = '.production-recipe-search';
  let timer = null;
  let latest = '';
  function boxFor(input){
    let box = input.parentElement.querySelector('.production-recipe-suggest');
    if(!box){ box = document.createElement('div'); box.className='smart-inline-results production-recipe-suggest'; box.style.display='none'; input.parentElement.appendChild(box); }
    return box;
  }
  function setRecipe(input, item){
    const form = input.closest('form');
    const hid = form && form.querySelector('input[name="recipe_id"]');
    if(hid) hid.value = item && item.id ? String(item.id) : '';
    if(item && input) input.value = ((item.code ? item.code + ' · ' : '') + item.name).trim();
  }
  async function search(q){
    const res = await fetch('/api/recipes/search?q=' + encodeURIComponent(q||'') + '&limit=12', {headers:{Accept:'application/json'}});
    if(!res.ok) return [];
    const js = await res.json();
    return js.items || [];
  }
  async function update(input){
    const q = (input.value||'').trim(); latest = q;
    const box = boxFor(input);
    if(q.length < 1){ box.innerHTML=''; box.style.display='none'; setRecipe(input,null); return; }
    const items = await search(q); if(latest !== q) return;
    if(!items.length){ box.innerHTML='<div class="search-empty">Sin coincidencias. Revisa el nombre en Recetas.</div>'; box.style.display='block'; return; }
    box.innerHTML = items.map(it => `<button type="button" data-rid="${it.id}" data-code="${String(it.code||'').replace(/"/g,'&quot;')}" data-name="${String(it.name||'').replace(/"/g,'&quot;')}"><strong>${it.name}</strong><small>${it.category||''} · ${it.subcategory||''}</small></button>`).join('');
    box.style.display='block';
  }
  document.addEventListener('input', function(e){ const input=e.target; if(!input.matches || !input.matches(selector)) return; const form=input.closest('form'); const hid=form&&form.querySelector('input[name="recipe_id"]'); if(hid) hid.value=''; clearTimeout(timer); timer=setTimeout(()=>update(input).catch(()=>{}),140); });
  document.addEventListener('focusin', function(e){ const input=e.target; if(input.matches && input.matches(selector)) update(input).catch(()=>{}); });
  document.addEventListener('click', function(e){ const b=e.target.closest('.production-recipe-suggest button[data-rid]'); if(!b) return; const input=b.closest('.row').querySelector(selector); setRecipe(input,{id:b.dataset.rid,code:b.dataset.code,name:b.dataset.name}); const box=b.closest('.production-recipe-suggest'); if(box){box.innerHTML='';box.style.display='none';} });
  document.addEventListener('click', function(e){ document.querySelectorAll('.production-recipe-suggest').forEach(box=>{ if(!box.contains(e.target) && !box.parentElement.contains(e.target)) box.style.display='none'; }); });
})();
