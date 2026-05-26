// orders.js — ayuda ligera de selección de artículos en pedidos
(function(){
  function debounce(fn, ms){ let t; return (...args)=>{ clearTimeout(t); t=setTimeout(()=>fn(...args), ms); }; }
  function currentBlock(form){
    const checked = form && form.querySelector('input[name="order_block_ui_manual"]:checked');
    return checked ? String(checked.value || 'fresh').toLowerCase() : 'fresh';
  }
  function currentFreshGroup(form){
    const checked = form && form.querySelector('input[name="fresh_group_filter"]:checked');
    return checked ? String(checked.value || 'all').toLowerCase() : 'all';
  }
  async function fetchItems(q, form){
    const params = new URLSearchParams();
    params.set('q', q || '');
    params.set('limit', '80');
    params.set('block', currentBlock(form));
    if(currentBlock(form) === 'fresh'){ params.set('fresh_group', currentFreshGroup(form)); }
    const res = await fetch('/api/items/search?' + params.toString(), {headers:{'Accept':'application/json'}});
    const js = await res.json();
    return (js && js.items) ? js.items : [];
  }
  function setUnit(form, unit){
    const sel = form && form.querySelector('select[name="qty_unit"]');
    if(!sel) return;
    const u = String(unit || 'ud').toLowerCase();
    if(u === 'g'){ sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>'; sel.value='g'; return; }
    if(u === 'ml'){ sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>'; sel.value='g'; return; }
    if(u === 'kg' || u === 'l'){ sel.innerHTML = '<option value="g">g</option><option value="kg">kg</option><option value="manojo">manojo</option>'; sel.value='kg'; return; }
    sel.innerHTML = `<option value="${u}">${u}</option>`;
    sel.value = u;
  }
  function sortItems(items, q){
    const qq = String(q || '').trim().toLowerCase();
    return (items || []).slice().sort((a,b)=>{
      const an = String(a.name||'').toLowerCase();
      const bn = String(b.name||'').toLowerCase();
      const as = an.startsWith(qq) ? 0 : 1;
      const bs = bn.startsWith(qq) ? 0 : 1;
      return as - bs || an.localeCompare(bn);
    });
  }
  function wire(form){
    if(!form || form.__orderSmartWired) return; form.__orderSmartWired = true;
    const input = form.querySelector('.order-item-query');
    const hidden = form.querySelector('input[name="item_id"][data-smart-item-id]');
    const results = form.querySelector('.order-item-results');
    if(!input || !hidden || !results) return;
    let last='';
    function hide(){ results.innerHTML=''; results.style.display='none'; }
    function choose(it){
      input.value = it.name + ' [#' + it.id + ']';
      hidden.value = String(it.id || '');
      setUnit(form, it.unit);
      hide();
    }
    function resetIfBlockChanges(){
      hidden.value = '';
      if(/\[#\d+\]\s*$/.test(input.value||'')) input.value = '';
      hide();
      if((input.value || '').trim().length > 0) search();
    }
    const search = debounce(async ()=>{
      const q = (input.value || '').trim();
      hidden.value = '';
      if(q.length < 1){ hide(); return; }
      last = q;
      try{
        let items = await fetchItems(q, form);
        if(last !== q) return;
        items = sortItems(items, q).slice(0, 20);
        if(!items.length){
          results.innerHTML = '<div class="order-empty-search">No hay artículos en este bloque o categoría.</div>';
          results.style.display='block';
          return;
        }
        results.innerHTML = items.map(it => `<button type="button" data-id="${it.id}" data-name="${String(it.name||'').replace(/"/g,'&quot;')}" data-unit="${String(it.unit||'').replace(/"/g,'&quot;')}"><span>${it.name}</span><small>${it.unit||'ud'} · ${(it.stock_area||'-')}</small></button>`).join('');
        results.style.display='block';
      }catch(_){ hide(); }
    }, 120);
    input.addEventListener('input', search);
    input.addEventListener('focus', search);
    input.addEventListener('keydown', e=>{
      if(e.key === 'Enter'){
        const first = results.querySelector('button[data-id]');
        if(first){ e.preventDefault(); first.click(); }
      }
    });
    form.querySelectorAll('input[name="order_block_ui_manual"]').forEach(r=>r.addEventListener('change', resetIfBlockChanges));
    form.querySelectorAll('input[name="fresh_group_filter"]').forEach(r=>r.addEventListener('change', resetIfBlockChanges));
    results.addEventListener('mousedown', e=>e.preventDefault());
    results.addEventListener('click', e=>{
      const btn = e.target.closest('button[data-id]'); if(!btn) return;
      choose({id:btn.dataset.id, name:btn.dataset.name, unit:btn.dataset.unit});
    });
    form.addEventListener('submit', ()=>{
      const m = /\[#(\d+)\]\s*$/.exec(input.value || '');
      if(m){ hidden.value = m[1]; return; }
      const raw = String(input.value || '').trim().toLowerCase();
      const exactBtn = Array.from(results.querySelectorAll('button[data-id]')).find(btn => String(btn.dataset.name || '').trim().toLowerCase() === raw);
      if(exactBtn) hidden.value = exactBtn.dataset.id || '';
    });
    document.addEventListener('click', e=>{ if(e.target!==input && !results.contains(e.target)) hide(); });
  }
  document.querySelectorAll('form[action*="/add_line_form"]').forEach(wire);
  document.addEventListener('focusin', e=>{ const f=e.target && e.target.closest && e.target.closest('form[action*="/add_line_form"]'); if(f) wire(f); });
})();

// v8_7_283 · Blindaje contra creación accidental de pedidos al hacer scroll en móvil.
(function(){
  let startX=0, startY=0, moved=false;
  document.addEventListener('touchstart', function(e){
    const t=e.touches && e.touches[0]; if(!t) return;
    startX=t.clientX; startY=t.clientY; moved=false;
  }, {passive:true});
  document.addEventListener('touchmove', function(e){
    const t=e.touches && e.touches[0]; if(!t) return;
    if(Math.abs(t.clientX-startX)>10 || Math.abs(t.clientY-startY)>10) moved=true;
  }, {passive:true});
  document.addEventListener('submit', function(e){
    const form=e.target;
    if(!form || !form.matches || !form.matches('[data-scroll-safe-submit="1"]')) return;
    if(moved){
      e.preventDefault();
      e.stopPropagation();
      moved=false;
      if(window.showToast) window.showToast('info','Scroll detectado. No se creó pedido accidentalmente.');
      return false;
    }
    const btn=form.querySelector('[data-critical-submit="new-order"]');
    if(btn){
      if(btn.dataset.submitting==='1'){
        e.preventDefault();
        e.stopPropagation();
        return false;
      }
      btn.dataset.submitting='1';
      btn.disabled=true;
      btn.textContent='Creando…';
    }
  }, true);
})();

// v8_7_288 · Pedidos: quitar línea sin saltar al inicio y sin recargar la pantalla.
(function(){
  function updateLineCounters(){
    const rows = Array.from(document.querySelectorAll('#orderLines ~ .table-wrap .order-line-row, tr.order-line-row'));
    const checked = rows.filter(r => r.classList.contains('order-line-checked')).length;
    const counter = document.querySelector('#orderLines + .muted');
    if(counter){ counter.textContent = `✅ ${checked}/${rows.length} líneas marcadas.`; }
  }
  document.addEventListener('submit', async function(e){
    const form = e.target;
    if(!form || !form.matches || !form.matches('form.order-line-delete-form')) return;
    e.preventDefault();
    e.stopPropagation();
    const row = form.closest('tr.order-line-row');
    const y = window.scrollY || 0;
    const btn = form.querySelector('button');
    if(btn){ btn.disabled = true; btn.textContent = 'Quitando…'; }
    try{
      const res = await fetch(form.action, {method:'POST', body:new FormData(form), headers:{'X-Requested-With':'fetch'}});
      if(!res.ok){ throw new Error('delete failed'); }
      if(row){
        row.style.transition = 'opacity .15s ease, transform .15s ease';
        row.style.opacity = '0'; row.style.transform = 'scale(.99)';
        setTimeout(()=>{ row.remove(); updateLineCounters(); window.scrollTo({top:y, behavior:'auto'}); }, 160);
      } else {
        window.scrollTo({top:y, behavior:'auto'});
      }
      if(window.showToast) window.showToast('ok','Línea quitada.');
    }catch(err){
      if(btn){ btn.disabled = false; btn.textContent = 'Quitar'; }
      if(window.showToast) window.showToast('err','No se pudo quitar la línea.');
      else alert('No se pudo quitar la línea.');
    }
    return false;
  }, true);
})();
