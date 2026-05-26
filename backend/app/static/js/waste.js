(function(){
  function setWasteVoiceNote(msg, cls){
    const box = document.getElementById('wasteVoiceSupport');
    if(!box) return;
    box.className = 'waste-voice-support' + (cls ? ' ' + cls : '');
    box.textContent = msg || '';
    box.hidden = !msg;
  }
  window.wasteStartVoice = async function(targetId){
    const target = document.getElementById(targetId);
    if(!target){ return; }
    if(window.__wasteRecorder && window.__wasteRecorder.state && window.__wasteRecorder.state !== 'inactive'){
      try{ window.__wasteRecorder.stop(); setWasteVoiceNote('Detenido. Analizando audio…', 'ok'); }catch(e){}
      return;
    }
    const fallbackMsg = 'Este iPhone puede seguir funcionando por voz usando el micrófono del teclado. Pulsa dentro del campo y dicta con el micrófono del teclado de iOS.';
    // 1) Intento preferente: audio real a OpenAI STT, si el navegador lo permite.
    if(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder){
      try{
        const stream = await navigator.mediaDevices.getUserMedia({audio:true});
        const chunks=[];
        const mr = new MediaRecorder(stream);
        mr.ondataavailable = ev => { if(ev.data && ev.data.size) chunks.push(ev.data); };
        mr.onstop = async () => {
          stream.getTracks().forEach(t=>t.stop());
          const blob = new Blob(chunks, {type: mr.mimeType || 'audio/webm'});
          const ext = (blob.type || '').includes('mp4') ? 'm4a' : ((blob.type || '').includes('ogg') ? 'ogg' : 'webm');
          const fd = new FormData();
          fd.append('audio', blob, 'merma.'+ext);
          fd.append('task_mode', 'WASTE');
          setWasteVoiceNote('Transcribiendo audio real con IA…', 'ok');
          try{
            const res = await fetch('/api/operativa/transcribe', {method:'POST', body:fd, headers:{'Accept':'application/json'}});
            const data = await res.json();
            if(data && data.ok && data.text){
              target.value = (target.value ? target.value + ' ' : '') + data.text;
              target.dispatchEvent(new Event('input', {bubbles:true}));
              setWasteVoiceNote('Audio transcrito. Revisa y pulsa Crear pendiente.', 'ok');
            }else{
              setWasteVoiceNote((data && data.error) || fallbackMsg, 'warn');
              target.focus();
            }
          }catch(e){ setWasteVoiceNote('No pude enviar el audio. Usa el micrófono del teclado del iPhone.', 'warn'); target.focus(); }
        };
        mr.start();
        setWasteVoiceNote('Grabando audio real… pulsa otra vez “Dictar ahora” para detener, o se detendrá solo en 8 segundos.', 'ok');
        window.__wasteRecorder = mr;
        window.__wasteRecorderStream = stream;
        const stopOnce = () => { try{ if(window.__wasteRecorder && window.__wasteRecorder.state !== 'inactive') window.__wasteRecorder.stop(); }catch(e){} target.removeEventListener('focus', stopOnce); };
        // No hay segundo botón en este panel; detenemos automáticamente a los 5 segundos para evitar grabaciones colgadas.
        setTimeout(()=>{ try{ if(mr.state !== 'inactive') mr.stop(); }catch(e){} }, 8000);
        return;
      }catch(e){
        setWasteVoiceNote('El navegador no permitió grabación real de audio. Si entras por http://IP_DEL_MAC, iPhone puede bloquear el micrófono real. Uso dictado web/teclado.', 'warn');
      }
    }
    // 2) Fallback: Web Speech / teclado iOS.
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!SR){
      setWasteVoiceNote(fallbackMsg, 'warn');
      target.focus();
      target.setSelectionRange && target.setSelectionRange(target.value.length, target.value.length);
      return;
    }
    const rec = new SR();
    rec.lang = 'es-ES'; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onstart = function(){ setWasteVoiceNote('Escuchando… di la merma con producto, cantidad, motivo y responsable.', 'ok'); };
    rec.onresult = function(ev){
      const txt = ev.results && ev.results[0] && ev.results[0][0] ? ev.results[0][0].transcript : '';
      if(txt){
        target.value = (target.value ? target.value + ' ' : '') + txt;
        target.dispatchEvent(new Event('input', {bubbles:true}));
        setWasteVoiceNote('Texto capturado. Revisa la propuesta y crea la merma pendiente.', 'ok');
      }
    };
    rec.onerror = function(){ setWasteVoiceNote(fallbackMsg, 'warn'); target.focus(); };
    rec.onend = function(){ if(document.activeElement !== target && !target.value){ target.focus(); } };
    try{ rec.start(); }catch(e){ setWasteVoiceNote(fallbackMsg, 'warn'); target.focus(); }
  };
})();


