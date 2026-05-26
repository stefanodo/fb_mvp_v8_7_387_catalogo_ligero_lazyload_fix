from fastapi import APIRouter, Form, File, UploadFile, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse, Response
import base64
import io
import socket


from app.services.ai_orchestrator_service import capabilities, handle_assistant_command, receive_document_for_review, transcribe_oido_alfi_audio, explain_command

router = APIRouter()




def _detect_lan_ip() -> str:
    """Devuelve una IP probable del Mac accesible desde móvil en Wi-Fi/hotspot."""
    candidates = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        candidates.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                candidates.append(ip)
    except Exception:
        pass
    for ip in candidates:
        if ip.startswith(("192.168.", "10.", "172.")):
            return ip
    return candidates[0] if candidates else "127.0.0.1"


def _mobile_base_url(request: Request) -> str:
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    ip = _detect_lan_ip()
    scheme = request.url.scheme or "http"
    host = ip if ip not in {"127.0.0.1", "localhost"} else (request.url.hostname or ip)
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    return f"{scheme}://{host}{'' if default_port else ':' + str(port)}"


@router.get("/api/mobile-beta/status")
def api_mobile_beta_status(request: Request):
    base = _mobile_base_url(request)
    client_ip = request.client.host if request.client else ""
    return JSONResponse({
        "ok": True,
        "mode": "BETA_LOCAL",
        "url": base + "/?page=inicio&center_id=0",
        "base_url": base,
        "lan_ip": _detect_lan_ip(),
        "client_ip": client_ip,
        "final_architecture": "dominio/PWA/login/base de datos central; QR solo para beta local",
    })


@router.get("/mobile-beta/qr.png")
def mobile_beta_qr(request: Request):
    try:
        import qrcode
        url = _mobile_base_url(request) + "/?page=inicio&center_id=0"
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control":"no-store"})
    except Exception:
        return Response(b"", media_type="image/png", status_code=500)


@router.get("/mobile-beta", response_class=HTMLResponse)
def mobile_beta_page(request: Request):
    base = _mobile_base_url(request)
    app_url = base + "/?page=inicio&center_id=0"
    qr_url = base + "/mobile-beta/qr.png"
    return f"""
<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Acceso móvil beta · System MAC</title>
<style>
body{{margin:0;background:#080d14;color:#f3f6fb;font-family:system-ui,-apple-system,Segoe UI,sans-serif;padding:18px}}
.wrap{{max-width:900px;margin:0 auto}} .card{{background:#121a26;border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:16px;margin:12px 0;box-shadow:0 14px 30px rgba(0,0,0,.25)}}
code,input{{background:#07111d;border:1px solid rgba(212,166,74,.35);color:#ffe4a5;border-radius:12px;padding:10px;display:block;width:100%;box-sizing:border-box}}
button,a.btn{{display:inline-flex;align-items:center;gap:8px;border:1px solid rgba(212,166,74,.55);background:rgba(212,166,74,.16);color:#ffe4a5;border-radius:12px;padding:10px 12px;text-decoration:none;font-weight:800;margin:5px 6px 5px 0}}
.small{{color:#aeb8c6;font-size:13px;line-height:1.45}} img{{background:#fff;border-radius:16px;padding:10px;max-width:240px;width:70%;height:auto}}
.warn{{border-color:rgba(255,201,87,.4);background:rgba(255,201,87,.10)}} .ok{{border-color:rgba(74,222,128,.35);background:rgba(74,222,128,.08)}}
</style></head><body><div class='wrap'>
<h1>📱 Acceso móvil beta local</h1>
<div class='card warn'><b>Beta local:</b> este QR/IP es solo para probar mientras System MAC corre en tu Mac. En versión final será dominio/PWA/login, sin QR.</div><div class='card warn'><b>Safari/iPhone:</b> esta beta usa <code>http://IP:8000</code>. Si Safari bloquea por “Solo HTTPS”, desactívalo temporalmente para esta prueba o usa Chrome. La versión final online usará HTTPS real.</div>
<div class='card'><h2>URL actual para móvil</h2><input id='mobileUrl' readonly value='{app_url}'><button onclick='copyUrl()'>Copiar enlace</button><a class='btn' href='{app_url}'>Abrir app</a><p class='small'>Mac detectado en red: <code>{base}</code>. Si cambias de Wi‑Fi o usas hotspot del iPhone, vuelve a abrir esta pantalla para regenerar el QR.</p></div>
<div class='card'><h2>QR dinámico</h2><img src='{qr_url}?t={id(request)}' alt='QR móvil System MAC'></div>
<div class='card ok'><h2>Diagnóstico</h2><p id='diag' class='small'>Comprobando…</p><button onclick='checkStatus()'>Revisar conexión</button><button onclick='clearCaches()'>Limpiar caché móvil / recargar app</button></div>
<script>
async function copyUrl(){{try{{await navigator.clipboard.writeText(document.getElementById('mobileUrl').value);alert('Enlace copiado');}}catch(e){{document.getElementById('mobileUrl').select();}}}}
async function checkStatus(){{try{{let r=await fetch('/api/mobile-beta/status',{{cache:'no-store'}});let j=await r.json();diag.textContent='Servidor OK · URL: '+j.url+' · Cliente: '+(j.client_ip||'');}}catch(e){{diag.textContent='No pude comprobar. Revisa que el Mac siga encendido y en la misma red.';}}}}
async function clearCaches(){{try{{if('serviceWorker' in navigator){{let regs=await navigator.serviceWorker.getRegistrations(); for(const reg of regs) await reg.unregister();}} if(window.caches){{let keys=await caches.keys(); for(const k of keys) await caches.delete(k);}} alert('Caché limpiada. Se recargará.'); location.href='{app_url}&_reload=' + Date.now();}}catch(e){{location.href='{app_url}&_reload=' + Date.now();}}}}
checkStatus();
</script></div></body></html>"""

