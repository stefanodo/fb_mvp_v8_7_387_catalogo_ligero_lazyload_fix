// Lightweight lazy-load helpers for large page fragments
(function(){
  function runInlineScripts(container){
    const scripts = container.querySelectorAll('script');
    scripts.forEach(oldScript => {
      const newScript = document.createElement('script');
      if (oldScript.src) {
        newScript.src = oldScript.src;
      }
      if (oldScript.type) {
        newScript.type = oldScript.type;
      }
      newScript.textContent = oldScript.textContent;
      oldScript.parentNode.replaceChild(newScript, oldScript);
    });
  }

  function loadFragment(url, containerId){
    const container = document.getElementById(containerId);
    if(!container) return;
    fetch(url).then(r=>{
      if(!r.ok) throw new Error('network');
      return r.text();
    }).then(html=>{
      container.innerHTML = html;
      runInlineScripts(container);
    }).catch(e=>{
      container.innerHTML = '<div class="notice err">No se pudo cargar el contenido.</div>';
      console.error(e);
    });
  }
  window.lazyLoads = { loadFragment };
})();