(function(){
  function showWastePanel(mode){
    const map={voice:'wastePanelVoice',photo:'wastePanelPhoto',manual:'wastePanelManual'};
    document.querySelectorAll('.waste-panel').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('[data-waste-mode]').forEach(b=>b.classList.remove('active'));
    const panel=document.getElementById(map[mode]||map.voice);
    if(panel){ panel.classList.add('active'); panel.scrollIntoView({behavior:'smooth', block:'center'}); }
    const btn=document.querySelector('[data-waste-mode="'+mode+'"]');
    if(btn){ btn.classList.add('active'); }
  }
  window.showWastePanel = showWastePanel;
  function initWasteAssistant(){
    document.querySelectorAll('[data-waste-mode]').forEach(btn=>{
      btn.addEventListener('click', ()=>showWastePanel(btn.dataset.wasteMode || 'voice'));
    });
    const first=document.querySelector('[data-waste-mode="voice"]');
    if(first) first.classList.add('active');
    const params=new URL(location.href).searchParams;
    const wid=params.get('wid');
    if(wid){ const row=document.getElementById('waste-'+wid); if(row){ row.scrollIntoView({behavior:'smooth', block:'center'}); row.classList.add('flash-row'); setTimeout(()=>row.classList.remove('flash-row'), 1800); } }
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', initWasteAssistant); else initWasteAssistant();
})();

// v8_7_334 · Anular merma sin flash/recarga visual completa.
document.addEventListener('submit', async function(e){
  const form = e.target && e.target.matches ? e.target : null;
  if(!form || !String(form.action||'').match(/\/waste\/\d+\/cancel/)) return;
  e.preventDefault();
  if(!confirm('Anular esta merma?')) return;
  const row = form.closest('.waste-row');
  if(row) row.classList.add('is-cancelling');
  try{
    const res = await fetch(form.action, {method:'POST', body:new FormData(form), headers:{'X-Requested-With':'fetch'}});
    if(!res.ok) throw new Error('HTTP '+res.status);
    if(row){
      row.classList.remove('is-cancelling');
      row.classList.remove('status-review','status-draft');
      row.classList.add('status-cancelled');
      row.querySelectorAll('.waste-row-actions form').forEach(x=>x.remove());
      const actions = row.querySelector('.waste-row-actions') || row;
      if(!actions.querySelector('.status-chip.cancelled')) actions.insertAdjacentHTML('beforeend','<span class="status-chip cancelled">Merma anulada</span>');
      row.querySelectorAll('.waste-tags span').forEach(sp=>{ if(['REVIEW','DRAFT'].includes((sp.textContent||'').trim())) sp.textContent='CANCELLED'; });
    }else{
      location.reload();
    }
  }catch(err){
    if(row) row.classList.remove('is-cancelling');
    form.submit();
  }
}, true);


// v8_7_357 · Autocompletado manual de mermas: no abre todo el catálogo al entrar.
(function(){
  function normalize(s){
    return String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toUpperCase().trim();
  }
  function initWasteManualAutocomplete(){
    const source = document.getElementById('wasteManualArticleSource');
    const input = document.getElementById('wasteManualArticleSearch');
    const hidden = document.getElementById('wasteManualArticleId');
    const fallback = document.getElementById('wasteManualFallbackName');
    const unitSel = document.querySelector('#wastePanelManual select[name="unit"]');
    const box = document.getElementById('wasteManualArticleSuggestions');
    if(!source || !input || !hidden || !box) return;
    const items = Array.from(source.options).filter(o=>String(o.value||'0')!=='0').map(o=>{
      const raw = (o.textContent||'').trim();
      const parts = raw.split('·');
      const name = (parts[0]||raw).trim();
      const unit = (o.dataset.unit || (parts[1]||'kg').trim() || 'kg').trim();
      return {id:o.value, name, unit, text:raw, key:normalize(raw+' '+name)};
    });
    function hide(){ box.hidden=true; box.innerHTML=''; }
    function choose(it){
      hidden.value = it.id || '0';
      input.value = it.name || '';
      if(fallback) fallback.value = '';
      if(unitSel && it.unit){ unitSel.value = it.unit; }
      hide();
    }
    function render(){
      const q = normalize(input.value);
      hidden.value='0';
      if(q.length < 2){ hide(); return; }
      const res = items.filter(it=>it.key.includes(q)).slice(0,8);
      if(!res.length){
        box.innerHTML = '<div class="empty">Sin coincidencias. Si es nuevo, déjalo escrito y se guardará para revisión.</div>';
        box.hidden=false;
        if(fallback && !fallback.value) fallback.value = input.value;
        return;
      }
      box.innerHTML = res.map((it,idx)=>'<button type="button" data-idx="'+idx+'"><span>'+it.name.replace(/</g,'&lt;')+'</span><small>'+it.unit.replace(/</g,'&lt;')+'</small></button>').join('');
      box.hidden=false;
      box.querySelectorAll('button').forEach((b,i)=>b.addEventListener('click',()=>choose(res[i])));
      if(fallback) fallback.value = input.value;
    }
    input.addEventListener('input', render);
    input.addEventListener('focus', function(){ if(normalize(input.value).length>=2) render(); });
    input.addEventListener('keydown', function(e){ if(e.key==='Escape') hide(); });
    document.addEventListener('click', function(e){ if(!box.contains(e.target) && e.target !== input) hide(); });
    const form = input.closest('form');
    if(form){
      form.addEventListener('submit', function(){
        if(hidden.value === '0' && fallback && !fallback.value.trim()) fallback.value = input.value.trim();
      });
    }
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', initWasteManualAutocomplete); else initWasteManualAutocomplete();
})();
