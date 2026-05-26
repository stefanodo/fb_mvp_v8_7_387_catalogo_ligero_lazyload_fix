from __future__ import annotations
import os, logging
from pathlib import Path
from typing import Optional
from .ai_provider_service import RecipeAIService, RecipeAIConfig
from .prompts import build_voice_cleanup_prompt
from .models import ImportedRecipeDraft
from app.services.operational_quick_service import force_spanish_operational_text

logger = logging.getLogger(__name__)

class RecipeVoiceConfig:
    provider: str = os.environ.get("RECIPE_VOICE_PROVIDER", "openai").lower()
    stt_model: str = os.environ.get("RECIPE_VOICE_STT_MODEL", "gpt-4o-transcribe")
    tts_model: str = os.environ.get("RECIPE_VOICE_TTS_MODEL", "gpt-4o-mini-tts")
    voice_name: str = os.environ.get("RECIPE_VOICE_NAME", "alloy")
    cleanup_model: str = os.environ.get("RECIPE_VOICE_CLEANUP_MODEL", os.environ.get("RECIPE_AI_TEXT_MODEL", "gpt-4o"))
    max_audio_mb: int = int(os.environ.get("RECIPE_VOICE_MAX_AUDIO_MB", "25"))

class VoiceSessionStatus:
    BORRADOR_GENERADO = "BORRADOR_GENERADO"
    ERROR_AUDIO = "ERROR_AUDIO"

class VoiceRecipeResult:
    def __init__(self, transcribed_text: str, cleaned_text: str, draft: Optional[ImportedRecipeDraft], assistant_text: str, audio_response_path: Optional[str], status: str, warnings: Optional[list[str]] = None):
        self.transcribed_text, self.cleaned_text, self.draft, self.assistant_text, self.audio_response_path, self.status, self.warnings = transcribed_text, cleaned_text, draft, assistant_text, audio_response_path, status, warnings or []
    def to_dict(self) -> dict:
        return {"transcribed_text": self.transcribed_text, "cleaned_text": self.cleaned_text, "draft": self.draft.to_dict() if self.draft else None, "assistant_text": self.assistant_text, "audio_response_path": self.audio_response_path, "status": self.status, "warnings": self.warnings}

class RecipeVoiceService:
    def __init__(self, catalog_items: Optional[list[dict]] = None, subrecipes: Optional[list[dict]] = None, voice_config: Optional[RecipeVoiceConfig] = None, ai_config: Optional[RecipeAIConfig] = None):
        self.voice_config = voice_config or RecipeVoiceConfig()
        self.recipe_ai_service = RecipeAIService(catalog_items or [], subrecipes or [], ai_config or RecipeAIConfig())
        self._openai_client = None
    def _openai_or_raise(self):
        if not os.environ.get("OPENAI_API_KEY"): raise EnvironmentError("OPENAI_API_KEY no configurada para voz.")
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return self._openai_client
    def validate_audio_file(self, audio_path: str) -> None:
        p = Path(audio_path)
        if not p.exists(): raise FileNotFoundError(f"Audio no encontrado: {audio_path}")
        if p.stat().st_size <= 0: raise ValueError("El archivo de audio está vacío.")
        if p.stat().st_size > self.voice_config.max_audio_mb * 1024 * 1024: raise ValueError("Audio demasiado grande.")
        if p.suffix.lower() not in {".mp3",".mp4",".mpeg",".mpga",".m4a",".wav",".webm",".ogg"}: raise ValueError(f"Formato de audio no soportado: {p.suffix}")
    def transcribe_audio(self, audio_path: str) -> str:
        self.validate_audio_file(audio_path)
        client = self._openai_or_raise()
        prompt = (
            "IDIOMA OBLIGATORIO: español. Transcribe una receta o instrucción de cocina/restaurante. "
            "No traduzcas al inglés. Mantén nombres de ingredientes y elaboraciones en español. "
            "Contexto: receta, ingredientes, elaboración, rendimiento, merma, alérgenos, pico de gallo, tomate, puerro, cebolla, cilantro. "
            "No inventes cantidades ni pasos."
        )
        with open(audio_path, "rb") as f:
            try:
                transcript = client.audio.transcriptions.create(model=self.voice_config.stt_model, file=f, language="es", prompt=prompt)
            except TypeError:
                transcript = client.audio.transcriptions.create(model=self.voice_config.stt_model, file=f)
        text = getattr(transcript, "text", None)
        if not text: raise ValueError("La transcripción no devolvió texto.")
        return force_spanish_operational_text(text.strip())
    def cleanup_voice_text(self, transcribed_text: str) -> str:
        text = (transcribed_text or "").strip()
        if not text: return ""
        client = self._openai_or_raise()
        r = client.responses.create(model=self.voice_config.cleanup_model, input=[{"role":"system","content":build_voice_cleanup_prompt()},{"role":"user","content":text}], max_output_tokens=2048)
        return (getattr(r, "output_text", "") or text).strip()
    def build_assistant_voice_text(self, draft: Optional[ImportedRecipeDraft]) -> str:
        if draft is None: return "No pude generar el borrador de receta. Puedes revisar el audio o escribir la receta manualmente."
        pending = sum(1 for i in draft.ingredients if i.is_critical_pending())
        text = f"He detectado la receta {draft.recipe_name}. Tiene {len(draft.ingredients)} ingredientes."
        if draft.yield_quantity and draft.yield_unit: text += f" El rendimiento indicado es {draft.yield_quantity} {draft.yield_unit}."
        text += f" Hay {pending} datos pendientes de revisión." if pending else " No veo pendientes críticos."
        return text + " ¿Quieres revisar ingredientes, corregir algo o guardar el borrador?"
    def text_to_speech(self, text: str, output_path: str) -> Optional[str]:
        if not text: return None
        try:
            client = self._openai_or_raise()
            out = Path(output_path); out.parent.mkdir(parents=True, exist_ok=True)
            with client.audio.speech.with_streaming_response.create(model=self.voice_config.tts_model, voice=self.voice_config.voice_name, input=text) as response:
                response.stream_to_file(str(out))
            return str(out)
        except Exception as exc:
            logger.warning("No se pudo generar respuesta de voz: %s", exc); return None
    def import_recipe_from_audio(self, audio_path: str, created_by: Optional[str] = None, response_audio_path: Optional[str] = None) -> VoiceRecipeResult:
        warnings = []
        try: transcribed = self.transcribe_audio(audio_path)
        except Exception as exc: return VoiceRecipeResult("", "", None, "No pude transcribir el audio. Puedes intentarlo de nuevo o escribir la receta manualmente.", None, VoiceSessionStatus.ERROR_AUDIO, [str(exc)])
        try: cleaned = self.cleanup_voice_text(transcribed)
        except Exception as exc: cleaned = transcribed; warnings.append(f"No se pudo limpiar la transcripción: {exc}")
        try: draft = self.recipe_ai_service.import_from_voice_text(cleaned, created_by)
        except Exception as exc: draft = None; warnings.append(f"No se pudo generar borrador desde voz: {exc}")
        assistant = self.build_assistant_voice_text(draft)
        audio = self.text_to_speech(assistant, response_audio_path) if response_audio_path else None
        return VoiceRecipeResult(transcribed, cleaned, draft, assistant, audio, VoiceSessionStatus.BORRADOR_GENERADO if draft else VoiceSessionStatus.ERROR_AUDIO, warnings)
