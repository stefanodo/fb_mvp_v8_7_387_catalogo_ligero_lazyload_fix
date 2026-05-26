(function(){
  function init(){
    document.querySelectorAll('body[data-page="inicio"] .direction-monthly-panel').forEach((panel, idx)=>{
      if(panel.dataset.compactReady) return;
      panel.dataset.compactReady='1';
      panel.classList.add('home-compact-panel');
      if(idx>0) panel.classList.add('is-collapsed');
      const head=panel.querySelector('.section-head') || panel.firstElementChild;
      const btn=document.createElement('button');
      btn.type='button';
      btn.className='btn tiny home-panel-toggle';
      btn.textContent=panel.classList.contains('is-collapsed')?'Ver detalle':'Ocultar detalle';
      btn.addEventListener('click',()=>{
        panel.classList.toggle('is-collapsed');
        btn.textContent=panel.classList.contains('is-collapsed')?'Ver detalle':'Ocultar detalle';
      });
      if(head) head.appendChild(btn);
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
