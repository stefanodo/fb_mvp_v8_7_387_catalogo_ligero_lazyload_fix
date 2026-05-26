(function(){
  'use strict';
  const $=(s,root=document)=>root.querySelector(s);
  const $$=(s,root=document)=>Array.from(root.querySelectorAll(s));
  const panel=$('#alfiCentralPanel');
  if(!panel) return;
  const text=$('#alfiText');
  const requestedBy=$('#alfiRequestedBy');
  const execute=$('#alfiExecute');
  const preview=$('#alfiPreview');
  const result=$('#alfiResult');
  const status=$('#alfiStatus');
  const speakToggle=$('#alfiSpeak');
  const mic=$('#alfiMic');
  const stop=$('#alfiStop');
  const testVoice=$('#alfiTestVoice');
  let mediaRecorder=null, stream=null, chunks=[];
  let suggestTimer=null;
  let recordMode='execute';
  let recordTimer=null;
  function setAlfiView(view){ document.body.dataset.alfiView=view||'dictar'; $$('[data-alfi-tab]').forEach(b=>b.classList.toggle('active', b.dataset.alfiTab===document.body.dataset.alfiView)); }
  setAlfiView('dictar');

  function esc(v){ return String(v||'').replace(/[&<>"']/g, ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function centerId(){ const h=document.querySelector('input[name="center_id"]'); return h ? (h.value||'0') : (document.getElementById('macVoiceAssistant')?.dataset.centerId||'0'); }
  function note(msg, cls){ if(status){ status.textContent=msg; status.className='op-help '+(cls||''); } }
  function speak(msg){ if(!speakToggle || !speakToggle.checked || !('speechSynthesis' in window)) return; try{ speechSynthesis.cancel(); let m=String(msg||''); if(m.length>115) m=m.slice(0,112)+'... revisa la pantalla.'; const u=new SpeechSynthesisUtterance(m); u.lang='es-ES'; u.rate=.98; speechSynthesis.speak(u); }catch(_){} }
  function norm(s){ return String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,''); }
  function extractResponsible(v){
    const s=norm(v); const m=s.match(/\bsoy\s+([a-z]+(?:\s+[a-z]+)?)/) || s.match(/\bresponsable\s+([a-z]+(?:\s+[a-z]+)?)/);
    if(!m) return '';
    const stops=new Set(['pedido','pide','agrega','añade','anade','produccion','produce','merma','hay','quiero','necesito','de','por','al','hacer','preparar']);
    return (m[1]||'').split(/\s+/).filter(w=>w&&!stops.has(w)).slice(0,2).map(w=>w[0].toUpperCase()+w.slice(1)).join(' ');
  }
  function panelForIntent(intent){
    const map={'PEDIDO':'#opPanelOrders','PRODUCCIÓN':'#opPanelProductions','MERMA':'#opPanelWaste'};
    return map[intent] ? $(map[intent]) : null;
  }
  function highlight(intent){
    $$('[data-op-panel]').forEach(p=>p.classList.remove('active-panel','flash-panel'));
    const p=panelForIntent(intent); if(p){ p.classList.add('active-panel','flash-panel'); setTimeout(()=>p.classList.remove('flash-panel'),1800); }
  }
  function render(data, mode){
    if(!result) return;
    data=data||{};
    const msg=data.message || 'Sin respuesta.';
    const er=data.expert_review || {};
    const parsed=data.parsed || {};
    const missing=Array.isArray(er.missing_fields)?er.missing_fields:[];
    const warnings=Array.isArray(er.warnings)?er.warnings:[];
    const suggestions=(data.suggestions||[]).filter(x=>x&&x.url&&x.label).slice(0,5);
    const links=[];
    if(data.redirect_url) links.push({label:'Abrir propuesta en Operativa', url:data.redirect_url});
    if(data.module_url) links.push({label:'Abrir módulo', url:data.module_url});
    suggestions.forEach(s=>links.push(s));
    const uniq=[]; const seen=new Set(); links.forEach(l=>{ if(l.url && !seen.has(l.url+l.label)){ seen.add(l.url+l.label); uniq.push(l); } });
    const parsedItems=Array.isArray(parsed.items)?parsed.items:[];
    const itemRows=parsedItems.slice(0,3).map(it=>'<li><b>'+esc((it.name||it.raw_name||'').toString().toUpperCase()||'Sin identificar')+'</b> · '+esc(it.qty||0)+' '+esc(it.unit||'')+'</li>').join('');
    result.hidden=false;
    result.innerHTML=
      '<div class="op-intent-head"><strong>'+esc(mode==='preview'?'Prelectura':'Resultado')+': '+esc(data.intent||'NO_ENTENDIDO')+'</strong><span>'+esc(data.status||'')+'</span></div>'+ 
      (data.normalized_text?'<p class="op-corrected"><strong>Texto limpio:</strong> '+esc(data.normalized_text)+'</p>':'')+
      '<p class="alfi-message">'+esc(msg)+'</p>'+ 
      '<div class="alfi-review-grid">'+
        '<div><span>Elemento</span><strong>'+esc(er.main_item||'—')+'</strong></div>'+ 
        '<div><span>Cantidad</span><strong>'+esc(er.qty?String(er.qty):'—')+' '+esc(er.unit||'')+'</strong></div>'+ 
        '<div><span>Riesgo</span><strong>'+esc(er.risk_level||'—')+'</strong></div>'+ 
        '<div><span>Confianza</span><strong>'+esc(Math.round(Number(er.confidence||data.confidence||0)*100))+'%</strong></div>'+ 
      '</div>'+ 
      (missing.length?'<div class="op-clarify">Falta: '+esc(missing.join(', '))+'</div>':'')+
      (warnings.length?'<div class="op-clarify soft">Avisos: '+esc(warnings.join(', '))+'</div>':'')+
      (itemRows?'<ul class="alfi-items">'+itemRows+'</ul>':'')+
      (uniq.length?'<div class="mini-actions alfi-links">'+uniq.slice(0,6).map(l=>'<a href="'+esc(l.url)+'">'+esc(l.label)+'</a>').join('')+'</div>':'');
    highlight(data.intent);
    setAlfiView('resultado');
    speak(msg);
  }

  async function refreshAudioDiagnostics(){
    const el=$('#alfiAudioDiag'); if(!el) return;
    const browserOk=!!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
    let server='sin comprobar';
    try{
      const r=await fetch('/api/oido-alfi/audio-diagnostics',{headers:{Accept:'application/json'}});
      const j=await r.json();
      server=j.backend_stt_ready ? ('STT servidor activo · '+(j.stt_provider||j.stt_mode||'')+' · '+(j.stt_model||'')) : 'STT servidor no configurado';
    }catch(_){ server='no pude comprobar STT servidor'; }
    el.textContent='Voz: navegador '+(browserOk?'permite grabación directa':'no garantiza grabación directa')+' · '+server+'. En móvil, si falla, usa el micrófono del teclado y Ejecutar.';
    el.className='op-help alfi-audio-diag '+(browserOk?'ok':'warn');
  }

  async function previewNow(){
    const q=(text.value||'').trim(); if(!q){ note('Escribe o dicta una orden.', 'warn'); text?.focus(); return null; }
    const name=extractResponsible(q); if(name && requestedBy && !requestedBy.value.trim()) requestedBy.value=name;
    note('Analizando sin ejecutar…','ok');
    try{
      const qs=new URLSearchParams({text:q, center_id:centerId()});
      const r=await fetch('/api/oido-alfi/suggest?'+qs.toString(), {headers:{Accept:'application/json'}});
      const data=await r.json(); render(data,'preview'); note('Prelectura lista. Revisa y pulsa Ejecutar si procede.', data.intent==='NO_ENTENDIDO'?'warn':'ok'); return data;
    }catch(e){ note('No pude previsualizar. Revisa conexión.', 'warn'); return null; }
  }
  async function executeNow(){
    const q=(text.value||'').trim(); if(!q){ note('Escribe o dicta una orden.', 'warn'); text?.focus(); return null; }
    const name=extractResponsible(q); if(name && requestedBy && !requestedBy.value.trim()) requestedBy.value=name;
    note('Ejecutando de forma segura…','ok');
    const fd=new FormData(); fd.append('center_id', centerId()); fd.append('text', q); fd.append('requested_by', (requestedBy?.value||''));
    try{
      const r=await fetch('/api/oido-alfi/command', {method:'POST', body:fd, headers:{Accept:'application/json'}});
      const data=await r.json(); render(data,'execute'); note(data.ok?'Acción segura creada o consulta respondida.':'Necesita revisión.', data.ok?'ok':'warn'); return data;
    }catch(e){ note('No pude ejecutar. Revisa conexión.', 'warn'); return null; }
  }

  function renderVoiceTest(data){
    result.hidden=false;
    const raw=data.raw_text || data.text || '';
    const clean=data.text || data.normalized_text || '';
    const action=data.preview || data.action_result || {};
    result.innerHTML='<div class="alfi-test-box"><strong>Prueba de voz sin crear nada</strong>'+
      '<p>Audio recibido: '+(data.audio_received?'sí':'sí')+' · Motor: '+esc(data.source||data.model||'STT servidor')+'</p>'+
      '<span>Transcripción bruta</span><code>'+esc(raw||'Sin texto')+'</code>'+
      '<span>Texto limpio</span><code>'+esc(clean||'Sin texto limpio')+'</code>'+
      '<span>Decisión</span><code>'+esc((action.intent||'NO_ENTENDIDO')+' · '+(action.message||data.message||''))+'</code></div>';
    setAlfiView('resultado');
  }

  async function uploadAudio(blob, mode){
    const fd=new FormData(); fd.append('center_id', centerId()); fd.append('requested_by', requestedBy?.value||''); fd.append('file', blob, 'oido_alfi.webm');
    note('Transcribiendo audio en español…','ok');
    try{
      const endpoint = mode==='test' ? '/api/oido-alfi/transcribe-test' : '/api/oido-alfi/transcribe-audio';
      const r=await fetch(endpoint, {method:'POST', body:fd, headers:{Accept:'application/json'}});
      const data=await r.json();
      if(mode==='test'){ if(data.text) text.value=data.text; renderVoiceTest(data); note(data.message||'Prueba de voz terminada. No se creó nada.', data.ok?'ok':'warn'); return data; }
      if(data.text){ text.value=data.text; render(data.action_result||data,'execute'); note(data.message||'Audio procesado.', data.ok?'ok':'warn'); }
      else { render(data,'execute'); note(data.message||'No pude transcribir. Usa el micrófono del teclado.', 'warn'); text?.focus(); }
      return data;
    }catch(e){ note('No pude enviar audio. Usa el micrófono del teclado en el campo.', 'warn'); text?.focus(); }
  }
  async function startRecording(mode){
    recordMode = mode || 'execute';
    if(!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)){
      note('Este navegador no permite grabación directa. Usa el micrófono del teclado dentro del campo.', 'warn'); text?.focus(); return;
    }
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:true}); chunks=[]; mediaRecorder=new MediaRecorder(stream);
      mediaRecorder.ondataavailable=e=>{ if(e.data&&e.data.size) chunks.push(e.data); };
      mediaRecorder.onstop=()=>{ try{stream.getTracks().forEach(t=>t.stop());}catch(_){} const blob=new Blob(chunks,{type:mediaRecorder.mimeType||'audio/webm'}); mediaRecorder=null; stream=null; if(mic) mic.hidden=false; if(stop) stop.hidden=true; if(blob.size) uploadAudio(blob, recordMode); };
      mediaRecorder.start(); if(mic) mic.hidden=true; if(stop) stop.hidden=false; note(recordMode==='test'?'Prueba de voz: grabando 5 segundos. No se creará nada.':'Grabando. Pulsa Parar y analizar.', 'ok'); if(recordMode==='test'){ clearTimeout(recordTimer); recordTimer=setTimeout(stopRecording, 5200); }
    }catch(e){ note('Safari/navegador no permitió grabar. Usa el micrófono del teclado dentro del campo.', 'warn'); text?.focus(); }
  }
  function stopRecording(){ clearTimeout(recordTimer); try{ if(mediaRecorder && mediaRecorder.state!=='inactive'){ mediaRecorder.stop(); return; } }catch(_){} try{stream?.getTracks()?.forEach(t=>t.stop());}catch(_){} if(mic) mic.hidden=false; if(stop) stop.hidden=true; }

  $$('[data-alfi-fill]', panel).forEach(b=>b.addEventListener('click',()=>{ text.value=b.dataset.alfiFill||''; text.focus(); previewNow(); }));
  text?.addEventListener('input',()=>{ const name=extractResponsible(text.value); if(name && requestedBy && !requestedBy.value.trim()) requestedBy.value=name; clearTimeout(suggestTimer); suggestTimer=setTimeout(()=>previewNow(),700); });
  preview?.addEventListener('click', previewNow);
  execute?.addEventListener('click', executeNow);
  mic?.addEventListener('click', ()=>startRecording('execute'));
  testVoice?.addEventListener('click', ()=>startRecording('test'));
  $$('[data-alfi-tab]').forEach(b=>b.addEventListener('click',()=>setAlfiView(b.dataset.alfiTab||'dictar')));
  stop?.addEventListener('click', stopRecording);
  refreshAudioDiagnostics();

  // Soporte para abrir directamente una cola tras crear borrador.
  const params=new URL(location.href).searchParams; const opType=params.get('op_type'); const line=params.get('op_line');
  const intentMap={ORDER:'PEDIDO',PRODUCTION:'PRODUCCIÓN',WASTE:'MERMA'}; if(opType) highlight(intentMap[opType]||opType);
  if(line){ const el=document.getElementById('op-line-'+line); if(el){ el.scrollIntoView({behavior:'smooth', block:'center'}); el.classList.add('flash-panel'); } }
})();
