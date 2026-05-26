// albaranes.js — F&B MVP · OCR draft state + nuevo proveedor en albarán
// Depende de: applySelectOptions (core.js)

function toggleNewSupplier(){
          const box = document.getElementById('newSupplierBox');
          if(!box) return;
          const isHidden = box.style.display === 'none' || box.style.display === '';
          box.style.display = isHidden ? 'block' : 'none';
          if(isHidden){
            const sel = document.getElementById('supplierSelect');
            if(sel) sel.value = '0';
          }
        }
      
        function renderPreview(files, targetId){
          const box = document.getElementById(targetId);
          if(!box) return;
          box.innerHTML = '';
          (files||[]).forEach(file => {
            if(!file || !file.type || !file.type.startsWith('image/')) return;
            const wrap = document.createElement('div');
            wrap.className = 'photo-thumb';
            const img = document.createElement('img');
            img.alt = file.name || 'foto';
            img.src = URL.createObjectURL(file);
            wrap.appendChild(img);
            const cap = document.createElement('div');
            cap.className = 'photo-caption';
            cap.textContent = file.name || 'foto';
            wrap.appendChild(cap);
            box.appendChild(wrap);
          });
        }
        function _appendFiles(targetInputId, files, previewId, countId, mirrorInputId){
          const target = document.getElementById(targetInputId);
          if(!target || !files || !files.length) return;
          const dt = new DataTransfer();
          const existing = target.files ? Array.from(target.files) : [];
          existing.forEach(f => dt.items.add(f));
          Array.from(files).forEach(f => { if(f && f.type && f.type.startsWith('image/')) dt.items.add(f); });
          target.files = dt.files;
          const mirror = mirrorInputId ? document.getElementById(mirrorInputId) : null;
          if(mirror) mirror.files = dt.files;
          const out = document.getElementById(countId);
          if(out) out.textContent = dt.files.length + ' seleccionada' + (dt.files.length===1 ? '' : 's');
          renderPreview(Array.from(target.files || []), previewId);
        }
        function updateFilesCount(){
          const master = document.getElementById('files_master');
          const out = document.getElementById('files_count');
          const all = master && master.files ? Array.from(master.files) : [];
          if(out) out.textContent = all.length + ' seleccionada' + (all.length===1 ? '' : 's');
          const pages=document.getElementById('files_pages_hint'); if(pages) pages.textContent='Páginas preparadas: '+all.length;
          renderPreview(all, 'files_preview');
        }
        function updateUploadCount(){
          const master = document.getElementById('up_master');
          const out = document.getElementById('up_count');
          const all = master && master.files ? Array.from(master.files) : [];
          if(out) out.textContent = all.length + ' seleccionada' + (all.length===1 ? '' : 's');
          renderPreview(all, 'up_preview');
        }
        function clearReceiptDraftFiles(){
          ['files_master','files_single','files_multi'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
          const box=document.getElementById('files_preview'); if(box) box.innerHTML='';
          const out=document.getElementById('files_count'); if(out) out.textContent='0 seleccionadas';
          const pages=document.getElementById('files_pages_hint'); if(pages) pages.textContent='Páginas preparadas: 0';
        }
        function clearReceiptUploadFiles(){
          ['up_master','up_single','up_multi'].forEach(id => { const el=document.getElementById(id); if(el) el.value=''; });
          const box=document.getElementById('up_preview'); if(box) box.innerHTML='';
          const out=document.getElementById('up_count'); if(out) out.textContent='0 seleccionadas';
        }
        function setupPhotoButtons(){
          const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || '') || (navigator.maxTouchPoints||0) > 1;
          document.querySelectorAll('.js-primary-upload-btn').forEach(btn => {
            btn.textContent = isMobile ? '📄 Escanear / subir 1 foto' : '📎 Subir 1 foto';
            btn.style.display = 'inline-flex';
          });
          document.querySelectorAll('.js-multi-upload-btn').forEach(btn => {
            btn.textContent = isMobile ? '🗂️ Añadir páginas' : '🗂️ Añadir varias fotos';
            btn.style.display = 'inline-flex';
          });
        }
        document.addEventListener('change', function(e){
          if(!e.target) return;
          if(e.target.id==='files_single' || e.target.id==='files_multi'){
            _appendFiles('files_master', e.target.files, 'files_preview', 'files_count');
            e.target.value='';
          }
          if(e.target.id==='up_single' || e.target.id==='up_multi'){
            _appendFiles('up_master', e.target.files, 'up_preview', 'up_count');
            e.target.value='';
          }
        });
        document.addEventListener('DOMContentLoaded', setupPhotoButtons);