@router.get("/api/oido-alfi/capabilities")
def api_oido_alfi_capabilities():
    return JSONResponse(capabilities())




@router.get("/api/oido-alfi/suggest")
def api_oido_alfi_suggest(center_id: int = Query(0), text: str = Query("")):
    """Prelectura sin ejecutar para endurecer sugerencias antes de confirmar."""
    return JSONResponse(explain_command(text, center_id=center_id))

@router.post("/api/oido-alfi/command")
def api_oido_alfi_command(center_id: int = Form(0), text: str = Form(""), requested_by: str = Form("")):
    return JSONResponse(handle_assistant_command(text, center_id=center_id, requested_by=requested_by))


@router.get("/api/oido-alfi/audio-diagnostics")
def api_oido_alfi_audio_diagnostics():
    from app.services.operational_quick_service import get_ai_status
    st = get_ai_status()
    provider = st.get("stt_provider") or st.get("stt_mode") or "local"
    return JSONResponse({
        "ok": True,
        "backend_stt_ready": bool(st.get("stt_configured")),
        "openai_key_loaded": bool(st.get("openai_key_loaded") or st.get("has_key")),
        "deepgram_key_loaded": bool(st.get("deepgram_key_loaded")),
        "stt_provider": provider,
        "stt_mode": provider,
        "stt_model": st.get("stt_model") or ("nova-3" if provider == "deepgram" else "gpt-4o-mini-transcribe"),
        "language": st.get("stt_language") or "es",
        "browser_note": "La grabación directa depende del permiso del navegador. Si falla, usa dictado del teclado y Ejecutar.",
    })


@router.post("/api/oido-alfi/document")
async def api_oido_alfi_document(center_id: int = Form(0), doc_type: str = Form("unknown"), file: UploadFile = File(...)):
    return JSONResponse(await receive_document_for_review(file, doc_type=doc_type, center_id=center_id))


@router.post("/api/oido-alfi/transcribe-audio")
async def api_oido_alfi_transcribe_audio(center_id: int = Form(0), requested_by: str = Form(""), file: UploadFile = File(...)):
    transcribed = await transcribe_oido_alfi_audio(file, center_id=center_id)
    if not transcribed.get("ok"):
        return JSONResponse({**transcribed, "handled": False, "action_result": None})
    text = transcribed.get("text") or ""
    action = handle_assistant_command(text, center_id=center_id, requested_by=requested_by or "voz")
    return JSONResponse({**transcribed, "handled": bool(action.get("handled")), "action_result": action, "message": action.get("message") or transcribed.get("message")})


@router.post("/api/oido-alfi/transcribe-test")
async def api_oido_alfi_transcribe_test(center_id: int = Form(0), file: UploadFile = File(...)):
    """Prueba de voz segura: transcribe y prelee, pero no crea pedidos/mermas/producciones."""
    transcribed = await transcribe_oido_alfi_audio(file, center_id=center_id)
    if not transcribed.get("ok"):
        return JSONResponse({**transcribed, "audio_received": True, "preview": None, "message": transcribed.get("message") or "No pude transcribir el audio."})
    text = transcribed.get("text") or ""
    preview = explain_command(text, center_id=center_id)
    return JSONResponse({**transcribed, "audio_received": True, "preview": preview, "message": "Prueba de voz terminada. No se ha creado ninguna acción."})


