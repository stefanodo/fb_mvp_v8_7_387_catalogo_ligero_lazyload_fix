(function(){
  function qs(sel, root){ return (root||document).querySelector(sel); }
  function qsa(sel, root){ return Array.from((root||document).querySelectorAll(sel)); }
  function escapeHtml(s){ return String(s==null?'':s).replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  function fmtLabNum(v, maxDec){
    const n=Number(v||0); if(!isFinite(n)) return '0';
    const dec = maxDec==null ? (Math.abs(n)>=100?0:(Math.abs(n)>=10?1:3)) : maxDec;
    return n.toLocaleString('es-ES',{minimumFractionDigits:0, maximumFractionDigits:dec});
  }
  function fmtLabQty(v,u){ return `${fmtLabNum(v)} ${u||''}`.trim(); }
  function fmtMoney(v){ return `${fmtLabNum(v,2)} €`; }
  function fmtInput(v, maxDec){
    const n=Number(v||0); if(!isFinite(n) || Math.abs(n)<1e-12) return '';
    const dec = maxDec==null ? 3 : maxDec;
    let out = n.toFixed(dec);
    out = out.replace(/\.?0+$/,'');
    return out;
  }
  async function postForm(url, data){
    const fd = new FormData(); Object.entries(data||{}).forEach(([k,v])=>fd.append(k,v));
    const r = await fetch(url, {method:'POST', body:fd, headers:{'Cache-Control':'no-store'}}); return await r.json();
  }
  async function getJson(url){ const r = await fetch(url, {headers:{'Cache-Control':'no-store'}}); return await r.json(); }
  let barEditorOptions = {items:[], productions:[]};
  async function loadBarEditorOptions(){ try{ barEditorOptions = await getJson('/api/lab/bar/editor-options'); buildIngredientDatalist(); }catch(e){ barEditorOptions={items:[],productions:[]}; } }
  function buildIngredientDatalist(){ const dl=qs('#barIngredientDatalist'); if(!dl) return; const opts=[]; (barEditorOptions.items||[]).forEach(x=>opts.push(`<option value="${escapeHtml(x.name)}"></option>`)); (barEditorOptions.productions||[]).forEach(x=>opts.push(`<option value="${escapeHtml(x.name)}"></option>`)); dl.innerHTML=opts.join(''); }
  function humanResult(data){
    if(!data) return '<div class="muted">Sin datos.</div>';
    let html = `<div class="lab-ok">${escapeHtml(data.message||'Resultado recibido')}</div>`;
    if(data.mode) html += `<div class="lab-chip">Modo: ${escapeHtml(data.mode)}</div>`;
    if(data.mapping) html += `<p><strong>Mapeo:</strong> ${escapeHtml(data.mapping.status)} · confianza ${escapeHtml(data.mapping.confidence||0)}%</p>`;
    if(data.alerts && data.alerts.length) html += '<ul>'+data.alerts.map(a=>`<li>${escapeHtml(a)}</li>`).join('')+'</ul>';
    if(data.quantity_mode){ html += `<div class="lab-chip">Consumo: ${escapeHtml(data.quantity_mode==='racion'?'ración/porción':'lote completo')}</div>`; }
    if(data.consumption_preview && data.consumption_preview.length){
      const pinfo=data.consumption_preview[0].portion_info||null;
      if(pinfo && pinfo.mode){ html += `<p class="lab-note">Escala aplicada: ${escapeHtml(pinfo.mode)} · factor ${escapeHtml(fmtLabNum(pinfo.scale_factor,4))}${pinfo.yield_portions?` · rendimiento receta: ${escapeHtml(fmtLabNum(pinfo.yield_portions,2))} raciones`:''}</p>`; }
      html += '<h4>Consumo teórico PREVIEW</h4><ul>'+data.consumption_preview.slice(0,8).map(e=>`<li>${escapeHtml(e.item_name)} · ${escapeHtml(e.qty_display||fmtLabQty(e.qty_theoretical,e.unit))}</li>`).join('')+'</ul>';
    }
    if(data.modifiers && data.modifiers.length){ html += '<h4>Modificadores</h4><ul>'+data.modifiers.map(m=>`<li>${escapeHtml(m.name)} → ${escapeHtml(m.action)} · ${escapeHtml(m.review_status)}</li>`).join('')+'</ul>'; }
    html += `<details class="lab-details"><summary>Diagnóstico técnico</summary><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre></details>`;
    return html;
  }

  function renderBarSummary(data){
    const sum=qs('#barLabSummary'), list=qs('#barCocktailList'), prods=qs('#barProductionList');
    if(!sum) return;
    if(!data || data.ok===false){ sum.innerHTML='<div class="lab-warn">Coctelería no disponible.</div>'; return; }
    const c=data.counts||{};
    sum.innerHTML = `<div class="lab-metrics"><span>Insumos: <b>${c.items||0}</b></span><span>Stock inicial: <b>${c.stock_movements||0}</b></span><span>Producciones: <b>${c.productions||0}</b></span><span>Cócteles: <b>${c.recipes||0}</b></span><span>Escandallos: <b>${c.recipe_lines||0}</b></span></div>` +
      `<div class="lab-chip">demo_data=true</div><div class="lab-chip">DATOS_DEMO_NO_PRODUCTIVOS=true</div><p>${escapeHtml(data.business||'')} · ${escapeHtml(data.bar||'')}</p>` +
      ((data.alerts||[]).length?'<ul>'+data.alerts.map(a=>`<li><b>${escapeHtml(a.alert_code)}</b>: ${escapeHtml(a.alert_text)}</li>`).join('')+'</ul>':'');
    const sel=qs('#barCocktailSelect');
    const dl=qs('#barCocktailDatalist');
    if(sel){ const current=sel.value; sel.innerHTML='<option value="">Selecciona cóctel...</option>'+(data.recipes||[]).map(r=>`<option value="${r.id}">${escapeHtml(r.name)}</option>`).join(''); if(current) sel.value=current; }
    if(dl){ dl.innerHTML=(data.recipes||[]).map(r=>`<option value="${escapeHtml(r.name)}" data-id="${r.id}"></option>`).join(''); }
    // La lista fija de cócteles queda oculta para no ocupar pantalla: solo se muestran sugerencias al escribir.
    if(list) list.innerHTML = '';
    if(prods) prods.innerHTML = (data.productions||[]).map(r=>`<div class="lab-row compact"><b>${escapeHtml(r.name)}</b><span>${escapeHtml(fmtLabQty(r.yield_qty,r.yield_unit||''))} · ${escapeHtml(fmtLabNum(r.cost_per_unit_2026,5))} €/u · vendible: ${r.es_vendible? 'sí':'no'}</span></div>`).join('');
  }
  async function refreshBar(){ try{ renderBarSummary(await getJson('/api/lab/bar/summary')); }catch(e){} }

  function renderBarOrders(data){
    const el=qs('#barOrderSummary'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">Pedidos LAB no disponibles.</div>'; return; }
    const area=data.area_order_lines||[]; const lines=data.consolidated_order_lines||[]; const receipts=data.receipt_split_lines||[];
    el.innerHTML = `<div class="lab-chip">LAB · no productivo</div>`+
      `<h4>Pedidos independientes por área</h4>`+
      (area.length?'<ul>'+area.map(x=>`<li><b>${escapeHtml(x.area)}</b> · ${escapeHtml(x.item_name)}: stock ${escapeHtml(Number(x.current_stock||0).toFixed(0))}/${escapeHtml(Number(x.max_stock||0).toFixed(0))} → pedir ${escapeHtml(Number(x.suggested_qty||0).toFixed(0))} ${escapeHtml(x.unit||'')} · ${escapeHtml(x.purchase_link_mode||'')}</li>`).join('')+'</ul>':'<p>Sin líneas.</p>')+
      `<h4>Pedido consolidado proveedor</h4>`+
      (lines.length?'<ul>'+lines.map(x=>`<li>${escapeHtml(x.item_name)} · <b>${escapeHtml(Number(x.total_qty||0).toFixed(0))} ${escapeHtml(x.unit||'')}</b> · ${escapeHtml(x.consolidation_reason||'')}</li>`).join('')+'</ul>':'<p>Sin consolidación.</p>')+
      `<h4>Recepción y reparto</h4>`+
      (receipts.length?'<ul>'+receipts.map(x=>`<li>${escapeHtml(x.item_name)} · pedido ${escapeHtml(Number(x.ordered_qty||0).toFixed(0))} / recibido ${escapeHtml(Number(x.received_qty||0).toFixed(0))} ${escapeHtml(x.unit||'')} · <b>${escapeHtml(x.auto_split_status||'')}</b><br><small>${escapeHtml(x.notes||'')}</small></li>`).join('')+'</ul>':'<p>Sin recepción.</p>')+
      `<details class="lab-details"><summary>Diagnóstico técnico</summary><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre></details>`;
  }
  async function refreshBarOrders(){ try{ renderBarOrders(await getJson('/api/lab/bar/orders/summary')); }catch(e){} }

  function cocktailHeaderForm(r){
    const photoPreview = (!r.photo_path || r.photo_path==='pendiente_subir')
      ? '<div class="cocktail-photo-editor-placeholder">Foto pendiente<br><small>Sube o pega ruta</small></div>'
      : `<img class="cocktail-photo-editor" src="${escapeHtml(r.photo_path)}" alt="${escapeHtml(r.name||'Cóctel')}">`;
    const codeText = r.code ? escapeHtml(r.code) : 'Se generará al guardar';
    const codeLabel = r.code ? 'Código' : 'Código pendiente';
    return `<form id="barCocktailHeaderForm" class="cocktail-edit-form cocktail-edit-compact" autocomplete="off">
      <input type="hidden" name="id" value="${escapeHtml(r.id||0)}">
      <input type="hidden" name="code" value="${escapeHtml(r.code||'')}">
      <div class="cocktail-edit-top">
        <div class="cocktail-photo-box">
          ${photoPreview}
          <div class="cocktail-photo-actions">
            <button class="btn ghost cocktail-photo-upload" type="button">Subir foto</button>
            <button class="btn danger cocktail-photo-remove" type="button">Quitar foto</button>
          </div>
          <label class="photo-path-label">Foto/ruta<input name="photo_path" value="${escapeHtml(r.photo_path||'pendiente_subir')}" placeholder="pendiente_subir"></label>
        </div>
        <div class="cocktail-main-fields">
          <div class="cocktail-code-lock"><span>${codeLabel}</span><b>${codeText}</b><small>${r.code ? 'No editable para evitar duplicados.' : 'No se crea registro ni código hasta guardar ficha con nombre.'}</small></div>
          <div class="cocktail-general-grid">
            <label class="field-name">Nombre<input name="name" value="${escapeHtml(r.name||'')}" required></label>
            <label>Categoría<input name="category" value="${escapeHtml(r.category||'clásico')}"></label>
            <label>Tipo<input name="cocktail_type" value="${escapeHtml(r.cocktail_type||'')}"></label>
            <label>Copa/vaso<input name="glass_type" value="${escapeHtml(r.glass_type||'')}"></label>
            <label>Servicio ml<input name="serving_size_ml" type="number" step="0.1" value="${escapeHtml(fmtInput(r.serving_size_ml,1)||0)}"></label>
            <label>Rend.<input name="yield_qty" type="number" step="0.1" value="${escapeHtml(fmtInput(r.yield_qty,1)||1)}"></label>
            <label>Unidad<input name="yield_unit" value="${escapeHtml(r.yield_unit||'copa')}"></label>
            <label>PVP<input name="sale_price" type="number" step="0.01" value="${escapeHtml(fmtInput(r.sale_price,2)||0)}"></label>
            <label>Margen %<input name="target_margin_percent" type="number" step="0.1" value="${escapeHtml(fmtInput(r.target_margin_percent,1)||80)}"></label>
            <label>Cont. %<input name="contingency_percent" type="number" step="0.1" value="${escapeHtml(fmtInput(r.contingency_percent,1)||5)}"></label>
            <label>Tiempo min<input name="preparation_time_minutes" type="number" step="0.1" value="${escapeHtml(fmtInput(r.preparation_time_minutes,1)||0)}"></label>
            <label>Dificultad<input name="difficulty" value="${escapeHtml(r.difficulty||'')}"></label>
            <label>Temporada<input name="seasonality" value="${escapeHtml(r.seasonality||'')}"></label>
            <label>Estado<input name="status" value="${escapeHtml(r.status||'activo')}"></label>
          </div>
          <label class="notes-label">Notas<textarea name="notes" rows="2">${escapeHtml(r.notes||'')}</textarea></label>
          <div class="cocktail-form-actions"><button class="btn gold" type="submit">Guardar ficha</button></div>
        </div>
      </div>
    </form>`;
  }
  function barOptions(){ return barEditorOptions || {items:[], productions:[]}; }
  function normName(v){ return (v||'').toString().trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,''); }
  function findBarSource(name, origin){
    const o=barOptions(); const n=normName(name);
    if(origin==='produccion_bar' || origin==='producción_bar'){
      const p=(o.productions||[]).find(x=>normName(x.name)===n || normName(x.code)===n);
      if(p) return {unit:p.yield_unit||'ml', cost:Number(p.cost_per_unit_2026||0), waste:Number(p.standard_waste_percent||0), origin:'produccion_bar'};
    }
    const it=(o.items||[]).find(x=>normName(x.name)===n);
    if(it) return {unit:it.base_unit||'ml', cost:Number(it.cost_per_base_unit_2026||0), waste:Number(it.standard_waste_percent||0), origin:'stock_bar'};
    return {unit:'ml', cost:0, waste:0, origin:origin||'stock_bar'};
  }
  function unitSelectHtml(currentUnit){
    const val=(currentUnit||'ml').toLowerCase();
    const opts=['ml','gr','ud'].map(u=>`<option value="${u}" ${val===u?'selected':''}>${u}</option>`).join('');
    return `<select name="unit" class="unit-compact" aria-label="Unidad">${opts}</select>`;
  }
  function lineForm(recipeId, x){
    x=x||{}; const isNew=!x.id;
    const originVal = (x.origin==='produccion_bar'||x.origin==='producción_bar') ? 'produccion_bar' : 'stock_bar';
    const originLabel = originVal==='produccion_bar' ? 'Prod. Bar' : 'Stock';
    const ingredientName = x.ingredient_name||'';
    const ingredientCell = isNew
      ? `<input class="ingredient-cell ingredient-new" name="ingredient_name" list="barIngredientDatalist" placeholder="Buscar ingrediente/preparado" value="${escapeHtml(ingredientName)}" aria-label="Ingrediente">`
      : `<div class="ingredient-locked" title="Ingrediente vinculado a Stock/Producción Bar. Para cambiarlo, quita la línea y añade el correcto."><b>${escapeHtml(ingredientName)}</b></div><input type="hidden" name="ingredient_name" value="${escapeHtml(ingredientName)}">`;
    const originCell = isNew
      ? `<select class="origin-compact" name="origin" aria-label="Origen"><option value="stock_bar" ${originVal==='stock_bar'?'selected':''}>Stock</option><option value="produccion_bar" ${originVal==='produccion_bar'?'selected':''}>Prod.</option></select>`
      : `<span class="origin-chip">${escapeHtml(originLabel)}</span><input type="hidden" name="origin" value="${escapeHtml(originVal)}">`;
    return `<form class="cocktail-line-form cocktail-line ${isNew?'new-line':''}" data-recipe-id="${escapeHtml(recipeId)}">
      <input type="hidden" name="line_id" value="${escapeHtml(x.id||0)}">
      ${ingredientCell}
      ${originCell}
      <input name="qty_net" type="number" step="0.001" placeholder="Cant." value="${escapeHtml(fmtInput(x.qty_net,2))}" aria-label="Cantidad">
      ${unitSelectHtml(x.unit||'ml')}
      <input name="waste_percent" type="number" step="0.1" placeholder="Merma %" value="${escapeHtml(fmtInput(x.waste_percent,1)||0)}" aria-label="Merma %">
      <input type="hidden" name="cost_unit_2026" value="${escapeHtml(fmtInput(x.cost_unit_2026,6)||0)}">
      <span class="cost-auto-pill" title="Coste automático desde Stock Bar o Producción Bar. No editable aquí.">${escapeHtml(fmtInput(x.cost_unit_2026,5)||0)} €/u</span>
      <span class="line-calc"><b>${escapeHtml(fmtLabQty(x.qty_gross||0,x.unit||''))}</b> · ${escapeHtml(fmtMoney(x.cost_total_gross_2026||0))}</span>
      <div class="line-actions"><button class="btn ghost" type="submit">Guardar</button>
      ${isNew?'<span class="line-empty-action"></span>':`<button class="btn danger cocktail-line-delete" type="button" data-recipe-id="${escapeHtml(recipeId)}" data-line-id="${escapeHtml(x.id)}">Quitar</button>`}</div>
    </form>`;
  }
  async function showCocktailDetail(id){
    const el=qs('#barCocktailDetail'); if(!el) return;
    el.innerHTML='Cargando detalle...';
    await loadBarEditorOptions();
    const d=await getJson('/api/lab/bar/cocktail/'+encodeURIComponent(id));
    if(!d || d.ok===false){ el.innerHTML='<div class="lab-warn">No se pudo cargar.</div>'; return; }
    const r=d.recipe||{};
    const stepsText=(d.steps||[]).map(s=>`${s.step_number||''}. ${s.instruction||''}`).join('\n');
    el.innerHTML = `<datalist id="barIngredientDatalist"></datalist><div class="cocktail-detail-head no-photo"><div><h3>${escapeHtml(r.name)}</h3><div class="lab-metrics"><span>Coste bruto: <b>${escapeHtml(fmtMoney(r.cost_2026_gross_with_waste))}</b></span><span>PVP: <b>${escapeHtml(fmtMoney(r.sale_price))}</b></span><span>Margen: <b>${escapeHtml(fmtLabNum(r.margin_percent_2026,1))}%</b></span><span>Alcohol calculado: <b>${escapeHtml(fmtLabNum(r.alcohol_percentage_calculated||r.alcohol_percentage_estimated,1))}%</b></span><span>Servicio: <b>${escapeHtml(fmtLabQty(r.serving_size_ml,'ml'))}</b></span></div></div></div>` +
      '<details open class="cocktail-section"><summary><b>Datos generales y foto</b></summary>'+cocktailHeaderForm(r)+'</details>'+
      '<h4>Escandallo editable</h4>'+
      '<div class="cocktail-line-head"><span>Ingrediente</span><span>Orig.</span><span>Cant.</span><span>Unidad</span><span>Merma %</span><span>Coste €/u</span><span>Bruto/coste</span><span>Acciones</span></div>'+
      '<div class="cocktail-lines">'+ (d.lines||[]).map(x=>lineForm(r.id,x)).join('') + '</div>'+
      '<h4>Añadir ingrediente/preparado</h4>'+lineForm(r.id,{})+
      '<h4>Procedimiento editable</h4><form id="barCocktailStepsForm" data-recipe-id="'+escapeHtml(r.id)+'"><textarea name="steps_text" rows="8">'+escapeHtml(stepsText)+'</textarea><button class="btn gold" type="submit">Guardar procedimiento</button></form>'+
      `<details class="lab-details"><summary>Regla alcohol / diagnóstico</summary><pre>${escapeHtml(JSON.stringify(d.calculation_rules||[],null,2))}</pre></details>`;
    buildIngredientDatalist();
  }

  async function showNewCocktailForm(){
    const el=qs('#barCocktailDetail'); if(!el) return;
    el.innerHTML='';
    await loadBarEditorOptions();
    const r={id:0,name:'',code:'',category:'clásico',cocktail_type:'',glass_type:'',yield_qty:1,yield_unit:'copa',serving_size_ml:150,sale_price:0,target_margin_percent:80,contingency_percent:5,preparation_time_minutes:0,difficulty:'',seasonality:'',photo_path:'pendiente_subir',notes:'',status:'activo'};
    el.innerHTML='<datalist id="barIngredientDatalist"></datalist><h3>Crear ficha técnica de cóctel</h3><p class="lab-note">Ficha nueva limpia. Primero guarda los datos generales; después añade ingredientes, mermas, cantidades y procedimiento.</p>'+cocktailHeaderForm(r);
    const form=qs('#barCocktailHeaderForm', el); if(form){ form.reset(); form.querySelector('input[name="id"]').value='0'; form.querySelector('input[name="code"]').value=''; }
    buildIngredientDatalist();
  }


  function renderBarBeverages(data){
    const el=qs('#barBeverageSummary'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">Bebidas por servicio no disponibles.</div>'; return; }
    const c=data.counts||{};
    const services=data.services||[];
    el.innerHTML = `<div class="lab-metrics"><span>Servicios: <b>${c.services||0}</b></span><span>Líneas: <b>${c.service_lines||0}</b></span><span>Medidas: <b>${c.pour_sizes||0}</b></span><span>Botellas abiertas: <b>${c.open_bottles||0}</b></span></div>`+
      `<div class="lab-chip">ml/gr propios de Barra</div><div class="lab-chip">PREVIEW TPV</div>`+
      '<h4>Servicios vendibles</h4>'+
      (services.length?'<ul>'+services.map(s=>`<li><button type="button" class="btn ghost" data-beverage-code="${escapeHtml(s.code)}">Simular</button> <b>${escapeHtml(s.name)}</b> · ${escapeHtml(s.service_type)} · ${escapeHtml(s.billing_mode)} · coste ${escapeHtml(Number(s.cost_total_2026||0).toFixed(2))} € · PVP ${escapeHtml(Number(s.bundle_sale_price||0).toFixed(2))} € · margen ${escapeHtml(Number(s.margin_percent_2026||0).toFixed(1))}%</li>`).join('')+'</ul>':'<p>Sin servicios.</p>')+
      '<h4>Botellas abiertas demo</h4>'+
      ((data.open_bottles||[]).length?'<ul>'+data.open_bottles.map(b=>`<li>${escapeHtml(b.item_name)} · restante teórico ${escapeHtml(Number(b.theoretical_ml_remaining||0).toFixed(0))}/${escapeHtml(Number(b.bottle_ml||0).toFixed(0))} ml · oxidación ${escapeHtml(Number(b.oxidation_waste_percent||0).toFixed(1))}%</li>`).join('')+'</ul>':'<p>Sin botellas abiertas.</p>')+
      `<details class="lab-details"><summary>Reglas / diagnóstico</summary><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre></details>`;
  }
  async function refreshBarBeverages(){ try{ renderBarBeverages(await getJson('/api/lab/bar/beverages/summary')); }catch(e){} }
  function renderBeverageSale(data){
    const el=qs('#barBeverageResult'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">No se pudo simular.</div>'; return; }
    el.innerHTML = `<div class="lab-ok">${escapeHtml(data.message||'Simulado')}</div><div class="lab-chip">${escapeHtml(data.billing_mode_used||'')}</div>`+
      '<h4>Ticket PREVIEW</h4><ul>'+ (data.ticket_lines_preview||[]).map(x=>`<li>${escapeHtml(x.name)} · ${escapeHtml(Number(x.price||0).toFixed(2))} €</li>`).join('') + `</ul><p><b>Total:</b> ${escapeHtml(Number(data.ticket_total_preview||0).toFixed(2))} € · margen ${escapeHtml(Number(data.margin_percent_preview||0).toFixed(1))}%</p>`+
      '<h4>Consumo Stock Bar PREVIEW</h4><ul>'+ (data.consumption_preview||[]).map(x=>`<li>${escapeHtml(x.item_name)} · ${escapeHtml(Number(x.qty_theoretical||0).toFixed(3))} ${escapeHtml(x.unit||'')} · ${escapeHtml(Number(x.cost_total_preview||0).toFixed(3))} €</li>`).join('') + '</ul>'+
      `<details class="lab-details"><summary>Diagnóstico técnico</summary><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre></details>`;
  }



  function renderBarMixers(data){
    const el=qs('#barMixerSummary'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">Mixers multi-servicio no disponibles.</div>'; return; }
    const items=data.items||[], open=data.open_containers||[];
    el.innerHTML = `<div class="lab-chip">ml propios de Barra</div><div class="lab-chip">envase abierto controlado</div>`+
      '<h4>Configuración de refrescos/mixers</h4>'+
      (items.length?'<ul>'+items.map(x=>`<li><b>${escapeHtml(x.name)}</b> · ${escapeHtml(x.container_type||'')} · ${escapeHtml(Number(x.container_volume_ml||0).toFixed(0))} ml · multi: ${x.is_multi_serve?'sí':'no'} · gas ${escapeHtml(Number(x.gas_loss_percent||0).toFixed(1))}%</li>`).join('')+'</ul>':'<p>Sin mixers.</p>')+
      '<h4>Envases abiertos demo</h4>'+
      (open.length?'<ul>'+open.map(x=>`<li>${escapeHtml(x.item_name)} · ${escapeHtml(x.container_code)} · usados ${escapeHtml(Number(x.used_ml||0).toFixed(0))}/${escapeHtml(Number(x.initial_ml||0).toFixed(0))} ml · restante ${escapeHtml(Number(x.remaining_ml||0).toFixed(0))} ml</li>`).join('')+'</ul>':'<p>Sin envases abiertos.</p>')+
      `<details class="lab-details"><summary>Reglas / diagnóstico</summary><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre></details>`;
  }
  async function refreshBarMixers(){ try{ renderBarMixers(await getJson('/api/lab/bar/mixers/summary')); }catch(e){} }


  function renderSharedReceipts(data){
    const box=qs('#barSharedReceiptSummary'); if(!box) return;
    if(!data||data.ok===false){ box.innerHTML=escapeHtml((data&&data.message)||'Sin datos.'); return; }
    const lines=data.lines||[];
    box.innerHTML='<p><b>'+escapeHtml(data.message||'Resumen albarán único compartido')+'</b></p>'+
      (data.document_code?'<p>Documento único: <b>'+escapeHtml(data.document_code)+'</b> · estado '+escapeHtml(data.status||'')+'</p>':'')+
      (lines.length?'<ul>'+lines.map(l=>`<li><b>${escapeHtml(l.item_name)}</b> · ${escapeHtml(l.received_qty)} ${escapeHtml(l.unit)} · ${escapeHtml(l.split_source)} · ${escapeHtml(l.split_status)}<pre>${escapeHtml(JSON.stringify(l.split||l.split_json||{},null,2))}</pre></li>`).join('')+'</ul>':'<p>Sin líneas.</p>')+
      (data.rules?'<p class="muted">'+data.rules.map(escapeHtml).join(' · ')+'</p>':'');
  }
  async function refreshSharedReceipts(){ try{ renderSharedReceipts(await getJson('/api/lab/bar/shared-receipts/summary')); }catch(e){} }

  function renderBarReceipts(data){
    const el=qs('#barReceiptSummary'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">Albaranes bebidas no disponibles.</div>'; return; }
    const lines=data.lines||[], mov=data.inventory_movements||[], rec=data.cost_recalculations||[];
    el.innerHTML = `<div class="lab-chip">OCR bebidas LAB</div><div class="lab-chip">Stock Bar / Inventario Bar</div>`+
      (data.latest?`<p><b>${escapeHtml(data.latest.document_code||'')}</b> · ${escapeHtml(data.latest.supplier_name||'')} · ${escapeHtml(Number(data.latest.total_amount||0).toFixed(2))} €</p>`:'<p>Sin albarán simulado.</p>')+
      '<h4>Líneas clasificadas</h4>'+
      (lines.length?'<ul>'+lines.map(x=>`<li><b>${escapeHtml(x.item_name_raw)}</b> · ${escapeHtml(Number(x.qty||0).toFixed(0))} ${escapeHtml(x.unit||'')} · ${escapeHtml(x.classification||'')} → <b>${escapeHtml(x.destination_stock||'')}</b> · ${escapeHtml(x.validation_status||'')}</li>`).join('')+'</ul>':'<p>Sin líneas.</p>')+
      '<h4>Movimientos Inventario Bar</h4>'+
      (mov.length?'<ul>'+mov.map(x=>`<li>${escapeHtml(x.item_name)} · ${escapeHtml(Number(x.qty||0).toFixed(0))} ${escapeHtml(x.unit||'')} · ${escapeHtml(x.movement_type||'')}</li>`).join('')+'</ul>':'<p>Sin movimientos.</p>')+
      '<h4>Recálculos afectados</h4>'+
      (rec.length?'<ul>'+rec.slice(0,12).map(x=>`<li>${escapeHtml(x.affected_type)} · ${escapeHtml(x.affected_name)} · línea ${escapeHtml(x.item_name)}: ${escapeHtml(Number(x.old_cost||0).toFixed(3))} € → ${escapeHtml(Number(x.new_cost||0).toFixed(3))} €</li>`).join('')+'</ul>':'<p>Sin recálculos.</p>')+
      `<details class="lab-details"><summary>Diagnóstico técnico</summary><pre>${escapeHtml(JSON.stringify(data,null,2))}</pre></details>`;
  }
  async function refreshBarReceipts(){ try{ renderBarReceipts(await getJson('/api/lab/bar/receipts/summary')); }catch(e){} }

  function renderSummary(id, data){
    const el=qs(id); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">No disponible.</div>'; return; }
    if(id==='#tpvLabSummary'){
      el.innerHTML = `<div class="lab-metrics"><span>Mapeos pendientes: <b>${data.pending_mappings||0}</b></span><span>Modificadores pendientes: <b>${data.pending_modifiers||0}</b></span><span>Eventos PREVIEW: <b>${data.preview_events||0}</b></span></div>` +
        (data.imports||[]).map(x=>`<div class="lab-row"><b>#${x.id}</b> ${escapeHtml(x.product||'')} <span>${escapeHtml(x.status||'')}</span></div>`).join('');
    } else if(id==='#continuitySummary'){
      el.innerHTML = `<div class="lab-metrics"><span>Pendientes: <b>${data.pending_events||0}</b></span><span>Errores: <b>${data.error_events||0}</b></span><span>Conflictos: <b>${data.pending_conflicts||0}</b></span></div>` +
        (data.events||[]).map(x=>`<div class="lab-row"><b>${escapeHtml(x.module)}</b> ${escapeHtml(x.event_type)} <span>${escapeHtml(x.sync_status)}</span></div>`).join('') +
        (data.conflicts&&data.conflicts.length?'<h4>Conflictos</h4>'+data.conflicts.map(x=>`<div class="lab-row warn"><b>#${x.offline_event_id}</b> ${escapeHtml(x.conflict_type)} <span>${escapeHtml(x.resolution_status)}</span></div>`).join(''):'');
    } else if(id==='#accountingSummary'){
      el.innerHTML = `<div class="lab-metrics"><span>Docs: <b>${(data.documents||[]).length}</b></span><span>Conciliaciones: <b>${(data.reconciliations||[]).length}</b></span><span>Pagos propuestos: <b>${(data.payment_proposals||[]).length}</b></span></div>` +
        (data.documents||[]).map(x=>`<div class="lab-row"><b>${escapeHtml(x.document_type)}</b> ${escapeHtml(x.document_number)} · ${escapeHtml(x.supplier_name||'Sin proveedor')} <span>${escapeHtml(Number(x.amount_total||0).toFixed(2))} €</span></div>`).join('') +
        (data.payment_proposals||[]).map(x=>`<div class="lab-row warn"><b>Pago no ejecutable</b> ${escapeHtml(x.supplier_name||'')} <span>${escapeHtml(x.due_date||'')}</span></div>`).join('');
    }
  }


  function stockStatusLabel(s){ return s==='bajo_min'?'Bajo mínimo':(s==='sobre_max'?'Sobre máximo':'OK'); }
  function renderBarStock(data){
    const el=qs('#barStockSummary'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">Stock Bar no disponible.</div>'; return; }
    const rows=data.items||[];
    const groups=(data.groups&&data.groups.length?data.groups:[{name:'Todos',items:rows.length}]);
    const groupNames=groups.map(g=>g.name);
    const renderRows=(list)=>'<div class="bar-stock-table"><div class="bar-stock-head"><span>Artículo</span><span>Grupo</span><span>Stock</span><span>Min/Max</span><span>Coste</span><span>Estado</span></div>'+list.map(x=>`<div class="bar-stock-row" data-stock-group="${escapeHtml(x.stock_group||'Otros insumos Barra')}"><b>${escapeHtml(x.name)}</b><span>${escapeHtml(x.stock_group||x.family||'')}</span><span>${escapeHtml(fmtLabQty(x.stock_qty,x.base_unit||''))}</span><span>${escapeHtml(fmtLabQty(x.min_stock,x.base_unit||''))} / ${escapeHtml(fmtLabQty(x.max_stock,x.base_unit||''))}</span><span>${escapeHtml(fmtMoney(x.stock_value_2026||0))}</span><span class="bar-status ${escapeHtml(x.stock_status||'ok')}">${escapeHtml(stockStatusLabel(x.stock_status))}</span></div>`).join('')+'</div>';
    const sections=groupNames.map(g=>{
      const list=rows.filter(x=>(x.stock_group||'Otros insumos Barra')===g);
      if(!list.length) return '';
      const meta=groups.find(x=>x.name===g)||{};
      return `<details class="bar-stock-group" open><summary><b>${escapeHtml(g)}</b><span>${escapeHtml(meta.items||list.length)} artículos · ${escapeHtml(fmtMoney(meta.value_2026||0))}</span></summary>${renderRows(list)}</details>`;
    }).join('');
    el.innerHTML = `<div class="lab-metrics"><span>Artículos: <b>${escapeHtml((data.totals||{}).items||0)}</b></span><span>Valor demo: <b>${escapeHtml(fmtMoney((data.totals||{}).value_2026||0))}</b></span><span>Bajo mínimo: <b>${escapeHtml((data.totals||{}).below_min||0)}</b></span></div>`+
      `<div class="bar-stock-filter"><button type="button" class="active" data-bar-stock-filter="">Todos</button>${groupNames.map(g=>`<button type="button" data-bar-stock-filter="${escapeHtml(g)}">${escapeHtml(g)}</button>`).join('')}</div>`+
      `<div class="bar-stock-groups">${sections}</div>`+
      `<details class="lab-details"><summary>Reglas</summary><pre>${escapeHtml(JSON.stringify(data.rules||[],null,2))}</pre></details>`;
    el.querySelectorAll('[data-bar-stock-filter]').forEach(btn=>btn.addEventListener('click',()=>{
      const group=btn.getAttribute('data-bar-stock-filter')||'';
      el.querySelectorAll('[data-bar-stock-filter]').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      el.querySelectorAll('.bar-stock-group').forEach(sec=>{
        const name=(sec.querySelector('summary b')||{}).textContent||'';
        sec.style.display=(!group || name===group)?'block':'none';
      });
    }));
  }
  async function refreshBarStock(){ try{ renderBarStock(await getJson('/api/lab/bar/stock/summary')); }catch(e){} }

  function renderBarInventory(data){
    const el=qs('#barInventorySummary'); if(!el) return;
    if(!data || data.ok===false){ el.innerHTML='<div class="lab-warn">Inventario Bar no disponible.</div>'; return; }
    const rows=data.items||[];
    el.innerHTML = `<div class="lab-chip">LAB preparado</div><div class="lab-chip">sin cierre de inventario real</div>`+`<div class="lab-metrics"><span>Líneas teóricas: <b>${escapeHtml(rows.length)}</b></span><span>Valor demo: <b>${escapeHtml(fmtMoney((data.totals||{}).value_2026||0))}</b></span></div>`+
      '<div class="bar-stock-table inventory"><div class="bar-stock-head"><span>Artículo</span><span>Ubicación</span><span>Teórico</span><span>Conteo</span><span>Diferencia</span><span>Estado</span></div>'+rows.map(x=>`<div class="bar-stock-row"><b>${escapeHtml(x.name)}</b><span>${escapeHtml(x.location||'')}</span><span>${escapeHtml(fmtLabQty(x.theoretical_qty,x.unit||''))}</span><span class="muted">pendiente</span><span class="muted">—</span><span>${escapeHtml(x.status||'')}</span></div>`).join('')+'</div>'+
      `<details class="lab-details"><summary>Reglas inventario</summary><pre>${escapeHtml(JSON.stringify(data.rules||[],null,2))}</pre></details>`;
  }
  async function refreshBarInventory(){ try{ renderBarInventory(await getJson('/api/lab/bar/inventory/summary')); }catch(e){} }

  async function refreshLab(){
    try{ renderSummary('#tpvLabSummary', await getJson('/api/lab/tpv/summary')); }catch(e){}
    try{ renderSummary('#continuitySummary', await getJson('/api/lab/continuity/summary')); }catch(e){}
    try{ renderSummary('#accountingSummary', await getJson('/api/lab/accounting/summary')); }catch(e){}
    try{ await loadBarEditorOptions(); }catch(e){}
    try{ await refreshBar(); }catch(e){}
    try{ await refreshBarOrders(); }catch(e){}
    try{ await refreshBarBeverages(); }catch(e){}
    try{ await refreshBarMixers(); }catch(e){}
    try{ await refreshBarReceipts(); }catch(e){}
    try{ await refreshSharedReceipts(); }catch(e){}
    try{ await refreshBarStock(); }catch(e){}
    try{ await refreshBarInventory(); }catch(e){}
  }
  document.addEventListener('DOMContentLoaded', ()=>{
    qsa('[data-lab-tab]').forEach(btn=>btn.addEventListener('click',()=>{
      qsa('[data-lab-tab]').forEach(b=>b.classList.remove('active')); btn.classList.add('active');
      qsa('[data-lab-panel]').forEach(p=>p.classList.toggle('active', p.dataset.labPanel===btn.dataset.labTab));
    }));

    qsa('[data-bar-view]').forEach(btn=>btn.addEventListener('click',()=>{
      const view=btn.dataset.barView;
      qsa('[data-bar-view]').forEach(b=>b.classList.toggle('active', b===btn));
      qsa('[data-bar-view-section]').forEach(sec=>sec.classList.toggle('active', sec.dataset.barViewSection===view));
      if(view==='stock') refreshBarStock();
      if(view==='inventario') refreshBarInventory();
      if(view==='servicios'){ refreshBarBeverages(); refreshBarMixers(); }
      if(view==='albaranes'){ refreshBarReceipts(); refreshSharedReceipts(); }
      if(view==='pedidos') refreshBarOrders();
    }));
    const form=qs('#tpvLabForm'); if(form) form.addEventListener('submit', async ev=>{ev.preventDefault(); const data=Object.fromEntries(new FormData(form).entries()); qs('#tpvLabResult').innerHTML='Procesando venta TPV LAB...'; const res=await postForm('/api/lab/tpv/simulate', data); qs('#tpvLabResult').innerHTML=humanResult(res); refreshLab();});
    const btn=qs('#labCheckRecipeBtn'); if(btn) btn.addEventListener('click', async()=>{ const id=qs('#labRecipeCheck').value; if(!id){ qs('#labRecipeCheckResult').innerHTML='Selecciona una receta.'; return;} const d=await getJson('/api/lab/tpv/components/'+encodeURIComponent(id)); qs('#labRecipeCheckResult').innerHTML=humanResult(d); });
    qsa('[data-offline-case]').forEach(b=>b.addEventListener('click', async()=>{ const res=await postForm('/api/lab/continuity/simulate', {case:b.dataset.offlineCase}); renderSummary('#continuitySummary', await getJson('/api/lab/continuity/summary')); alert(res.message||'Evento creado'); }));
    const sync=qs('#labSyncBtn'); if(sync) sync.addEventListener('click', async()=>{ const res=await postForm('/api/lab/continuity/sync', {}); renderSummary('#continuitySummary', await getJson('/api/lab/continuity/summary')); alert(res.message||'Sync ejecutada'); });
    const acc=qs('#labAccountingSimBtn'); if(acc) acc.addEventListener('click', async()=>{ const res=await postForm('/api/lab/accounting/simulate', {}); renderSummary('#accountingSummary', await getJson('/api/lab/accounting/summary')); alert(res.message||'Conciliación simulada'); });
    const barLoad=qs('#labBarLoadBtn'); if(barLoad) barLoad.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/load-demo', {}); alert(res.message||'Demo Coctelería actualizada'); refreshBar(); });
    const barRefresh=qs('#labBarRefreshBtn'); if(barRefresh) barRefresh.addEventListener('click', ()=>{refreshBar(); refreshBarBeverages(); refreshBarMixers(); refreshBarReceipts(); refreshSharedReceipts(); refreshBarStock(); refreshBarInventory();});
    const barStockRefresh=qs('#labBarStockRefreshBtn'); if(barStockRefresh) barStockRefresh.addEventListener('click', refreshBarStock);
    const barInventoryRefresh=qs('#labBarInventoryRefreshBtn'); if(barInventoryRefresh) barInventoryRefresh.addEventListener('click', refreshBarInventory);
    const cocktailOpen=qs('#barCocktailOpenBtn'); if(cocktailOpen) cocktailOpen.addEventListener('click', ()=>{
      const sel=qs('#barCocktailSelect');
      const id = sel?.value || qs('#barCocktailSearch')?.dataset.selectedCocktailId || '';
      if(id) showCocktailDetail(id);
    });
    const cocktailSelect=qs('#barCocktailSelect'); if(cocktailSelect) cocktailSelect.addEventListener('change', ()=>{
      const search=qs('#barCocktailSearch');
      if(search){ search.dataset.selectedCocktailId = cocktailSelect.value || ''; }
      // No abrir ficha automáticamente: el usuario debe pulsar Ver ficha.
    });
    const cocktailNew=qs('#barCocktailNewBtn'); if(cocktailNew) cocktailNew.addEventListener('click', ()=>{
      const search=qs('#barCocktailSearch'); if(search){ search.value=''; search.dataset.selectedCocktailId=''; }
      const sel=qs('#barCocktailSelect'); if(sel) sel.value='';
      const box=qs('#barCocktailSuggestions'); if(box) box.innerHTML='';
      showNewCocktailForm();
    });
    const cocktailSearch=qs('#barCocktailSearch'); if(cocktailSearch) cocktailSearch.addEventListener('input', async()=>{
      const q=cocktailSearch.value.trim();
      const suggestionBox=qs('#barCocktailSuggestions');
      if(!q){ if(suggestionBox) suggestionBox.innerHTML=''; return; }
      const res=await getJson('/api/lab/bar/cocktails/search?q='+encodeURIComponent(q));
      const recipes=res.recipes||[];
      const dl=qs('#barCocktailDatalist');
      if(dl) dl.innerHTML=recipes.map(r=>`<option value="${escapeHtml(r.name)}"></option>`).join('');
      if(suggestionBox){
        suggestionBox.innerHTML=recipes.slice(0,8).map(r=>`<button type="button" class="bar-suggestion-row" data-cocktail-id="${r.id}"><b>${escapeHtml(r.name)}</b><span>${escapeHtml(fmtMoney(r.cost_2026_gross_with_waste))} · margen ${escapeHtml(fmtLabNum(r.margin_percent_2026,1))}%</span></button>`).join('');
      }
      const exact=recipes.find(r=>r.name.toLowerCase()===q.toLowerCase());
      if(exact){
        const sel=qs('#barCocktailSelect'); if(sel) sel.value=exact.id;
        cocktailSearch.dataset.selectedCocktailId = exact.id;
        // No abrir ficha automáticamente: queda preparada y se abre solo al pulsar Ver ficha.
      } else {
        cocktailSearch.dataset.selectedCocktailId = '';
      }
    });
    const barBeverageLoad=qs('#labBarBeverageLoadBtn'); if(barBeverageLoad) barBeverageLoad.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/beverages/load-demo', {}); alert(res.message||'Bebidas actualizadas'); refreshBarBeverages(); });
    const barMixerLoad=qs('#labBarMixerLoadBtn'); if(barMixerLoad) barMixerLoad.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/mixers/load-demo', {}); alert(res.message||'Mixers actualizados'); refreshBarMixers(); });
    const barReceiptSim=qs('#labBarReceiptSimBtn'); if(barReceiptSim) barReceiptSim.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/receipts/simulate', {receipt_variant:'beverages'}); renderBarReceipts(res); });
    const barReceiptShared=qs('#labBarReceiptSharedBtn'); if(barReceiptShared) barReceiptShared.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/receipts/simulate', {receipt_variant:'shared'}); renderBarReceipts(res); });
    const sharedReceiptOrder=qs('#labSharedReceiptOrderBtn'); if(sharedReceiptOrder) sharedReceiptOrder.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/shared-receipts/simulate', {receipt_variant:'pedido_previo'}); renderSharedReceipts(res); });
    const sharedReceiptPct=qs('#labSharedReceiptPctBtn'); if(sharedReceiptPct) sharedReceiptPct.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/shared-receipts/simulate', {receipt_variant:'porcentaje'}); renderSharedReceipts(res); });
    const sharedReceiptReview=qs('#labSharedReceiptReviewBtn'); if(sharedReceiptReview) sharedReceiptReview.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/shared-receipts/simulate', {receipt_variant:'sin_regla'}); renderSharedReceipts(res); });
    const barOrderSim=qs('#labBarOrderSimBtn'); if(barOrderSim) barOrderSim.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/orders/simulate', {receipt_variant:'match'}); renderBarOrders(res); });
    const barOrderDiff=qs('#labBarOrderDiffBtn'); if(barOrderDiff) barOrderDiff.addEventListener('click', async()=>{ const res=await postForm('/api/lab/bar/orders/simulate', {receipt_variant:'short'}); renderBarOrders(res); });
    document.addEventListener('input', ev=>{
      const lf=ev.target.closest('.cocktail-line-form');
      if(!lf) return;
      if(ev.target.matches('[name="ingredient_name"], [name="origin"]')){
        const name=(lf.querySelector('[name="ingredient_name"]')?.value || '').trim();
        const origin=(lf.querySelector('[name="origin"]')?.value || 'stock_bar');
        const src=findBarSource(name, origin);
        const unit=lf.querySelector('[name="unit"]'); if(unit && src.unit) unit.value=src.unit;
        const cost=lf.querySelector('[name="cost_unit_2026"]'); if(cost) cost.value=String(src.cost||0);
        const costPill=lf.querySelector('.cost-auto-pill'); if(costPill) costPill.textContent=(src.cost||0).toFixed(5).replace(/0+$/,'').replace(/\.$/,'')+' €/u';
        const waste=lf.querySelector('[name="waste_percent"]'); if(waste && (!waste.value || Number(waste.value)===0) && src.waste) waste.value=String(src.waste);
      }
    });
    document.addEventListener('change', ev=>{
      const lf=ev.target.closest('.cocktail-line-form');
      if(!lf) return;
      if(ev.target.matches('[name="ingredient_name"], [name="origin"]')){
        const name=(lf.querySelector('[name="ingredient_name"]')?.value || '').trim();
        const origin=(lf.querySelector('[name="origin"]')?.value || 'stock_bar');
        const src=findBarSource(name, origin);
        const unit=lf.querySelector('[name="unit"]'); if(unit && src.unit) unit.value=src.unit;
        const cost=lf.querySelector('[name="cost_unit_2026"]'); if(cost) cost.value=String(src.cost||0);
        const costPill=lf.querySelector('.cost-auto-pill'); if(costPill) costPill.textContent=(src.cost||0).toFixed(5).replace(/0+$/,'').replace(/\.$/,'')+' €/u';
      }
    });
    document.addEventListener('submit', async ev=>{
      const hf=ev.target.closest('#barCocktailHeaderForm');
      if(hf){ ev.preventDefault(); const data=Object.fromEntries(new FormData(hf).entries()); const res=await postForm('/api/lab/bar/cocktail/save', data); if(res.ok){ const id=res.recipe_id; await refreshBar(); await showCocktailDetail(id); } else alert(res.message||'No se pudo guardar'); return; }
      const lf=ev.target.closest('.cocktail-line-form');
      if(lf){ ev.preventDefault(); const rid=lf.dataset.recipeId; const data=Object.fromEntries(new FormData(lf).entries()); const res=await postForm('/api/lab/bar/cocktail/'+encodeURIComponent(rid)+'/line/save', data); if(res.ok){ await refreshBar(); await showCocktailDetail(rid); } else alert(res.message||'No se pudo guardar línea'); return; }
      const sf=ev.target.closest('#barCocktailStepsForm');
      if(sf){ ev.preventDefault(); const rid=sf.dataset.recipeId; const data=Object.fromEntries(new FormData(sf).entries()); const res=await postForm('/api/lab/bar/cocktail/'+encodeURIComponent(rid)+'/steps/save', data); if(res.ok){ await showCocktailDetail(rid); } else alert(res.message||'No se pudo guardar procedimiento'); return; }
    });
    document.addEventListener('click', async ev=>{
      const up=ev.target.closest('.cocktail-photo-upload');
      if(up){ const inp=qs('#barCocktailHeaderForm input[name="photo_path"]'); if(inp){ inp.focus(); inp.select(); } return; }
      const rm=ev.target.closest('.cocktail-photo-remove');
      if(rm){ const inp=qs('#barCocktailHeaderForm input[name="photo_path"]'); if(inp){ inp.value='pendiente_subir'; inp.focus(); } return; }
      const del=ev.target.closest('.cocktail-line-delete'); if(del){ const res=await postForm('/api/lab/bar/cocktail/'+encodeURIComponent(del.dataset.recipeId)+'/line/'+encodeURIComponent(del.dataset.lineId)+'/delete', {}); if(res.ok){ await refreshBar(); await showCocktailDetail(del.dataset.recipeId); } return; }
      const b=ev.target.closest('[data-cocktail-id]');
      if(b){
        const box=qs('#barCocktailSuggestions'); if(box) box.innerHTML='';
        const search=qs('#barCocktailSearch');
        if(search){ search.value=(b.querySelector('b')?.textContent || '').trim(); search.dataset.selectedCocktailId=b.dataset.cocktailId; }
        const sel=qs('#barCocktailSelect'); if(sel) sel.value=b.dataset.cocktailId;
        // Seleccionar sugerencia no abre la ficha. Se abre solo con Ver ficha.
        return;
      }
      const v=ev.target.closest('[data-beverage-code]'); if(v){ const mode = (v.dataset.beverageCode.includes('VODKA-REDBULL') || v.dataset.beverageCode.includes('WHISKY-COLA')) ? 'bundle_price' : ''; renderBeverageSale(await postForm('/api/lab/bar/beverages/simulate', {service_code:v.dataset.beverageCode, billing_mode:mode})); }});
    const ref=qs('[data-lab-refresh]'); if(ref) ref.addEventListener('click', refreshLab);
    refreshLab();
  });
})();

// LAB · Flujos críticos móvil + ALFI
(function(){
  const qs=(s,root=document)=>root.querySelector(s);
  function esc(v){return String(v??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
  async function getJson(url){const r=await fetch(url,{cache:'no-store'}); return await r.json();}
  async function postForm(url,obj){const fd=new FormData(); Object.entries(obj||{}).forEach(([k,v])=>fd.append(k,v)); const r=await fetch(url,{method:'POST',body:fd}); return await r.json();}
  function fmtImpact(impact){
    if(!impact) return '';
    if(Array.isArray(impact.stock_preview)) return '<ul>'+impact.stock_preview.map(x=>'<li>'+esc(typeof x==='string'?x:JSON.stringify(x))+'</li>').join('')+'</ul>';
    return '<pre>'+esc(JSON.stringify(impact,null,2))+'</pre>';
  }
  function renderSummary(data){
    const el=qs('#criticalFlowSummary'); if(!el) return;
    if(!data||data.ok===false){ el.innerHTML='<div class="lab-warn">Sin resumen de flujos críticos.</div>'; return; }
    const c=data.counts||{};
    const drafts=data.drafts||[];
    el.innerHTML='<div class="lab-metrics"><span>Correcciones: <b>'+esc(c.validation_correction||0)+'</b></span><span>Pedidos editables: <b>'+esc(c.editable_order_suggestions||0)+'</b></span><span>Racionados: <b>'+esc(c.portioning||0)+'</b></span><span>ALFI: <b>'+esc(c.alfi_preview||0)+'</b></span></div>'+
      '<h4>Últimos borradores</h4>'+(drafts.length?'<ul>'+drafts.map(d=>'<li><b>'+esc(d.title)+'</b> · '+esc(d.flow_type)+' · '+esc(d.status)+' · '+esc(d.created_at)+'<br><button class="btn ghost" data-critical-confirm="'+esc(d.id)+'">Registrar confirmación LAB</button><details><summary>Impacto</summary>'+fmtImpact(d.impact)+'</details></li>').join('')+'</ul>':'<p>No hay borradores.</p>')+
      '<p class="muted">'+(data.rules||[]).map(esc).join(' · ')+'</p>';
  }
  function renderResult(data){
    const el=qs('#criticalFlowResult'); if(!el) return;
    if(!data||data.ok===false){ el.innerHTML='<div class="lab-warn">'+esc(data&&data.message||'Error')+'</div>'; return; }
    if(data.results){
      el.innerHTML='<div class="lab-ok">'+esc(data.message||'Simulacro creado')+'</div>'+
        '<h4>Conclusiones</h4><ul>'+((data.conclusions||[]).map(x=>'<li>'+esc(x)+'</li>').join(''))+'</ul>'+
        '<h4>Flujos</h4>'+data.results.map(r=>'<div class="lab-mini-card"><b>'+esc(r.title)+'</b><p>'+esc(r.message||'')+'</p>'+fmtImpact(r.impact)+'</div>').join('');
      return;
    }
    el.innerHTML='<div class="lab-ok">'+esc(data.message||'Propuesta creada')+'</div><h4>'+esc(data.title||data.flow_type||'Prelectura')+'</h4>'+fmtImpact(data.impact)+'<details><summary>Payload</summary><pre>'+esc(JSON.stringify(data.payload||{},null,2))+'</pre></details>';
  }
  async function refresh(){ try{ renderSummary(await getJson('/api/lab/critical/summary')); }catch(e){} }
  document.addEventListener('DOMContentLoaded',()=>{
    const sim=qs('#labCriticalSimBtn'); if(sim) sim.addEventListener('click',async()=>{ const d=await postForm('/api/lab/critical/simulate',{}); renderResult(d); await refresh(); });
    const ref=qs('#labCriticalRefreshBtn'); if(ref) ref.addEventListener('click',refresh);
    const form=qs('#labCriticalAlfiForm'); if(form) form.addEventListener('submit',async(ev)=>{ ev.preventDefault(); const text=(new FormData(form).get('text')||'').toString(); const d=await postForm('/api/lab/critical/alfi-preview',{text:text,actor:'ALFI LAB'}); renderResult(d); await refresh(); });
    document.addEventListener('click',async(ev)=>{ const b=ev.target.closest('[data-critical-confirm]'); if(!b) return; const d=await postForm('/api/lab/critical/confirm',{draft_id:b.dataset.criticalConfirm,actor:'Sistema Demo',note:'Confirmación LAB desde pantalla'}); renderResult(d); await refresh(); });
    refresh();
  });
})();
