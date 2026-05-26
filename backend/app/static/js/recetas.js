// recetas.js — F&B MVP · lógica de recetas (recipe update form)
// Depende de: applySelectOptions, fmtQty (core.js)

(function(){
  const form = document.getElementById('recipeUpdateForm');
  const btn = document.getElementById('recipeUpdateSubmit');
  if(!form || !btn) return;
  form.addEventListener('submit', function(){
    if(btn.disabled) return false;
    btn.disabled = true;
    btn.textContent = 'Guardando...';
    return true;
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





(function(){
  const KEY = 'recipe_ing_scroll_restore';
  document.addEventListener('submit', function(e){
    const form = e.target;
    if(!form || !form.matches) return;
    if(!form.matches('form[action*="/ingredient/"]') && !form.matches('form[action$="/ingredient/add_form"]')) return;
    try{
      sessionStorage.setItem(KEY, JSON.stringify({
        y: window.scrollY || 0,
        rid: new URL(window.location.href).searchParams.get('rid') || '',
        at: Date.now()
      }));
    }catch(_e){}
  }, true);
  window.addEventListener('load', function(){
    try{
      const params = new URLSearchParams(window.location.search);
      if(!params.get('ing_ok')) return;
      const raw = sessionStorage.getItem(KEY);
      if(!raw) return;
      const info = JSON.parse(raw || '{}');
      sessionStorage.removeItem(KEY);
      if(!info || (Date.now() - (info.at||0) > 15000)) return;
      const restore = ()=>{ window.scrollTo({top: Number(info.y||0), behavior:'auto'}); };
      requestAnimationFrame(restore);
      setTimeout(restore, 60);
      setTimeout(restore, 180);
    }catch(_e){}
  });
})();
(function(){
  const input = document.getElementById('recipe_search_input');
  const hidden = document.getElementById('recipe_search_rid');
  const suggest = document.getElementById('recipe_search_suggest');
  if(!input || !hidden || !suggest) return;
  let timer = null;
  let latest = '';
  let remoteCache = new Map();

  function renderSuggest(items){
    if(!items || !items.length){ suggest.innerHTML=''; suggest.style.display='none'; return; }
    suggest.innerHTML = items.map(it => {
      const name = String(it.name||'').trim().toUpperCase();
      const meta = [it.category, it.type].filter(Boolean).join(' · ');
      return `<button type="button" data-id="${String(it.id||'')}" data-name="${name.replace(/"/g,'&quot;')}"><span>${name}</span>${meta ? `<small>${meta}</small>` : ''}</button>`;
    }).join('');
    suggest.style.display='block';
  }

  async function remoteSearch(q){
    const key = String(q||'').trim().toUpperCase();
    if(remoteCache.has(key)) return remoteCache.get(key);
    const res = await fetch('/api/recipes/search?q=' + encodeURIComponent(q || '') + '&limit=8', {headers:{'Accept':'application/json'}});
    if(!res.ok) throw new Error('search failed');
    const js = await res.json();
    const items = (js && js.items ? js.items : []).map(it => ({
      id: String(it.id || ''),
      name: String(it.name || '').trim().toUpperCase(),
      category: String(it.category || ''),
      type: it.is_subrecipe ? 'SUB-RECETA' : 'RECETA'
    }));
    remoteCache.set(key, items);
    return items;
  }

  function pickBest(items, name){
    const q = String(name || input.value || '').trim().toUpperCase();
    const arr = Array.isArray(items) ? items : Array.from(remoteCache.values()).flat();
    if(!q) return null;
    let hit = arr.find(it => String(it.name||'').trim().toUpperCase()===q);
    if(hit) return hit;
    hit = arr.find(it => String(it.name||'').trim().toUpperCase().startsWith(q));
    if(hit) return hit;
    hit = arr.find(it => String(it.name||'').trim().toUpperCase().includes(q));
    if(hit) return hit;
    return arr.length===1 ? arr[0] : (arr[0] || null);
  }

  function syncHiddenByExactName(name, items){
    const hit = pickBest(items, name);
    hidden.value = hit ? String(hit.id || '') : '';
  }

  async function update(){
    const q = (input.value || '').trim();
    latest = q;
    if(q.length < 1){ hidden.value=''; renderSuggest([]); return; }
    try{
      const remote = await remoteSearch(q);
      if(latest !== q) return;
      renderSuggest(remote.slice(0,8));
      syncHiddenByExactName();
    }catch(_){
      if(latest !== q) return;
      renderSuggest([]);
    }
  }

  input.addEventListener('input', function(){
    hidden.value='';
    clearTimeout(timer);
    timer = setTimeout(update, 120);
  });
  input.addEventListener('focus', function(){ if((input.value||'').trim().length >= 1) update(); });
  input.addEventListener('change', function(){ syncHiddenByExactName(); });
  input.form && input.form.addEventListener('submit', async function(e){
    const q = (input.value || '').trim();
    if(!q) return;
    syncHiddenByExactName();
    if(hidden.value) return;
    e.preventDefault();
    try{
      const remote = await remoteSearch(q);
      syncHiddenByExactName(q, remote);
    }catch(_e){}
    input.form.submit();
  });
  document.addEventListener('click', function(e){
    const btn = e.target.closest('#recipe_search_suggest button');
    if(btn){
      input.value = btn.getAttribute('data-name') || '';
      hidden.value = btn.getAttribute('data-id') || '';
      renderSuggest([]);
      return;
    }
    if(!suggest.contains(e.target) && e.target !== input){ renderSuggest([]); }
  });
})();

(function(){
  const list=document.getElementById('subrecipes_datalist');
  if(!list) return;
  const options = Array.from(list.querySelectorAll('option')).map(o => ({name:(o.value||'').trim().toUpperCase(), id:(o.dataset.id||'').trim(), unit:((o.dataset.yieldUnit||'g').trim().toLowerCase())}));
  function syncSubrecipeInput(input){
    if(!input) return;
    const form=input.closest('form');
    const hidden=form && form.querySelector('[data-subrecipe-id="1"]');
    const unitSel=form && form.querySelector('select[name="qty_unit"]');
    const q=(input.value||'').trim().toUpperCase();
    const hit=options.find(o=>o.name===q);
    if(hidden) hidden.value = hit ? hit.id : '';
    if(unitSel && hit){
      if(hit.unit==='ud') applySelectOptions(unitSel, 'ud');
      else applySelectOptions(unitSel, 'g');
    }
  }
  document.querySelectorAll('.subrecipe-search').forEach(function(input){
    input.addEventListener('input', function(){ syncSubrecipeInput(input); });
    const form=input.closest('form');
    if(form) form.addEventListener('submit', function(){ syncSubrecipeInput(input); });
  });
})();

(function(){
  function num(v){
    if(v===undefined || v===null) return 0;
    const s=String(v).replace(',', '.').replace(/[^0-9.\-]/g,'');
    const n=parseFloat(s);
    return Number.isFinite(n)?n:0;
  }
  function factor(inputUnit, baseUnit){
    const iu=(inputUnit||'').toLowerCase();
    const bu=(baseUnit||'').toLowerCase();
    if(iu===bu) return 1;
    if(iu==='kg' && bu==='g') return 1000;
    if(iu==='g' && bu==='kg') return 1/1000;
    if(iu==='l' && bu==='g') return 1000;
    if(iu==='ml' && bu==='g') return 1;
    if(iu==='kg' && bu==='g') return 1000;
    if(iu==='g' && bu==='kg') return 1/1000;
    if(iu==='ud' && bu==='ud') return 1;
    return 1;
  }
  function fmtQty(v){
    const n=num(v);
    if(Math.abs(n-Math.round(n))<1e-9) return String(Math.round(n));
    return n.toFixed(3).replace(/\.0+$/,'').replace(/(\.\d*?)0+$/,'$1');
  }
  function debounce(fn, ms){ let t; return ()=>{ clearTimeout(t); t=setTimeout(fn, ms); }; }
  function recalcRecipeLive(){
    const panel=document.getElementById('recipePanel');
    const calc=document.getElementById('recipeCalc');
    if(!panel || !calc) return;
    let subtotal=0;
    panel.querySelectorAll('tr.recipe-ing-row').forEach(function(tr){
      const unitCost=num(tr.dataset.unitCost||0);
      const baseUnit=(tr.dataset.baseUnit||'g').toLowerCase();
      const qtyInput=num(tr.querySelector('.qty-value')?.value||0);
      const qtyUnit=(tr.querySelector('select[name="qty_unit"]')?.value||baseUnit).toLowerCase();
      const waste=num((tr.querySelector('.waste-pct') || tr.querySelector('.waste-field'))?.value||0);
      const qtyBase = qtyInput * factor(qtyUnit, baseUnit);
      const wasteFactor = Math.max(0.0001, 1 - (waste/100));
      const qtyGross = waste>0 ? (qtyBase / wasteFactor) : qtyBase;
      const qtyNet = qtyBase;
      const lineCost = qtyGross * unitCost;
      subtotal += lineCost;
      const g=tr.querySelector('.gross-val'); if(g) g.textContent = fmtQty(qtyGross);
      const n=tr.querySelector('.net-val'); if(n) n.textContent = fmtQty(qtyNet);
      const w=tr.querySelector('.waste-val'); if(w) w.textContent = waste.toFixed(2).replace(/\.00$/,'');
      const lc=tr.querySelector('.line-cost'); if(lc) lc.textContent = lineCost.toFixed(2);
    });
    const contingency = num(document.getElementById('recipe_contingency')?.value||0);
    const yieldVal = Math.max(0.0001, num(document.getElementById('recipe_yield')?.value||1));
    const adjusted = subtotal * (1 + contingency/100);
    const costPer = adjusted / yieldVal;
    const manualPrice = num(document.getElementById('recipe_price')?.value||0);
    const vatRateRaw = num(calc.dataset.vatRate||0.10);
    const vatRate = (vatRateRaw > 1 ? vatRateRaw/100 : vatRateRaw);
    let priceEx = manualPrice;
    if(!(priceEx>0)){
      const tfc = num(document.getElementById('recipe_tfc')?.value||30);
      if(tfc>0){ priceEx = costPer / (tfc/100); }
    }
    const priceVat = priceEx * vatRate;
    const priceInc = priceEx + priceVat;
    const a=document.getElementById('calc_cost_adj'); if(a) a.textContent = adjusted.toFixed(2);
    const b=document.getElementById('calc_cost_per'); if(b) b.textContent = costPer.toFixed(2);
    const c=document.getElementById('calc_price_ex'); if(c) c.textContent = priceEx.toFixed(2) + ' €';
    const d=document.getElementById('calc_price_vat'); if(d) d.textContent = priceVat.toFixed(2) + ' €';
    const e=document.getElementById('calc_price_inc'); if(e) e.textContent = priceInc.toFixed(2) + ' €';

    const prep = num(document.getElementById('labor_prep_min')?.value||0);
    const cook = num(document.getElementById('labor_cook_min')?.value||0);
    const rest = num(document.getElementById('labor_rest_min')?.value||0);
    const people = num(document.getElementById('labor_people')?.value||0);
    const hourly = num(document.getElementById('labor_hourly_cost')?.value||0);
    const totalMin = Math.max(0, prep + cook + rest);
    const laborTotal = (totalMin / 60) * people * hourly;
    const laborPer = laborTotal / yieldVal;
    const operatingPer = (adjusted + laborTotal) / yieldVal;
    const lt=document.getElementById('labor_total_min'); if(lt) lt.textContent = totalMin.toFixed(0);
    const lct=document.getElementById('labor_cost_total'); if(lct) lct.textContent = laborTotal.toFixed(2);
    const lcp=document.getElementById('labor_cost_per_portion'); if(lcp) lcp.textContent = laborPer.toFixed(2);
    const lop=document.getElementById('labor_operating_per_portion'); if(lop) lop.textContent = operatingPer.toFixed(2);

    const indirectVatRate = 0.21;
    const salesBase = Math.max(0, num(document.getElementById('indirect_sales_base')?.value||0));
    function taxMode(id){ return (document.getElementById(id)?.value || 'ex_vat'); }
    function netAmount(amountId, modeId){
      const amount = Math.max(0, num(document.getElementById(amountId)?.value||0));
      return taxMode(modeId)==='inc_vat' ? amount / (1 + indirectVatRate) : amount;
    }
    function pct(amount){ return salesBase>0 ? (amount / salesBase * 100) : 0; }
    const rentNet = netAmount('indirect_rent_amount','indirect_rent_tax_mode');
    const servicesNet = netAmount('indirect_services_amount','indirect_services_tax_mode');
    const adminNet = netAmount('indirect_admin_amount','indirect_admin_tax_mode');
    const marketingNet = netAmount('indirect_marketing_amount','indirect_marketing_tax_mode');
    const otherNet = netAmount('indirect_other_amount','indirect_other_tax_mode');
    const salaryNet = Math.max(0, num(document.getElementById('salary_cost_amount')?.value||0));
    const rentPct = pct(rentNet);
    const servicesPct = pct(servicesNet);
    const adminPct = pct(adminNet);
    const marketingPct = pct(marketingNet);
    const otherPct = pct(otherNet);
    const salaryPct = pct(salaryNet);
    const totalPct = rentPct + servicesPct + adminPct + marketingPct + otherPct + salaryPct;
    const indirectLoadPer = priceEx * (totalPct/100);
    const setPct=(id,val)=>{ const el=document.getElementById(id); if(el) el.textContent = val.toFixed(2); };
    setPct('indirect_rent_pct', rentPct);
    setPct('indirect_services_pct', servicesPct);
    setPct('indirect_admin_pct', adminPct);
    setPct('indirect_marketing_pct', marketingPct);
    setPct('indirect_other_pct', otherPct);
    setPct('salary_cost_pct', salaryPct);
    setPct('indirect_total_pct', totalPct);
    const ilp=document.getElementById('indirect_load_per_portion'); if(ilp) ilp.textContent = indirectLoadPer.toFixed(2);
    const its=document.getElementById('indirect_total_pct_summary'); if(its) its.textContent = totalPct.toFixed(2);
    const ilps=document.getElementById('indirect_load_per_portion_summary'); if(ilps) ilps.textContent = indirectLoadPer.toFixed(2);
  }
  const scheduleRecalc = debounce(recalcRecipeLive, 120);
  document.addEventListener('input', function(e){
    const t=e.target;
    if(!t || !t.closest || !t.closest('#recipePanel')) return;
    if(t.matches('.qty-value, .waste-pct, .waste-field, #recipe_contingency, #recipe_yield, #recipe_price, #recipe_tfc, #labor_prep_min, #labor_cook_min, #labor_rest_min, #labor_people, #labor_hourly_cost, #indirect_sales_base, #indirect_rent_amount, #indirect_services_amount, #indirect_admin_amount, #indirect_marketing_amount, #indirect_other_amount, #salary_cost_amount')) scheduleRecalc();
  });
  document.addEventListener('change', function(e){
    const t=e.target;
    if(!t || !t.closest || !t.closest('#recipePanel')) return;
    if(t.matches('select[name="qty_unit"], .qty-value, .waste-pct, .waste-field, #recipe_contingency, #recipe_yield, #recipe_price, #recipe_tfc, #labor_prep_min, #labor_cook_min, #labor_rest_min, #labor_people, #labor_hourly_cost, #indirect_rent_tax_mode, #indirect_services_tax_mode, #indirect_admin_tax_mode, #indirect_marketing_tax_mode, #indirect_other_tax_mode')) scheduleRecalc();
  });
  window.addEventListener('load', function(){ setTimeout(recalcRecipeLive, 20); });
})();


(function(){
  function debounce(fn, ms){ let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); }; }
  async function fetchItems(q){
    const res = await fetch('/api/items/search?q=' + encodeURIComponent(q || '') + '&limit=12', {headers:{'Accept':'application/json'}});
    const js = await res.json();
    return (js && js.items) ? js.items : [];
  }
  async function fetchSubrecipes(q){
    const res = await fetch('/api/recipes/search?q=' + encodeURIComponent(q || '') + '&limit=12&subrecipes_only=1', {headers:{'Accept':'application/json'}});
    const js = await res.json();
    return (js && js.items) ? js.items : [];
  }
  function setUnit(form, unit){
    const sel = form && form.querySelector('select[name="qty_unit"][data-smart-unit]');
    if(!sel) return;
    const u = String(unit || 'ud').toLowerCase();
    if(u === 'g' || u === 'ml'){ sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option><option value="ud">ud</option>'; sel.value='g'; return; }
    if(u === 'kg' || u === 'l'){ sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option><option value="ud">ud</option>'; sel.value='kg'; return; }
    if(u === 'ud'){ sel.innerHTML = '<option value="ud">ud</option><option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>'; sel.value='ud'; return; }
    sel.value = u;
  }
  function toggleType(form){
    const sel = form && form.querySelector('#component_type_select');
    const itemRow = form && form.querySelector('[data-component-item="1"]');
    const subRow = form && form.querySelector('[data-component-subrecipe="1"]');
    const isSub = !!sel && (String(sel.value||'item').toLowerCase() === 'subrecipe');
    if(itemRow) itemRow.style.display = isSub ? 'none' : '';
    if(subRow) subRow.style.display = isSub ? '' : 'none';
    return isSub;
  }
  function wire(form){
    if(!form || form.__recipeSmartWired) return; form.__recipeSmartWired = true;
    const typeSel = form.querySelector('#component_type_select');
    const itemInput = form.querySelector('.recipe-item-query');
    const itemHidden = form.querySelector('input[name="item_id"][data-smart-item-id]');
    const itemResults = form.querySelector('.recipe-item-results');
    const subInput = form.querySelector('.subrecipe-search');
    const subHidden = form.querySelector('input[name="subrecipe_id"][data-subrecipe-id]');
    const subResults = form.querySelector('.recipe-subrecipe-results');
    function hideItem(){ if(itemResults){ itemResults.innerHTML=''; itemResults.style.display='none'; } }
    function hideSub(){ if(subResults){ subResults.innerHTML=''; subResults.style.display='none'; } }
    function chooseItem(it){
      if(!itemInput || !itemHidden) return;
      itemInput.value = it.name + ' [#' + it.id + ']';
      itemHidden.value = String(it.id || '');
      setUnit(form, it.unit);
      hideItem();
    }
    function chooseSub(it){
      if(!subInput || !subHidden) return;
      subInput.value = String(it.name || '').trim().toUpperCase();
      subHidden.value = String(it.id || '');
      setUnit(form, it.yield_unit || 'g');
      hideSub();
    }
    const itemSearch = debounce(async ()=>{
      if(toggleType(form)) return hideItem();
      const q = (itemInput && itemInput.value || '').trim();
      if(itemHidden) itemHidden.value = '';
      if(q.length < 1){ hideItem(); return; }
      try{
        const items = await fetchItems(q);
        if(!items.length){ hideItem(); return; }
        itemResults.innerHTML = items.map(it => `<button type="button" data-id="${it.id}" data-name="${String(it.name||'').replace(/"/g,'&quot;')}" data-unit="${String(it.unit||'').replace(/"/g,'&quot;')}">${it.name} <small>[${it.unit||'ud'}]</small></button>`).join('');
        itemResults.style.display='block';
      }catch(_){ hideItem(); }
    }, 120);
    const subSearch = debounce(async ()=>{
      if(!toggleType(form)) return hideSub();
      const q = (subInput && subInput.value || '').trim();
      if(subHidden) subHidden.value = '';
      if(q.length < 1){ hideSub(); return; }
      try{
        const items = await fetchSubrecipes(q);
        if(!items.length){ hideSub(); return; }
        subResults.innerHTML = items.map(it => `<button type="button" data-id="${it.id}" data-name="${String(it.name||'').replace(/"/g,'&quot;')}" data-unit="${String(it.yield_unit||'g').replace(/"/g,'&quot;')}">${it.name} <small>[SUB-RECETA]</small></button>`).join('');
        subResults.style.display='block';
      }catch(_){ hideSub(); }
    }, 120);
    if(typeSel){
      typeSel.addEventListener('change', ()=>{ toggleType(form); hideItem(); hideSub(); });
      toggleType(form);
    }
    if(itemInput && itemResults){
      itemInput.addEventListener('input', itemSearch);
      itemInput.addEventListener('focus', itemSearch);
      itemResults.addEventListener('mousedown', e=>e.preventDefault());
      itemResults.addEventListener('click', e=>{
        const btn = e.target.closest('button[data-id]'); if(!btn) return;
        chooseItem({id:btn.dataset.id, name:btn.dataset.name, unit:btn.dataset.unit});
      });
    }
    if(subInput && subResults){
      subInput.addEventListener('input', subSearch);
      subInput.addEventListener('focus', subSearch);
      subResults.addEventListener('mousedown', e=>e.preventDefault());
      subResults.addEventListener('click', e=>{
        const btn = e.target.closest('button[data-id]'); if(!btn) return;
        chooseSub({id:btn.dataset.id, name:btn.dataset.name, yield_unit:btn.dataset.unit});
      });
    }
    form.addEventListener('submit', ()=>{
      const isSub = toggleType(form);
      if(!isSub && itemInput && itemHidden){
        const m = /\[#(\d+)\]\s*$/.exec(itemInput.value || '');
        if(m) itemHidden.value = m[1];
      }
    });
    document.addEventListener('click', e=>{
      if(itemInput && e.target!==itemInput && itemResults && !itemResults.contains(e.target)) hideItem();
      if(subInput && e.target!==subInput && subResults && !subResults.contains(e.target)) hideSub();
    });
  }
  const recipeForm = document.querySelector('form[action$="/ingredient/add_form"]');
  if(recipeForm) wire(recipeForm);
  document.addEventListener('focusin', e=>{ const f=e.target && e.target.closest && e.target.closest('form[action$="/ingredient/add_form"]'); if(f) wire(f); });
})();
(function(){
  function qs(sel, root){ return (root||document).querySelector(sel); }
  function htmlToDoc(html){ return new DOMParser().parseFromString(html, 'text/html'); }
  function replaceRecipeIngredientsFromHtml(html){
    const doc = htmlToDoc(html);
    const freshBlock = doc.querySelector('#recipeIngredientsBlock');
    const currentBlock = document.querySelector('#recipeIngredientsBlock');
    if(freshBlock && currentBlock){
      currentBlock.replaceWith(freshBlock);
      return true;
    }
    const fresh = doc.querySelector('#recipePanel');
    const current = document.querySelector('#recipePanel');
    if(!fresh || !current) return false;
    current.replaceWith(fresh);
    try{ window.initRecipeScopeLocks && window.initRecipeScopeLocks(document); }catch(_e){}
    return true;
  }
  async function submitRecipeIngredientForm(form){
    const y = window.scrollY || 0;
    const fd = new FormData(form);
    const res = await fetch(form.action, {
      method: (form.method || 'POST').toUpperCase(),
      body: fd,
      headers: { 'X-Requested-With':'fetch', 'Accept':'text/html' },
      credentials: 'same-origin',
      redirect: 'follow'
    });
    const html = await res.text();
    replaceRecipeIngredientsFromHtml(html);
    requestAnimationFrame(()=>window.scrollTo({ top:y, behavior:'auto' }));
    setTimeout(()=>window.scrollTo({ top:y, behavior:'auto' }), 20);
    setTimeout(()=>window.scrollTo({ top:y, behavior:'auto' }), 80);
  }
  document.addEventListener('submit', function(e){
    const form = e.target;
    if(!form || !form.matches) return;
    if(form.matches('form[action$="/ingredient/add_form"]') || form.matches('form[action*="/ingredient/"][action$="/update_form"]') || form.matches('form[action*="/ingredient/"][action$="/delete_form"]')){
      e.preventDefault();
      submitRecipeIngredientForm(form).catch(()=>form.submit());
    }
  }, true);
})();

(function(){
  function initRecipeScopeLocksLocal(root){
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
      box.onchange = refresh;
      centerInputs.forEach(cb=>{
        cb.onchange = ()=>{ if(cb.checked){ box.checked = false; refresh(); } };
      });
      refresh();
    });
  }
  window.initRecipeScopeLocks = initRecipeScopeLocksLocal;
  document.addEventListener('DOMContentLoaded', ()=>{ try{ initRecipeScopeLocksLocal(document); }catch(_e){} });
})();


/* v8_7_350 · Recetas estable: guardar sin recargar pantalla completa ni mezclar vistas */
(function(){
  if(window.__recipeStableAjaxV350) return;
  window.__recipeStableAjaxV350 = true;

  function htmlToDoc(html){ return new DOMParser().parseFromString(html, 'text/html'); }
  function hardCleanRecipeTransientState(){
    try{ sessionStorage.removeItem('flow_preserve'); }catch(_e){}
    try{ document.body.classList.remove('mobile-menu-open'); }catch(_e){}
    try{ window.closeMobileMenu && window.closeMobileMenu(); }catch(_e){}
    document.querySelectorAll('.recipe-search-suggest,.smart-inline-results').forEach(el=>{ try{ el.style.display='none'; }catch(_e){} });
  }
  function replaceRecipePanelFromHtml(html){
    const doc = htmlToDoc(html);
    const freshPanel = doc.querySelector('#recipePanel');
    const currentPanel = document.querySelector('#recipePanel');
    if(freshPanel && currentPanel){
      currentPanel.replaceWith(freshPanel);
      return true;
    }
    return false;
  }
  function flashSaved(){
    const panel = document.querySelector('#recipePanel');
    if(!panel) return;
    let msg = panel.querySelector('.recipe-save-feedback-v350');
    if(!msg){
      msg = document.createElement('div');
      msg.className = 'recipe-save-feedback-v350';
      msg.textContent = 'Ficha guardada sin recargar la pantalla.';
      panel.insertBefore(msg, panel.firstElementChild ? panel.firstElementChild.nextSibling : panel.firstChild);
    }
    msg.classList.add('is-visible');
    setTimeout(()=>msg && msg.classList.remove('is-visible'), 1800);
  }
  async function ajaxRecipeForm(form){
    const beforeY = window.scrollY || 0;
    const activeName = document.activeElement && form.contains(document.activeElement) ? (document.activeElement.name || document.activeElement.id || '') : '';
    const btn = form.querySelector('[type="submit"],button:not([type])');
    const oldText = btn ? btn.textContent : '';
    hardCleanRecipeTransientState();
    document.body.classList.add('recipe-saving-v350');
    if(btn){ btn.disabled=true; btn.textContent='Guardando…'; }
    try{
      const res = await fetch(form.action, {
        method: (form.method || 'POST').toUpperCase(),
        body: new FormData(form),
        headers: {'X-Requested-With':'fetch','Accept':'text/html'},
        credentials:'same-origin',
        redirect:'follow'
      });
      const html = await res.text();
      if(!res.ok || !replaceRecipePanelFromHtml(html)) throw new Error('recipe ajax failed');
      try{ window.initRecipeScopeLocks && window.initRecipeScopeLocks(document); }catch(_e){}
      try{
        if(activeName){
          const selector = `[name="${CSS.escape(activeName)}"], #${CSS.escape(activeName)}`;
          const tgt = document.querySelector(selector);
          if(tgt){ tgt.focus({preventScroll:true}); }
        }
      }catch(_e){}
      const maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      const targetY = Math.min(beforeY, maxY);
      requestAnimationFrame(()=>window.scrollTo({top:targetY, behavior:'auto'}));
      setTimeout(()=>window.scrollTo({top:targetY, behavior:'auto'}), 40);
      flashSaved();
      try{ history.replaceState(null, '', new URL(res.url || location.href).pathname + new URL(res.url || location.href).search); }catch(_e){}
    }catch(err){
      console.warn('Recipe stable ajax fallback', err);
      form.submit();
    }finally{
      document.body.classList.remove('recipe-saving-v350');
      const freshBtn = document.querySelector('#recipeUpdateSubmit');
      if(freshBtn){ freshBtn.disabled=false; freshBtn.textContent='Guardar ficha'; }
      if(btn && btn.isConnected){ btn.disabled=false; btn.textContent=oldText || btn.textContent; }
    }
  }

  document.addEventListener('submit', function(e){
    const form = e.target;
    if(!form || !form.matches) return;
    const isMain = form.matches('#recipeUpdateForm');
    const isPhoto = form.matches('.recipe-photo-upload') || (form.action && (form.action.includes('/upload_photo') || form.action.includes('/remove_photo')));
    if(!isMain && !isPhoto) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    ajaxRecipeForm(form);
  }, true);
})();