@router.get("/ai-system/ui")
def ai_system_ui(center_id: int = Query(0)):
    caps = capabilities()
    status = caps.get("ai_status") or {}
    html = f"""
<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>OÍDO ALFI · IA System MAC</title>
<link rel='stylesheet' href='/static/style.css'><link rel='stylesheet' href='/static/css/voice_assistant.css'>
<style>
body{{background:#090d14;color:#eef4ff;font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:28px}}
.ai-wrap{{max-width:1100px;margin:0 auto}} .ai-top{{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:18px}}
.ai-card{{background:rgba(18,26,38,.88);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:16px;margin:12px 0;box-shadow:0 12px 32px rgba(0,0,0,.25)}}
.ai-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}} .chip{{display:inline-flex;border:1px solid rgba(212,166,74,.45);border-radius:999px;padding:6px 10px;margin:4px;color:#ffe4a5;background:rgba(212,166,74,.10);font-weight:800}}
input,select,button{{border-radius:12px;padding:10px;border:1px solid rgba(255,255,255,.18);background:#101722;color:#fff}} button,.btn{{background:#1b2534;color:#fff;text-decoration:none;font-weight:900}} .gold{{border-color:#d4a64a;background:rgba(212,166,74,.18);color:#ffe4a5}}
.small{{color:#aeb8c6;font-size:13px;line-height:1.45}} code{{color:#ffe4a5}}
</style></head><body><div class='ai-wrap'>
<div class='ai-top'><div><h1>🎧 OÍDO ALFI · IA System MAC</h1><p class='small'>Núcleo central: consulta, lectura documental, voz y propuestas pendientes con revisión humana.</p></div><a class='btn gold' href='/?page=inicio&center_id={int(center_id or 0)}'>← Inicio System MAC</a></div>
<div class='ai-card'><b>Estado IA:</b> <span class='chip'>{status.get('status_label','LOCAL')}</span> <span class='small'>{status.get('warning','')}</span></div>
<div class='ai-grid'>
<div class='ai-card'><h3>Puede hacer</h3><p class='small'>Consultar stock/proveedores/recetas, abrir módulos, crear borradores de pedido/merma/producción, importar recetas y guardar documentos en revisión.</p></div>
<div class='ai-card'><h3>No puede hacer solo</h3><p class='small'>Validar albarán, mover stock definitivo, confirmar mermas/producciones, cerrar pedidos, modificar recetas maestras o cambiar proveedores/precios críticos.</p></div>
<div class='ai-card'><h3>Regla central</h3><p class='small'><code>IA propone → System MAC valida → humano confirma</code></p></div>
</div>
<div class='ai-card'><h3>Probar comprensión</h3><p class='small'>Uso técnico controlado: no crea acciones críticas; muestra una respuesta humana y el detalle mínimo de diagnóstico.</p><form id='cmdForm'><input type='hidden' name='center_id' value='{int(center_id or 0)}'><input name='text' style='width:min(680px,100%)' placeholder='Ej.: ¿de qué proveedor es el puerro? / merma de tomate 4 kg'><button class='gold'>Probar</button></form><div id='cmdOut' class='small'></div></div>
<div class='ai-card'><h3>Subir documento a revisión IA</h3><form id='docForm' enctype='multipart/form-data'><input type='hidden' name='center_id' value='{int(center_id or 0)}'><select name='doc_type'><option value='recipe'>Receta</option><option value='albaran'>Albarán</option><option value='invoice'>Factura</option></select><input type='file' name='file' accept='image/*,.pdf'><button class='gold'>Guardar/leer</button></form><div id='docOut' class='small'></div></div>
<div class='ai-card'><h3>Módulos conectados</h3>{''.join(f"<span class='chip'>{k}</span>" for k in caps.get('modules',{}).keys())}</div>
</div><script>
function esc(v){{return String(v||'').replace(/[&<>"']/g,ch=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));}}
function renderHuman(j,out){{
  const er=j.expert_review||{{}}; const item=j.item||{{}}; const msg=j.message||'Sin respuesta.';
  const ok=j.ok?'OK':'Revisión';
  const links=[]; if(j.redirect_url) links.push(['Abrir módulo',j.redirect_url]); if(j.module_url) links.push(['Abrir detalle',j.module_url]);
  out.innerHTML='<div class="ai-card" style="background:rgba(255,255,255,.04)"><h3>'+esc(ok)+' · '+esc(j.intent||j.type||j.status||'Respuesta')+'</h3><p>'+esc(msg)+'</p>'+
    '<p><b>Texto limpio:</b> '+esc(j.normalized_text||'—')+'</p>'+
    '<p><b>Elemento:</b> '+esc(er.main_item||item.name||'—')+' · <b>Cantidad:</b> '+esc(er.qty||'—')+' '+esc(er.unit||'')+' · <b>Confianza:</b> '+esc(Math.round(Number(er.confidence||j.confidence||0)*100))+'%</p>'+
    '<p><b>Siguiente acción:</b> '+esc(j.next_required_action||'Revisar si procede.')+'</p>'+
    (links.length?'<p>'+links.map(l=>'<a class="btn gold" href="'+esc(l[1])+'">'+esc(l[0])+'</a>').join(' ')+'</p>':'')+
    '<details><summary>Diagnóstico técnico</summary><pre>'+esc(JSON.stringify(j,null,2))+'</pre></details></div>';
}}
async function postForm(url, form, out){{ const r=await fetch(url,{{method:'POST',body:new FormData(form)}}); const j=await r.json(); renderHuman(j,out); }}
document.getElementById('cmdForm').addEventListener('submit',e=>{{e.preventDefault();postForm('/api/oido-alfi/command',e.target,document.getElementById('cmdOut'))}});
document.getElementById('docForm').addEventListener('submit',e=>{{e.preventDefault();postForm('/api/oido-alfi/document',e.target,document.getElementById('docOut'))}});
</script></body></html>"""
    return HTMLResponse(html)