function bindReceiptCreateAjax(){
  const form = document.getElementById('receiptNewForm');
  const btn = document.getElementById('receiptNewSubmit');
  const msg = document.getElementById('receiptNewMsg');
  if(!form || !btn) return;
  form.addEventListener('submit', async function(e){
    e.preventDefault();
    try{
      btn.disabled = true;
      if(msg) msg.textContent = 'Creando borrador...';
      const fd = new FormData(form);
      const res = await fetch(form.action, {method:'POST', body:fd, redirect:'follow'});
      if(msg) msg.textContent = 'Abriendo borrador...';
      if(res.redirected && res.url){
        window.location.href = res.url;
        return;
      }
      const txt = await res.text();
      const m = String(txt||'').match(/\?page=albaranes[^"'\s<>]*/);
      if(m && m[0]){
        window.location.href = m[0].startsWith('/') ? m[0] : ('/' + m[0]);
        return;
      }
      window.location.reload();
    }catch(err){
      console.error(err);
      if(msg) msg.textContent = 'No se pudo abrir solo. Recarga una vez.';
      btn.disabled = false;
    }
  });
}

function bindOCRSubmitOnce(){
  const forms = document.querySelectorAll('form[action*="/process_ocr"]');
  forms.forEach((form)=>{
    form.addEventListener('submit', function(){
      const btn = form.querySelector('button[type="submit"]');
      if(btn){
        btn.disabled = true;
        const old = btn.textContent;
        btn.dataset.oldText = old;
        btn.textContent = old.includes('GET') ? 'Procesando…' : 'Procesando OCR…';
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', function(){
  bindReceiptCreateAjax();
  bindOCRSubmitOnce();
});


(function(){
  try {
    const params = new URLSearchParams(window.location.search);
    if (document.body && params.get("page") === "albaranes") {
      const aid = params.get("aid");
      const needsFocus = params.get("ocr_ok") || params.get("head_ok") || params.get("ocr_err") || params.get("ocr_wait") || params.get("ocr_line_ok") || params.get("ocr_line_err");
      if (aid && needsFocus) {
        requestAnimationFrame(() => {
          const lineId = params.get("ocr_line_id");
          const row = lineId ? document.getElementById(`ocrLineRow${lineId}`) : null;
          const target = row || document.getElementById("ocrSection") || document.getElementById("receiptPanel");
          if (target) target.scrollIntoView({behavior:"auto", block: row ? "center" : "start"});
        });
      }
    }
  } catch (e) {}
})();
(function(){
  try {
    const params = new URLSearchParams(window.location.search);
    if (document.body && params.get("page") === "albaranes") {
      const statusNode = document.querySelector('[data-ocr-status]');
      const aid = params.get('aid');
      const status = statusNode ? (statusNode.getAttribute('data-ocr-status') || '').toUpperCase() : '';
      if (aid && status === 'PROCESSING') {
        let tries = 0;
        let seenReady = false;
        const poll = () => {
          tries += 1;
          try {
            fetch(`/api/receipt/${aid}/ocr_status?ts=` + Date.now(), {cache:'no-store', headers:{'X-Requested-With':'XMLHttpRequest'}})
              .then(r => r.json())
              .then(data => {
                const nextStatus = String((data && data.status) || '').toUpperCase();
                if (nextStatus && nextStatus !== 'PROCESSING') {
                  const url = new URL(window.location.href);
                  url.searchParams.set('ocr_ok','1');
                  url.searchParams.set('ts', String(Date.now()));
                  window.location.replace(url.toString() + '#ocrSection');
                  return;
                }
                if (tries < 80) setTimeout(poll, 1200);
              })
              .catch(() => { if (tries < 80) setTimeout(poll, 1500); });
          } catch(e) { if (tries < 80) setTimeout(poll, 1500); }
        };
        setTimeout(poll, 900);
      }
    }
  } catch (e) {}
})();


function recipeUnitOptionsFor(base){
  const b=(base||'ud').toLowerCase();
  if(b==='g' || b==='kg') return ['g','kg'];
  if(b==='ml' || b==='l') return ['g','kg'];
  return [b||'ud'];
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

function initReceiptOCRDraftState(){
  try{
    const section = document.getElementById('ocrSection');
    if(!section) return;
    const receiptId = (section.querySelector('[data-ocr-supplier-form="1"]') || section.querySelector('[data-ocr-line-form="1"]'))?.dataset.receiptId || '';
    if(!receiptId) return;
    const key = `receipt_ocr_draft_${receiptId}`;
    let state = {};
    try{ state = JSON.parse(localStorage.getItem(key) || '{}') || {}; }catch(e){ state = {}; }
    const save = ()=>{ try{ localStorage.setItem(key, JSON.stringify(state)); }catch(e){} };

    const supplierForm = section.querySelector('[data-ocr-supplier-form="1"]');
    if(supplierForm){
      const q = supplierForm.querySelector('[data-ocr-supplier-query="1"]');
      const c = supplierForm.querySelector('[data-ocr-supplier-create="1"]');
      if(q){
        if(state.supplier_query && !q.value) q.value = state.supplier_query;
        q.addEventListener('input', ()=>{ state.supplier_query = q.value || ''; save(); });
      }
      if(c){
        if(typeof state.supplier_create === 'boolean') c.checked = state.supplier_create;
        c.addEventListener('change', ()=>{ state.supplier_create = !!c.checked; save(); });
      }
      supplierForm.addEventListener('submit', ()=>{
        if(q) state.supplier_query = q.value || '';
        if(c) state.supplier_create = !!c.checked;
        save();
      });
    }

    section.querySelectorAll('[data-ocr-line-form="1"]').forEach((form)=>{
      const lineId = form.dataset.ocrLineId;
      if(!lineId) return;
      state.lines = state.lines || {};
      state.lines[lineId] = state.lines[lineId] || {};
      const item = form.querySelector('[data-ocr-item-query="1"]');
      const create = form.querySelector('[data-ocr-create-if-missing="1"]');
      const unit = form.querySelector('[data-ocr-unit-family="1"]');
      const ls = state.lines[lineId];
      if(item && ls.item_query && (!item.value || item.value.length < ls.item_query.length)) item.value = ls.item_query;
      if(create && typeof ls.create_if_missing === 'boolean') create.checked = ls.create_if_missing;
      if(unit && ls.unit_family) unit.value = ls.unit_family;
      if(item) item.addEventListener('input', ()=>{ ls.item_query = item.value || ''; save(); });
      if(create) create.addEventListener('change', ()=>{ ls.create_if_missing = !!create.checked; save(); });
      if(unit) unit.addEventListener('change', ()=>{ ls.unit_family = unit.value || ''; save(); });
      form.addEventListener('submit', ()=>{
        if(item) ls.item_query = item.value || '';
        if(create) ls.create_if_missing = !!create.checked;
        if(unit) ls.unit_family = unit.value || '';
        state.last_submitted_line = lineId;
        save();
      });
    });
  }catch(e){ console.log(e); }
}
document.addEventListener('DOMContentLoaded', initReceiptOCRDraftState);

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
