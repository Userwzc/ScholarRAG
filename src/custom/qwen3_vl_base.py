"""Base class for Qwen3-VL embedding models.

Provides:
- Shared pixel / frame configuration constants (IMAGE_BASE_FACTOR … MAX_TOTAL_PIXELS).
- ``_truncate_tokens`` — special-token-preserving truncation (static method).
- ``_normalize_multimodal`` — normalise text/image/video to typed lists.
- ``_build_media_content`` — convert normalised lists to Qwen-VL content dicts.
- ``_safe_process_vision_info`` — wraps ``process_vision_info`` with a NULL fallback.

Subclasses define their own ``MAX_LENGTH`` and implement task-specific inference logic.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union

from PIL import Image

from src.utils.logger import get_logger
from .vision_utils import is_video_input, sample_frames

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared pixel / frame constants
# These values are used by the embedder.
# MAX_LENGTH is left for subclasses to define.
# ---------------------------------------------------------------------------

IMAGE_BASE_FACTOR: int = 16
IMAGE_FACTOR: int = IMAGE_BASE_FACTOR * 2
MIN_PIXELS: int = 4 * IMAGE_FACTOR * IMAGE_FACTOR
MAX_PIXELS: int = 1800 * IMAGE_FACTOR * IMAGE_FACTOR
FPS: float = 1
MAX_FRAMES: int = 64
FRAME_MAX_PIXELS: int = 768 * IMAGE_FACTOR * IMAGE_FACTOR
MAX_TOTAL_PIXELS: int = 10 * FRAME_MAX_PIXELS

# Type alias for a single video: either a file-path string or a list of frames.
_VideoInput = Union[str, List[Union[str, Image.Image]]]


class Qwen3VLBase:
    """Mixin base carrying shared configuration and stateless helpers.

    Subclasses must call ``super().__init__()`` and may override any of the
    configuration attributes before their own ``__init__`` logic runs.
    """

    def __init__(
        self,
        min_pixels: int = MIN_PIXELS,
        max_pixels: int = MAX_PIXELS,
        total_pixels: int = MAX_TOTAL_PIXELS,
        fps: float = FPS,
        max_frames: int = MAX_FRAMES,
        default_instruction: str = "Represent the user's input.",
    ) -> None:
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.total_pixels = total_pixels
        self.fps = fps
        self.max_frames = max_frames
        self.default_instruction = default_instruction

    # ------------------------------------------------------------------
    # Token truncation
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_tokens(
        token_ids: List[int],
        max_length: int,
        special_token_ids: set,
    ) -> List[int]:
        """Truncate *token_ids* to *max_length* preserving all special tokens.

        Non-special tokens are dropped from the interior of the sequence until
        the total length fits within *max_length*.  Special tokens (e.g. BOS,
        EOS, image placeholders) are always retained so the model receives a
        structurally valid input.
        """
        if len(token_ids) <= max_length:
            return token_ids

        num_special = sum(1 for t in token_ids if t in special_token_ids)
        num_non_special_to_keep = max_length - num_special

        final: List[int] = []
        kept = 0
        for t in token_ids:
            if t in special_token_ids:
                final.append(t)
            elif kept < num_non_special_to_keep:
                final.append(t)
                kept += 1
        return final

    # ------------------------------------------------------------------
    # Multimodal input normalisation
    # ------------------------------------------------------------------

    def _normalize_multimodal(
        self,
        text: Optional[Union[List[str], str]],
        image: Optional[Union[List[Union[str, Image.Image]], str, Image.Image]],
        video: Optional[
            Union[
                List[Union[str, List[Union[str, Image.Image]]]],
                str,
                List[Union[str, Image.Image]],
            ]
        ],
    ) -> tuple:
        """Normalise text / image / video arguments to typed ``List``s.

        Returns ``(texts, images, videos)`` where each element is guaranteed
        to be a ``list`` (possibly empty).
        """
        # ---- text ----
        if text is None:
            texts: List[str] = []
        elif isinstance(text, str):
            texts = [text]
        else:
            texts = list(text)

        # ---- image ----
        if image is None:
            images: List[Union[str, Image.Image]] = []
        elif not isinstance(image, list):
            images = [image]
        else:
            images = list(image)

        # ---- video ----
        if video is None:
            videos: List[_VideoInput] = []
        elif is_video_input(video):
            videos = [video]  # type: ignore[list-item]
        else:
            videos = list(video)  # type: ignore[arg-type]

        return texts, images, videos

    # ------------------------------------------------------------------
    # Media content dict construction
    # ------------------------------------------------------------------

    def _build_media_content(
        self,
        images: List[Union[str, Image.Image]],
        videos: List[_VideoInput],
        fps: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> List[dict]:
        """Convert normalised image/video lists to Qwen-VL content dicts.

        Returns a flat list of content dicts ready to be inserted into a
        conversation message.  Text entries are NOT included here — callers
        append them separately so they can control ordering.
        """
        content: List[dict] = []

        for vid in videos:
            video_content: Any = None
            video_kwargs: dict = {"total_pixels": self.total_pixels}

            if isinstance(vid, list):
                # Frame sequence
                frames: List[Union[str, Image.Image]] = vid
                if self.max_frames is not None:
                    frames = sample_frames(frames, max_frames or self.max_frames)
                video_content = [
                    ("file://" + f if isinstance(f, str) else f) for f in frames
                ]
            elif isinstance(vid, str):
                video_content = (
                    vid if vid.startswith(("http://", "https://")) else "file://" + vid
                )
                video_kwargs = {
                    "fps": fps or self.fps,
                    "max_frames": max_frames or self.max_frames,
                }
            else:
                raise TypeError("Unrecognised video type: %s" % type(vid))

            if video_content:
                content.append(
                    {"type": "video", "video": video_content, **video_kwargs}
                )

        for img in images:
            image_content: Any = None

            if isinstance(img, Image.Image):
                image_content = img
            elif isinstance(img, str):
                image_content = (
                    img if img.startswith(("http://", "https://")) else "file://" + img
                )
            else:
                raise TypeError("Unrecognised image type: %s" % type(img))

            if image_content:
                content.append(
                    {
                        "type": "image",
                        "image": image_content,
                        "min_pixels": self.min_pixels,
                        "max_pixels": self.max_pixels,
                    }
                )

        return content

    # ------------------------------------------------------------------
    # process_vision_info safe wrapper
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_process_vision_info(
        conversations: Any,
        processor: Any,
    ) -> tuple:
        """Call ``process_vision_info`` and return a NULL fallback on error.

        Returns ``(images, video_inputs, video_kwargs, text_override)`` where
        ``text_override`` is non-empty only when the fallback is triggered.
        """
        from qwen_vl_utils.vision_process import process_vision_info

        try:
            images, video_inputs, video_kwargs = process_vision_info(
                conversations,
                image_patch_size=16,
                return_video_metadata=True,
                return_video_kwargs=True,
            )
            return images, video_inputs, video_kwargs, ""
        except Exception as exc:
            logger.error("Error in processing vision info: %s", exc)
            null_text: str = processor.apply_chat_template(
                [{"role": "user", "content": [{"type": "text", "text": "NULL"}]}],
                add_generation_prompt=True,
                tokenize=False,
            )
            return None, None, {"do_sample_frames": False}, null_text
