(function(){
  'use strict';
  const $=(s,root=document)=>root.querySelector(s);
  const $$=(s,root=document)=>Array.from(root.querySelectorAll(s));
  const norm=s=>(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
  function page(){return document.body.dataset.page||'inicio'}
  function centerId(){ const root=$('#macVoiceAssistant'); const n=parseInt(root?.dataset.centerId||'0',10); return Number.isFinite(n)?n:0; }
  function go(p, extra){ const qs=new URLSearchParams({page:p, center_id:String(centerId()||0)}); if(extra) Object.entries(extra).forEach(([k,v])=>qs.set(k,String(v))); location.href='/?'+qs.toString(); return true; }
  function statusEl(){return $('#macVoiceStatus')}
  function speak(text){
    const ck=$('#macVoiceSpeak');
    if(!ck || !ck.checked || !('speechSynthesis' in window)) return;
    try{ window.speechSynthesis.cancel(); const u=new SpeechSynthesisUtterance(text); u.lang='es-ES'; u.rate=.98; window.speechSynthesis.speak(u); }catch(_){ }
  }
  function say(msg, cls){ const el=statusEl(); if(el){ el.textContent=msg; el.className='mac-voice-status '+(cls||''); } speak(msg.replace(/^[✅⚠️✕]+\s*/,'')); }
  function answerEl(){ return $('#macVoiceAnswer'); }
  function clearAnswer(){ const el=answerEl(); if(el){ el.hidden=true; el.textContent=''; } }
  function renderAnswer(data){
    const el=answerEl(); if(!el || !data) return;
    const msg=data.message||'Sin respuesta.';
    const pageLink=data.open_page ? '/?page='+encodeURIComponent(data.open_page)+'&center_id='+String(centerId()||0) : '';
    const extra=[];
    if(data.intent){ extra.push('<span class="muted">Intención:</span> <b>'+escapeHtml(data.intent)+'</b>'); }
    if(data.normalized_text){ extra.push('<span class="muted">Texto limpio:</span> <b>'+escapeHtml(data.normalized_text)+'</b>'); }
    if(data.supplier && data.supplier.name){ extra.push('<span class="muted">Proveedor:</span> <b>'+escapeHtml(data.supplier.name)+'</b>'); }
    if(data.item && data.item.name){ extra.push('<span class="muted">Insumo:</span> <b>'+escapeHtml(data.item.name)+'</b>'); }
    const suggestions=(data.suggestions||[]).filter(x=>x&&x.url&&x.label).slice(0,4).map(x=>'<a href="'+escapeHtml(x.url)+'">'+escapeHtml(x.label)+'</a>').join('');
    el.innerHTML='<div>'+escapeHtml(msg)+'</div>'+(extra.length?'<div class="mac-voice-meta">'+extra.join(' · ')+'</div>':'')+(suggestions?'<div class="mini-actions">'+suggestions+'</div>':'')+(pageLink&&!suggestions?'<div class="mini-actions"><a href="'+pageLink+'">Abrir pantalla relacionada</a></div>':'');
    el.hidden=false;
  }
  function escapeHtml(s){ return String(s||'').replace(/[&<>"']/g, ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function isInfoQuery(c){
    return /(^| )(telefono|teléfono|mail|email|correo|contacto|datos|reparto|entrega|dias|días|minimo|mínimo|condiciones|notas)( |$)/.test(c) ||
      c.includes('de que proveedor') || c.includes('de qué proveedor') || c.includes('proveedor de') || c.includes('proveedor del') || c.includes('quien vende') || c.includes('quién vende') || c.includes('que proveedor tiene') || c.includes('qué proveedor tiene') ||
      c.includes('hay ') || c.includes('cuanto queda') || c.includes('cuánto queda') || c.includes('tengo stock');
  }
  async function apiInfo(raw){
    const qs=new URLSearchParams({q:raw||'', center_id:String(centerId()||0)});
    try{ const r=await fetch('/api/oido-alfi/query?'+qs.toString(), {headers:{'Accept':'application/json'}}); const data=await r.json(); renderAnswer(data); if(data.message) say(data.message, data.ok?'ok':'warn'); return data; }
    catch(e){ say('OÍDO ALFI no pudo consultar datos. Abro la pantalla relacionada para revisar.','warn'); return null; }
  }

  async function apiAssistant(raw){
    const fd=new FormData();
    fd.append('center_id', String(centerId()||0));
    fd.append('text', raw||'');
    const by=$('#macVoiceRequestedBy')?.value||'';
    if(by) fd.append('requested_by', by);
    try{
      const r=await fetch('/api/oido-alfi/command', {method:'POST', body:fd, headers:{'Accept':'application/json'}});
      const data=await r.json();
      renderAnswer(data);
      if(data.message) say(data.message, data.ok?'ok':'warn');
      return data;
    }catch(e){ return null; }
  }

  let suggestTimer=null;
  async function apiSuggest(raw){
    const txt=(raw||'').trim();
    if(txt.length<4){ return; }
    const qs=new URLSearchParams({text:txt, center_id:String(centerId()||0)});
    try{
      const r=await fetch('/api/oido-alfi/suggest?'+qs.toString(), {headers:{'Accept':'application/json'}});
      const data=await r.json();
      if(data && data.status==='PREVIEW') renderAnswer(data);
    }catch(_){}
  }

  let mediaRecorder=null, audioChunks=[], recordingStream=null;
  function canRecordAudio(){ return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder); }
  async function uploadAudioBlob(blob){
    const fd=new FormData();
    fd.append('center_id', String(centerId()||0));
    const by=$('#macVoiceRequestedBy')?.value||'';
    if(by) fd.append('requested_by', by);
    fd.append('file', blob, 'oido_alfi.webm');
    try{
      say('Transcribiendo con OÍDO ALFI…','ok');
      const r=await fetch('/api/oido-alfi/transcribe-audio', {method:'POST', body:fd, headers:{'Accept':'application/json'}});
      const data=await r.json();
      if(data.text && $('#macVoiceCommand')) $('#macVoiceCommand').value=data.text;
      if(data.action_result) renderAnswer(data.action_result); else renderAnswer(data);
      say(data.message || data.text || 'Audio procesado.', data.ok?'ok':'warn');
      return data;
    }catch(e){ say('No pude enviar el audio. Usa el micrófono del teclado en el campo de texto.','warn'); return null; }
  }
  async function startAudioRecording(listen, stop){
    if(!canRecordAudio()) return false;
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:true});
      recordingStream=stream; audioChunks=[];
      mediaRecorder=new MediaRecorder(stream);
      mediaRecorder.ondataavailable=e=>{ if(e.data && e.data.size>0) audioChunks.push(e.data); };
      mediaRecorder.onstop=async()=>{
        try{ recordingStream?.getTracks()?.forEach(t=>t.stop()); }catch(_){}
        recordingStream=null;
        if(listen) listen.hidden=false; if(stop) stop.hidden=true;
        const blob=new Blob(audioChunks, {type: mediaRecorder?.mimeType || 'audio/webm'});
        mediaRecorder=null; audioChunks=[];
        if(blob.size>0) await uploadAudioBlob(blob); else say('No se grabó audio.','warn');
      };
      mediaRecorder.start();
      say('Grabando audio. Pulsa Parar al terminar.','ok');
      if(listen) listen.hidden=true; if(stop) stop.hidden=false;
      return true;
    }catch(e){
      say('Safari/navegador no permitió grabar audio. Usa el micrófono del teclado dentro del campo.','warn');
      return false;
    }
  }
  function stopAudioRecording(){
    try{ if(mediaRecorder && mediaRecorder.state !== 'inactive'){ mediaRecorder.stop(); return true; } }catch(_){}
    try{ recordingStream?.getTracks()?.forEach(t=>t.stop()); }catch(_){}
    return false;
  }


  function clickFirst(selectors){ for(const s of selectors){ const el=$(s); if(el){ el.click(); return true; }} return false; }
  function submitFirst(selectors){ for(const s of selectors){ const el=$(s); if(el){ const f=el.closest('form'); if(f){ f.requestSubmit?f.requestSubmit():f.submit(); return true;} el.click(); return true; }} return false; }
  function scrollToSel(selectors){ for(const s of selectors){ const el=$(s); if(el){ el.scrollIntoView({behavior:'smooth',block:'center'}); return true; }} return false; }
  function chooseRadioByValue(name,value){ const el=$(`input[name="${name}"][value="${value}"]`); if(el){ el.checked=true; el.dispatchEvent(new Event('change',{bubbles:true})); return true;} return false; }

  function createOrder(){
    if(page() !== 'pedidos') return go('pedidos');
    const form=$('form[action="/order/new_form"]'); if(!form){ say('No encuentro el formulario de nuevo pedido.','err'); return true; }
    const resp=form.querySelector('select[name="responsible_user_id"]');
    if(resp && !resp.value){ const first=Array.from(resp.options).find(o=>o.value); if(first){ resp.value=first.value; resp.dispatchEvent(new Event('change',{bubbles:true})); } else { say('Falta responsable activo antes de crear pedido.','warn'); return true; } }
    say('Creo un pedido borrador para revisar.','ok'); form.requestSubmit?form.requestSubmit():form.submit(); return true;
  }
  function createProduction(){ if(page()!=='producciones') return go('producciones'); const f=$('form[action="/production/new_form"]'); if(!f){ say('No encuentro el formulario de nueva producción.','err'); return true;} say('Creo una producción borrador.','ok'); f.requestSubmit?f.requestSubmit():f.submit(); return true; }
  function createReceipt(){ if(page()!=='albaranes') return go('albaranes'); say('Abro nuevo albarán. Añade fotos y revisa antes de validar.','ok'); scrollToSel(['#receiptNewForm','form[action="/receipt/new_form"]']); return true; }
  function createWaste(raw){
    const cid=centerId(); if(!cid){ say('Selecciona un local concreto para registrar merma. En “Todos” no descuento stock.','warn'); return go('mermas'); }
    const form=document.createElement('form'); form.method='POST'; form.action='/waste/from_voice'; form.enctype='multipart/form-data';
    const fields={center_id:String(cid), responsible_user_id:'0', responsible_name:'', voice_text:raw||'', photo_note:''};
    Object.entries(fields).forEach(([k,v])=>{ const i=document.createElement('input'); i.type='hidden'; i.name=k; i.value=v; form.appendChild(i); });
    document.body.appendChild(form); say('Creo merma pendiente para revisar antes de confirmar.','ok'); form.submit(); return true;
  }
  function showOrderBlock(cmd){
    if(page()!=='pedidos') return go('pedidos');
    const map=[['verduras','fresh','verduras'],['pescados','fresh','pescados'],['pescado','fresh','pescados'],['carnes','fresh','carnes'],['carne','fresh','carnes'],['huevos','fresh','huevos'],['lacteos','fresh','lacteos'],['lácteos','fresh','lacteos'],['frescos','fresh','all'],['congelados','frozen',null],['secos','dry',null],['limpieza','clean',null],['producciones','prod',null]];
    const hit=map.find(m=>cmd.includes(m[0])); if(!hit) return false;
    chooseRadioByValue('block_key',hit[1]); if(hit[2]) chooseRadioByValue('fresh_group_filter',hit[2]);
    scrollToSel(['#orderAddLine','[data-order-block-list]']); say('Muestro '+hit[0]+' en pedidos.','ok'); return true;
  }
  function consult(cmd){
    if(cmd.includes('stock') || cmd.includes('hay ') || cmd.includes('insumo') || cmd.includes('insumos')){ say('Abro Stock. Usa el buscador para verificar existencia, cantidades y ubicación.','ok'); return go('stock'); }
    if(cmd.includes('pedir') || cmd.includes('bajo minimo') || cmd.includes('bajo mínimo')){ say('Abro Inicio con alertas y Pedidos para ver sugerencias.','ok'); return go('inicio'); }
    if(cmd.includes('venta') || cmd.includes('ventas') || cmd.includes('platos')){ say('Abro Inicio. El ranking de ventas aparecerá cuando haya TPV normalizado.','ok'); return go('inicio'); }
    if(cmd.includes('margen') || cmd.includes('proveedor subio') || cmd.includes('proveedor subió')){ say('Abro Dashboard de dirección para revisar margen y proveedores.','ok'); return go('inicio'); }
    return false;
  }
  async function command(raw){
    const c=norm(raw); if(!c) return;
    clearAnswer();
    const central=await apiAssistant(raw);
    if(central && central.handled && central.action_type !== 'FALLBACK'){
      if(central.redirect_url){ setTimeout(()=>{ location.href=central.redirect_url; }, 650); }
      return true;
    }
    if(isInfoQuery(c)){
      const data=await apiInfo(raw);
      if(data && data.type && data.type !== "fallback") return true;
    }
    if(consult(c)) return true;
    if(c.includes('ia receta') || c.includes('receta por voz') || c.includes('receta por foto') || c.includes('nueva receta') || c.includes('importar receta')){ say('Abro IA Recetas. Se crea borrador, no receta maestra automática.','ok'); location.href='/recipe-ai/ui'; return true; }
    if(c.includes('inventario')) return go('inventario');
    if(c.includes('stock')) return go('stock');
    if(c.includes('inicio') || c.includes('dashboard')) return go('inicio');
    if(c.includes('albaran') || c.includes('albaranes')){ if(c.includes('crear')||c.includes('nuevo')) return createReceipt(); if(c.includes('validar')){ if(page()!=='albaranes') return go('albaranes'); const ok=submitFirst(['form[action*="/validate_form"] button[type="submit"]']); say(ok?'Valido el albarán abierto.':'Abre un albarán pendiente antes de validar.', ok?'ok':'warn'); return true;} return go('albaranes'); }
    if(c.includes('pedido') || c.includes('pedidos') || ['verduras','pescados','carnes','huevos','lacteos','frescos','congelados','secos','limpieza'].some(x=>c.includes(x))){ if(c.includes('crear')||c.includes('nuevo')) return createOrder(); if(c.includes('revisar')||c.includes('proveedor')){ if(page()!=='pedidos') return go('pedidos'); const ok=clickFirst(['a[href*="preconfirm=1"]']); say(ok?'Abro revisión por proveedor.':'No hay pedido borrador listo para revisar.', ok?'ok':'warn'); return true;} if(showOrderBlock(c)) return true; return go('pedidos'); }
    if(c.includes('produccion') || c.includes('producciones')){ if(c.includes('crear')||c.includes('nueva')||c.includes('nuevo')) return createProduction(); return go('producciones'); }
    if(c.includes('merma') || c.includes('mermas') || c.includes('perdida') || c.includes('desperdicio')){ if(c.includes('control')||c.includes('dinero')) return go('mermas_control'); if(c.includes('foto')){ if(page()!=='mermas') return go('mermas'); if(window.showWastePanel) window.showWastePanel('photo'); say('Abro merma por foto.','ok'); return true;} return createWaste(raw); }
    if(c.includes('receta') || c.includes('recetas')) return go('recetas');
    say('No he reconocido el comando. Prueba: teléfono de proveedor, de qué proveedor es salmón, crear pedido, registrar merma, crear producción, receta por foto o qué hay que pedir.','warn'); return false;
  }
  function initTabs(){
    const root=$('#macVoiceAssistant'); if(!root) return;
    $$('[data-alfi-tab]', root).forEach(btn=>btn.addEventListener('click',()=>{
      const key=btn.dataset.alfiTab;
      $$('[data-alfi-tab]', root).forEach(b=>b.classList.toggle('is-active', b===btn));
      $$('[data-alfi-panel]', root).forEach(p=>{ const on=p.dataset.alfiPanel===key; p.hidden=!on; p.classList.toggle('is-active', on); });
    }));
  }
  function initDrag(){
    const root=$('#macVoiceAssistant'), fab=$('#macVoiceFab'); if(!root||!fab) return;
    const saved=localStorage.getItem('macVoicePos'); if(saved){ try{ const p=JSON.parse(saved); root.style.left=p.left; root.style.top=p.top; root.style.right='auto'; root.style.bottom='auto'; }catch(_){} }
    let sx=0, sy=0, ox=0, oy=0, moved=false;
    fab.addEventListener('pointerdown', e=>{ if(e.target.closest('button')!==fab) return; moved=false; sx=e.clientX; sy=e.clientY; const r=root.getBoundingClientRect(); ox=r.left; oy=r.top; fab.setPointerCapture(e.pointerId); root.classList.add('is-dragging'); });
    fab.addEventListener('pointermove', e=>{ if(!root.classList.contains('is-dragging')) return; const dx=e.clientX-sx, dy=e.clientY-sy; if(Math.abs(dx)+Math.abs(dy)>6) moved=true; const nx=Math.max(8, Math.min(window.innerWidth-72, ox+dx)); const ny=Math.max(8, Math.min(window.innerHeight-72, oy+dy)); root.style.left=nx+'px'; root.style.top=ny+'px'; root.style.right='auto'; root.style.bottom='auto'; });
    function end(e){ if(!root.classList.contains('is-dragging')) return; root.classList.remove('is-dragging'); try{ fab.releasePointerCapture(e.pointerId); }catch(_){} localStorage.setItem('macVoicePos', JSON.stringify({left:root.style.left, top:root.style.top})); setTimeout(()=>{ moved=false; },0); }
    fab.addEventListener('pointerup', end); fab.addEventListener('pointercancel', end);
    fab.addEventListener('click', e=>{ if(moved){ e.preventDefault(); e.stopPropagation(); } }, true);
  }
  function init(){
    const root=$('#macVoiceAssistant'); if(!root) return;
    const fab=$('#macVoiceFab'), panel=$('#macVoicePanel'), close=$('#macVoiceClose'), listen=$('#macVoiceListen'), stop=$('#macVoiceStop'), form=$('#macVoiceCommandForm'), input=$('#macVoiceCommand');
    initTabs(); initDrag();
    fab?.addEventListener('click', ()=>{ if(root.classList.contains('is-dragging')) return; const open=panel.hasAttribute('hidden'); if(open){ panel.removeAttribute('hidden'); fab.setAttribute('aria-expanded','true'); setTimeout(()=>input?.focus(),80); } else { panel.setAttribute('hidden',''); fab.setAttribute('aria-expanded','false'); } });
    close?.addEventListener('click', ()=>{ panel.setAttribute('hidden',''); fab.setAttribute('aria-expanded','false'); });
    $$('[data-voice-command]',root).forEach(b=>b.addEventListener('click',()=>command(b.dataset.voiceCommand||'')));
    form?.addEventListener('submit', e=>{ e.preventDefault(); const v=input.value; input.value=''; command(v); });
    input?.addEventListener('input', ()=>{
      clearTimeout(suggestTimer);
      suggestTimer=setTimeout(()=>apiSuggest(input.value||''), 420);
    });
    const SR=window.SpeechRecognition||window.webkitSpeechRecognition; let rec=null;
    if(SR){
      rec=new SR(); rec.lang='es-ES'; rec.interimResults=false; rec.continuous=false;
      rec.onstart=()=>{ say('Escuchando dictado del navegador…','ok'); if(listen)listen.hidden=true; if(stop)stop.hidden=false; };
      rec.onend=()=>{ if(!mediaRecorder){ if(listen)listen.hidden=false; if(stop)stop.hidden=true; } };
      rec.onerror=()=>say('No pude captar dictado del navegador. Usa grabación OpenAI o el micrófono del teclado.','warn');
      rec.onresult=ev=>{ const txt=ev.results?.[0]?.[0]?.transcript||''; if(input) input.value=txt; say('He entendido: '+txt,'ok'); command(txt); };
    }
    listen?.addEventListener('click', async()=>{
      clearAnswer();
      const recorded=await startAudioRecording(listen, stop);
      if(recorded) return;
      if(rec){ try{rec.start();}catch(_){say('El micrófono ya está activo o bloqueado.','warn');} }
      else say('Este navegador no permite grabación directa. En iPhone usa el micrófono del teclado dentro del campo.','warn');
    });
    stop?.addEventListener('click',()=>{
      if(stopAudioRecording()) return;
      if(rec){ try{rec.stop();}catch(_){} }
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
