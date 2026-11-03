import os
import time
import logging
from typing import List, Optional
from sqlmodel import Session
from app.models.models import ModelConfig
from google import genai
from google.genai import types
from PIL import Image
import io

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self, session: Session):
        self.session = session
        
    def _get_client(self, model_type: str):
        from app.cruds.crud_config import get_active_config
        config = get_active_config(self.session, model_type)
        
        if not config:
            raise ValueError(f"No active configuration found for {model_type} model.")
            
        if config.provider.lower() == "google":
            # Initialize Google Client
            return genai.Client(api_key=config.api_key), config.model_name
            
        raise NotImplementedError(f"Provider {config.provider} not supported yet.")

    def generate_storyboard(self, system_prompt: str, user_input: str) -> str:
        from app.cruds.crud_config import get_active_config
        config = get_active_config(self.session, "text")
        if not config:
            raise ValueError("No active configuration found for text model.")
        provider = (config.provider or "google").lower()

        user_msg = (f"User Input: {user_input}\n\n"
                    f"Please generate the full storyboard in JSON format as requested.")
        full_prompt = f"{system_prompt}\n\n{user_msg}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if provider == "openai":
                    from openai import OpenAI
                    oai = OpenAI(api_key=config.api_key, base_url=config.base_url or None)
                    resp = oai.chat.completions.create(
                        model=config.model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                    )
                    return resp.choices[0].message.content
                # --- Google (Gemini) default ---
                client = genai.Client(api_key=config.api_key)
                response = client.models.generate_content(
                    model=config.model_name, contents=full_prompt)
                return response.text
            except Exception as e:
                logger.error(f"Error generating storyboard (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise e

    @staticmethod
    def _downscale(image_bytes: bytes, target_px: int) -> bytes:
        """Resize so the longest edge == target_px (never upscales). Returns PNG bytes."""
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if longest <= target_px:
            return image_bytes
        scale = target_px / longest
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _read_replicate_output(item) -> Optional[bytes]:
        """Replicate returns FileOutput objects (have .read()) or URL strings."""
        if item is None:
            return None
        if hasattr(item, "read"):
            return item.read()
        if isinstance(item, (bytes, bytearray)):
            return bytes(item)
        if isinstance(item, str):
            import requests as rq
            r = rq.get(item, timeout=180)
            r.raise_for_status()
            return r.content
        return None

    # Aspect ratios supported by FLUX.2 on Replicate
    _FLUX_AR = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "4:5", "5:4", "21:9", "9:21"}

    def _generate_image_replicate(self, config, prompt, context_images, aspect_ratio, target_px) -> bytes:
        import replicate
        # Ceiling (not the typical time): warm FLUX runs take seconds; this only needs to
        # exceed a cold start (model loading onto a GPU, ~1-3 min) so the read doesn't abort.
        client = replicate.Client(api_token=config.api_key, timeout=180)
        model = config.model_name or "black-forest-labs/flux-2-klein-9b"

        files = []
        if context_images:
            for p in context_images[:5]:  # FLUX accepts up to 5 reference images
                if os.path.exists(p):
                    files.append(open(p, "rb"))

        inp = {"prompt": prompt, "output_format": "png"}
        if files:
            inp["images"] = files
        inp["aspect_ratio"] = aspect_ratio if aspect_ratio in self._FLUX_AR else (
            "match_input_image" if files else "1:1")

        logger.info(f"DEBUG: Replicate run model={model} refs={len(files)} ar={inp['aspect_ratio']}")
        _t0 = time.time()
        try:
            out = None
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    out = client.run(model, input=inp)
                    break
                except Exception as e:
                    msg = str(e).lower()
                    throttled = "429" in msg or "throttled" in msg or "rate limit" in msg
                    transient = any(k in msg for k in (
                        "timed out", "timeout", "connection", "502", "503", "504",
                        "temporarily", "read operation"))
                    if (throttled or transient) and attempt < max_retries - 1:
                        wait = (12 * (attempt + 1)) if throttled else (5 * (attempt + 1))
                        logger.warning(f"Replicate {'throttled' if throttled else 'transient error'} "
                                       f"(attempt {attempt+1}): {e}. Retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                    raise
                finally:
                    for f in files:  # reopen handles are consumed per attempt
                        try:
                            f.seek(0)
                        except Exception:
                            pass
        finally:
            for f in files:
                try:
                    f.close()
                except Exception:
                    pass

        item = out[0] if isinstance(out, (list, tuple)) else out
        data = self._read_replicate_output(item)
        if not data:
            raise RuntimeError("Replicate returned no image data")
        logger.info(f"DEBUG: Replicate image received ({len(data)} bytes) in {time.time() - _t0:.1f}s")
        if target_px:
            data = self._downscale(data, target_px)
        return data

    def generate_image(self, prompt: str, context_images: List[str] = None, aspect_ratio: str = "16:9", resolution: str = "2K") -> bytes:
        from app.cruds.crud_config import get_active_config
        config = get_active_config(self.session, "image")
        if not config:
            raise ValueError("No active configuration found for image model.")
        provider = (config.provider or "google").lower()

        # A numeric resolution (e.g. "500") means generate at the base size and
        # downscale the result so its longest edge matches that pixel target.
        api_size = resolution
        target_px = None
        if resolution not in ("1K", "2K", "4K"):
            digits = "".join(ch for ch in str(resolution) if ch.isdigit())
            if digits:
                target_px = int(digits)
            api_size = "1K"

        if provider == "replicate":
            return self._generate_image_replicate(config, prompt, context_images, aspect_ratio, target_px)

        # --- Google (Gemini) path ---
        client = genai.Client(api_key=config.api_key)
        model_name = config.model_name

        contents = [prompt]
        if context_images:
            for img_path in context_images:
                if os.path.exists(img_path):
                    try:
                        prev_img = Image.open(img_path)
                        contents.append(prev_img)
                    except Exception as e:
                        logger.warning(f"Failed to load context image {img_path}: {e}")
                else:
                    # Log missing context image but don't fail, just skip it
                    logger.warning(f"Warning: Context image not found at {img_path}, skipping.")

        # Retry loop
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"DEBUG: Starting image generation attempt {attempt + 1}/{max_retries} with model {model_name}...")
                logger.info(f"DEBUG: Prompt length: {len(prompt)}")
                if context_images:
                    logger.info(f"DEBUG: Context images count: {len(context_images)}")

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        image_config=types.ImageConfig(
                            aspect_ratio=aspect_ratio,
                            image_size=api_size
                        ),
                    )
                )
                logger.info(f"DEBUG: Generation API call completed for attempt {attempt + 1}")
                
                if response.parts:
                    for part in response.parts:
                        if part.inline_data is not None:
                            image_data = part.inline_data.data
                            if len(image_data) > 0:
                                logger.info(f"DEBUG: Successfully received image data ({len(image_data)} bytes)")
                                if target_px:
                                    image_data = self._downscale(image_data, target_px)
                                return image_data
                            else:
                                logger.warning(f"Warning: Received empty image data on attempt {attempt + 1}")
                
                # Check for text refusal/error
                if response.text:
                    logger.warning(f"Model response text (no image): {response.text}")
                    
                logger.warning(f"Attempt {attempt + 1} failed: No valid image data found in response.")
                if attempt == max_retries - 1:
                    raise ValueError(f"No image found in response after {max_retries} retries. Last response: {response.text if response.text else 'Empty'}")
                
                time.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(f"Error generating image (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise e
        return b""
