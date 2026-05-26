from fastapi import APIRouter, Form, Query, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse

from app.services.operational_quick_service import add_operational_command, update_operational_line, interpret_operational_command, transcribe_audio_bytes, create_missing_article_and_add_to_order

router = APIRouter()


def _url(center_id=0, line_id=0, ok=0, op_type=''):
    u = f"/?page=operativa&center_id={int(center_id or 0)}"
    if line_id:
        u += f"&op_line={int(line_id)}"
    if op_type:
        u += f"&op_type={op_type}"
    if ok:
        u += "&ok=1"
    return u


@router.get('/api/operativa/interpret')
def operativa_interpret(q: str = Query(''), task_mode: str = Query('AUTO')):
    parsed = interpret_operational_command(q, task_mode)
    return JSONResponse(parsed)




@router.post('/api/operativa/transcribe')
async def operativa_transcribe(audio: UploadFile = File(...), task_mode: str = Form('AUTO')):
    data = await audio.read()
    res = transcribe_audio_bytes(data, filename=audio.filename or 'audio.webm', content_type=audio.content_type or 'audio/webm')
    if res.get('ok') and res.get('text'):
        res['parsed'] = interpret_operational_command(res.get('text') or '', task_mode)
    return JSONResponse(res)



@router.post('/api/operativa/create')
def operativa_create_api(center_id: int = Form(0), voice_text: str = Form(''), requested_by: str = Form(''), task_mode: str = Form('AUTO')):
    res = add_operational_command(center_id=center_id, voice_text=voice_text, requested_by=requested_by, source='voice_auto', forced_task_type=task_mode)
    res['redirect_url'] = _url(center_id, res.get('line_id') or 0, 1, res.get('task_type') or '')
    return JSONResponse(res)

@router.post('/operativa/from_voice')
def operativa_from_voice(center_id: int = Form(0), voice_text: str = Form(''), requested_by: str = Form(''), task_mode: str = Form('AUTO')):
    res = add_operational_command(center_id=center_id, voice_text=voice_text, requested_by=requested_by, source='voice', forced_task_type=task_mode)
    return RedirectResponse(_url(center_id, res.get('line_id') or 0, 1, res.get('task_type') or ''), status_code=303)


@router.post('/operativa/line/{line_id}/action')
def operativa_line_action(line_id: int, center_id: int = Form(0), action: str = Form(''), qty_total: str = Form('')):
    q = None
    try:
        if qty_total != '': q = float(str(qty_total).replace(',', '.'))
    except Exception:
        q = None
    update_operational_line(line_id, action, q)
    return RedirectResponse(_url(center_id, line_id, 1), status_code=303)


@router.post('/operativa/create_missing_article')
def operativa_create_missing_article(center_id: int = Form(0), item_name: str = Form(''), qty: str = Form('0'), unit: str = Form('kg'), requested_by: str = Form(''), voice_text: str = Form('')):
    try:
        q = float(str(qty or '0').replace(',', '.'))
    except Exception:
        q = 0.0
    res = create_missing_article_and_add_to_order(center_id=center_id, item_name=item_name, qty=q, unit=unit, requested_by=requested_by, voice_text=voice_text)
    return RedirectResponse(_url(center_id, res.get('line_id') or 0, 1, 'ORDER'), status_code=303)
