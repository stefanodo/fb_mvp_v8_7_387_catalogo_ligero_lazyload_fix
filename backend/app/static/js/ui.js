// ui.js — F&B MVP · toasts, menú hamburguesa, tabs admin
// Cargado como archivo estático externo — sin duplicados

// ============================================================
// SISTEMA DE TOASTS — notificaciones visibles y auto-dismiss
// ============================================================
(function(){
  const ICONS = { ok:'✓', err:'✕', warn:'⚠', info:'ℹ' };
  const DURATIONS = { ok:3500, err:6000, warn:5000, info:4000 };

  function showToast(type, text, duration) {
    const container = document.getElementById('toast-container');
    if (!container || !text) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span class="toast-icon">${ICONS[type]||'ℹ'}</span><span class="toast-body">${text}</span><button class="toast-close" aria-label="Cerrar">×</button>`;
    container.appendChild(toast);
    const close = () => {
      toast.classList.add('hiding');
      setTimeout(() => toast.remove(), 200);
    };
    toast.querySelector('.toast-close').addEventListener('click', close);
    setTimeout(close, duration || DURATIONS[type] || 4000);
    return toast;
  }
  window.showToast = showToast;

  // Leer query params al cargar y mostrar toasts automáticamente
  document.addEventListener('DOMContentLoaded', function() {
    const p = new URLSearchParams(window.location.search);

    // Mensajes OK
    if (p.get('mv_ok'))        showToast('ok', 'Movimiento guardado correctamente.');
    if (p.get('validated_ok')) showToast('ok', 'Albarán validado e impactado en stock.');
    if (p.get('ocr_ok') && !p.get('ocr_skip')) showToast('ok', 'OCR ejecutado correctamente.');
    if (p.get('ocr_ok') && p.get('ocr_skip'))  showToast('info', 'OCR ya leído anteriormente. Se abre revisión sin reprocesar.');
    if (p.get('ocr_line_ok'))  showToast('ok', 'Línea OCR aceptada y guardada.');
    if (p.get('head_ok'))      showToast('ok', 'Proveedor aplicado correctamente.');
    if (p.get('ok') === '1' || p.get('ok') === 'photo') showToast('ok', p.get('ok') === 'photo' ? 'Foto guardada correctamente.' : 'Cambios guardados.');
    if (p.get('ing_ok'))       showToast('ok', 'Ingrediente guardado.');
    if (p.get('del_ok'))       showToast('ok', 'Línea eliminada.');
    if (p.get('reset_ok'))     showToast('ok', 'Albarán reiniciado. Movimientos asociados borrados.');
    if (p.get('deleted_ok'))   showToast('ok', 'Albarán eliminado.');
    if (p.get('created'))      showToast('ok', 'Borrador creado. Añade fotos para procesar con OCR.');
    if (p.get('price_ok'))     showToast('ok', 'Precio actualizado.');
    if (p.get('lab'))          showToast('ok', 'Artículo creado desde Laboratorio.');
    if (p.get('provider_deleted')) showToast('ok', 'Proveedor eliminado.');
    if (p.get('provider_archived')) showToast('info', 'Proveedor archivado (tiene historial). Ya no aparece en formularios.');
    if (p.get('cleared_pending')) showToast('ok', `${p.get('cleared_pending')} albarán(es) pendiente(s) eliminado(s).`);
    if (p.get('added'))        showToast('ok', `${p.get('added')} línea(s) sugerida(s) añadida(s) al pedido.`);

    // Mensajes de espera
    if (p.get('ocr_wait'))     showToast('warn', 'OCR procesando en segundo plano. La pantalla se actualizará cuando termine.', 8000);

    // Errores
    const err = p.get('err');
    if (err) {
      const errMsgs = {
        '1': 'No se pudo guardar. Revisa los campos y vuelve a intentarlo.',
        'item': 'Artículo no encontrado. Asegúrate de seleccionarlo de la lista.',
        'unit': 'Unidad no válida para ese artículo.',
        'qty': 'Cantidad inválida.',
        'ing': 'Ingrediente no encontrado.',
        'subrecipe': 'Sub-receta no válida o no seleccionada.',
        'item_dup': 'Ya existe un artículo con ese nombre y unidad.',
        'dblock': 'La base de datos estaba ocupada. Vuelve a intentarlo.',
        'db_locked': 'La base de datos estaba ocupada. Cierra otra ventana del sistema.',
        'name': 'El nombre no puede estar vacío.',
        'dup': 'Ya existe una receta con ese nombre.',
        'photo': 'No se pudo guardar la foto. Comprueba el formato (JPG, PNG, HEIC).',
        'waste_local': 'No se puede confirmar la merma: falta seleccionar un local concreto.',
        'waste_responsible': 'No se puede confirmar la merma: falta responsable.',
        'waste_article': 'No se puede confirmar la merma: falta vincular artículo/elaboración real del catálogo.',
        'waste_qty': 'No se puede confirmar la merma: falta cantidad válida o unidad compatible.',
        'waste_warehouse': 'No se puede confirmar la merma: el almacén no pertenece al local.',
        'waste_confirm': 'No se pudo confirmar la merma. Completa los datos obligatorios.',
      };
      showToast('err', errMsgs[err] || `Error: ${err}. Revisa los campos.`);
    }
    const ocrErr = p.get('ocr_err');
    if (ocrErr === 'locked') showToast('err', 'La base estaba ocupada. Cierra otra ventana y vuelve a pulsar una sola vez.', 7000);
    else if (ocrErr)         showToast('err', 'El OCR no pudo terminar. Vuelve a intentarlo.', 6000);

    const ocrLineErr = p.get('ocr_line_err');
    if (ocrLineErr === 'resolve') showToast('err', 'Selecciona o crea un artículo válido antes de aceptar la línea.', 6000);
    else if (ocrLineErr === 'locked') showToast('err', 'La base estaba ocupada al guardar la línea. Vuelve a pulsar.', 6000);
    else if (ocrLineErr === 'missing') showToast('warn', 'La línea OCR ya no existe. Recarga la revisión del albarán.');
    else if (ocrLineErr === 'state')   showToast('warn', 'El albarán ya no está pendiente. La línea no se pudo aceptar.');
    else if (ocrLineErr)               showToast('err', 'No se pudo guardar la línea OCR.');

    const supErr = p.get('ocr_supplier_err');
    if (supErr === 'resolve') showToast('err', 'No se pudo aplicar el proveedor. Selecciona uno existente o marca "Crear proveedor".', 6000);
    else if (supErr)          showToast('err', 'No se pudo aplicar el proveedor detectado.');

    const provErr = p.get('provider_err');
    if (provErr === 'not_found')     showToast('err', 'Proveedor no encontrado.');
    else if (provErr === 'delete_failed') showToast('err', 'No se pudo eliminar el proveedor.');

    // Limpiar params de estado de la URL sin recargar
    const clean = ['mv_ok','validated_ok','ocr_ok','ocr_skip','ocr_line_ok','head_ok','ok',
                   'ing_ok','del_ok','reset_ok','deleted_ok','created','price_ok','lab',
                   'provider_deleted','provider_archived','cleared_pending','added','ocr_wait',
                   'err','ocr_err','ocr_line_err','ocr_supplier_err','provider_err'];
    let changed = false;
    const url = new URL(window.location.href);
    clean.forEach(k => { if (url.searchParams.has(k)) { url.searchParams.delete(k); changed = true; } });
    if (changed) history.replaceState({}, '', url.toString());
  });
})();

// ============================================================
// TABS CATÁLOGO + MENÚ HAMBURGUESA MÓVIL
// ============================================================
function switchAdminTab(btn, tabId) {
  // Desactivar todos los tabs
  document.querySelectorAll('.admin-tab').forEach(t => t.style.display = 'none');
  document.querySelectorAll('.subnav-btn').forEach(b => b.classList.remove('active'));
  // Activar el seleccionado
  const tab = document.getElementById(tabId);
  if (tab) tab.style.display = 'block';
  btn.classList.add('active');
  // Guardar tab activo en sessionStorage para mantenerlo al volver
  try { sessionStorage.setItem('adminTab', tabId); } catch(e) {}
}

// Restaurar tab activo al cargar la página de admin
document.addEventListener('DOMContentLoaded', function() {
  if (document.getElementById('tab-articulos')) {
    try {
      const saved = sessionStorage.getItem('adminTab');
      if (saved && document.getElementById(saved)) {
        const btn = document.querySelector(`.subnav-btn[onclick*="${saved}"]`);
        if (btn) switchAdminTab(btn, saved);
      }
    } catch(e) {}
  }
});

// ============================================================
// MENÚ HAMBURGUESA MÓVIL
// ============================================================
function toggleMobileMenu() {
  const menu     = document.getElementById('mobileMenu');
  const backdrop = document.getElementById('mobileMenuBackdrop');
  const btn      = document.getElementById('hamburgerBtn');
  if (!menu) return;
  const isOpen = menu.classList.contains('open');
  if (isOpen) {
    closeMobileMenu();
  } else {
    menu.classList.add('open');
    backdrop && backdrop.classList.add('open');
    btn && btn.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

function closeMobileMenu() {
  const menu     = document.getElementById('mobileMenu');
  const backdrop = document.getElementById('mobileMenuBackdrop');
  const btn      = document.getElementById('hamburgerBtn');
  menu     && menu.classList.remove('open');
  backdrop && backdrop.classList.remove('open');
  btn      && btn.classList.remove('open');
  document.body.style.overflow = '';
}

// Cerrar menú con Escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeMobileMenu();
});

// v8_7_283 · Fix iOS: no sintetizar clicks en touchend.
// El código anterior hacía e.preventDefault()+el.click() en cada touchend.
// En móvil, al hacer scroll y terminar el dedo encima de un botón, podía disparar submit
// y crear pedidos/guardar formularios sin intención. Dejamos que Safari gestione el click
// normal y solo bloqueamos taps que vienen de un desplazamiento real.
(function(){
  let sx=0, sy=0, moved=false;
  document.addEventListener('touchstart', function(e){
    const t=e.touches && e.touches[0];
    if(!t) return;
    sx=t.clientX; sy=t.clientY; moved=false;
  }, {passive:true});
  document.addEventListener('touchmove', function(e){
    const t=e.touches && e.touches[0];
    if(!t) return;
    if(Math.abs(t.clientX-sx)>10 || Math.abs(t.clientY-sy)>10) moved=true;
  }, {passive:true});
  document.addEventListener('click', function(e){
    const clickable = e.target && e.target.closest && e.target.closest('button, .btn, .nav-btn, .mobile-nav-btn, a.mini, a.btn');
    if(clickable && moved){
      e.preventDefault();
      e.stopPropagation();
      moved=false;
    }
  }, true);
})();

// Fix iOS Safari: tablas scrollables con touch
document.querySelectorAll('.table-wrap, .tablewrap').forEach(el => {
  el.style.webkitOverflowScrolling = 'touch';
});

// Ajuste de altura en móvil (iOS safe area)
function setMobileVh() {
  const vh = window.innerHeight * 0.01;
  document.documentElement.style.setProperty('--vh', `${vh}px`);
}
setMobileVh();
window.addEventListener('resize', setMobileVh);

// v8_7_332 · Inventario/Stock: navegación estable sin salto ni bloqueo por familia.
(function(){
  const INV_SCROLL_KEY = 'systemMacInventoryScrollY';
  const STOCK_SCROLL_KEY = 'systemMacStockScrollY';

  function restoreScroll(key){
    try{
      const raw = sessionStorage.getItem(key);
      if(!raw) return;
      const y = Number(raw || '0');
      sessionStorage.removeItem(key);
      if(!Number.isFinite(y) || y < 0) return;
      const run = () => window.scrollTo({top:y, behavior:'auto'});
      run(); setTimeout(run, 30); setTimeout(run, 120);
    }catch(_e){}
  }

  document.addEventListener('DOMContentLoaded', function(){
    const params = new URLSearchParams(location.search);
    if(params.get('page') === 'inventario') restoreScroll(INV_SCROLL_KEY);
    if(params.get('page') === 'stock') restoreScroll(STOCK_SCROLL_KEY);
  });

  document.addEventListener('click', function(e){
    const inv = e.target.closest('a.inventory-mode-link');
    if(inv){
      e.preventDefault();
      try{ sessionStorage.setItem(INV_SCROLL_KEY, String(window.scrollY || 0)); }catch(_e){}
      document.querySelectorAll('a.inventory-mode-link').forEach(x=>x.classList.remove('active','pending'));
      inv.classList.add('active','pending');
      const url = new URL(inv.href, window.location.origin);
      // limpiar familia heredada incompatible y forzar familia del bloque pulsado
      const mode = inv.dataset.invMode || url.searchParams.get('inv_mode') || 'materias_primas';
      const family = inv.dataset.invFamily || (mode === 'producciones' ? 'frio' : mode === 'limpieza' ? 'limpieza' : mode === 'libres' ? 'libres' : 'verduras');
      url.searchParams.set('page','inventario');
      url.searchParams.set('inv_mode', mode);
      url.searchParams.set('inv_family', family);
      url.searchParams.set('inv_nav_ts', String(Date.now()));
      url.hash = 'inventoryModePanel';
      window.location.assign(url.toString());
      return;
    }
    const stock = e.target.closest('a.stock-block-btn');
    if(stock){
      try{ sessionStorage.setItem(STOCK_SCROLL_KEY, String(window.scrollY || 0)); }catch(_e){}
      const url = new URL(stock.href, window.location.origin);
      url.searchParams.set('stock_nav_ts', String(Date.now()));
      url.hash = 'stockNavBlocks';
      stock.href = url.toString();
    }
  }, true);
})();


// v8_7_350 · Beta local: limpiar service worker/cachés antiguos que podían enseñar pantallas mezcladas en Safari.
(function(){
  if(window.__systemMacCacheGuardV350) return;
  window.__systemMacCacheGuardV350 = true;
  function closeTransientUi(){
    try{ document.body.classList.remove('mobile-menu-open'); }catch(_e){}
    const menu=document.getElementById('mobileMenu'); if(menu) menu.classList.remove('open','is-open','active');
    const backdrop=document.getElementById('mobileMenuBackdrop'); if(backdrop) backdrop.classList.remove('open','is-open','active');
  }
  document.addEventListener('DOMContentLoaded', closeTransientUi);
  window.addEventListener('pageshow', function(){ closeTransientUi(); });
  if('serviceWorker' in navigator){
    navigator.serviceWorker.getRegistrations().then(regs=>{
      regs.forEach(reg=>{ try{ reg.unregister(); }catch(_e){} });
    }).catch(()=>{});
  }
  if(window.caches && caches.keys){
    caches.keys().then(keys=>keys.forEach(k=>{ try{ caches.delete(k); }catch(_e){} })).catch(()=>{});
  }
})();
