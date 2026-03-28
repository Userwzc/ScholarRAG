import torch
import torch.nn.functional as F
import unicodedata

from dataclasses import dataclass
from typing import Optional, List, Union, Dict, Any
from PIL import Image
from transformers.models.qwen3_vl.modeling_qwen3_vl import (
    Qwen3VLPreTrainedModel,
    Qwen3VLModel,
    Qwen3VLConfig,
)
from transformers.models.qwen3_vl.processing_qwen3_vl import Qwen3VLProcessor
from transformers.modeling_outputs import ModelOutput
from transformers.processing_utils import Unpack
from transformers.utils import TransformersKwargs
from transformers.cache_utils import Cache

from src.utils.logger import get_logger
from .qwen3_vl_base import (
    Qwen3VLBase,
    MIN_PIXELS,
    MAX_PIXELS,
    MAX_TOTAL_PIXELS,
    FPS,
    MAX_FRAMES,
)

logger = get_logger(__name__)

# Embedding-specific constants
MAX_LENGTH = 8192
PAD_TOKEN = "<|endoftext|>"


# Define output structure for embeddings
@dataclass
class Qwen3VLForEmbeddingOutput(ModelOutput):
    last_hidden_state: Optional[torch.FloatTensor] = None
    attention_mask: Optional[torch.Tensor] = None


# Define model class to compute embeddings
class Qwen3VLForEmbedding(Qwen3VLPreTrainedModel):
    _checkpoint_conversion_mapping = {}
    accepts_loss_kwargs = False
    config: Qwen3VLConfig

    def __init__(self, config):
        super().__init__(config)
        self.model = Qwen3VLModel(config)
        self.post_init()

    def get_input_embeddings(self):
        return self.model.get_input_embeddings()

    def set_input_embeddings(self, value):
        self.model.set_input_embeddings(value)

    def set_decoder(self, decoder):
        self.model.set_decoder(decoder)

    def get_decoder(self):
        return self.model.get_decoder()

    # Extract video features from model
    def get_video_features(
        self,
        pixel_values_videos: torch.FloatTensor,
        video_grid_thw: Optional[torch.LongTensor] = None,
    ):
        return self.model.get_video_features(pixel_values_videos, video_grid_thw)

    # Extract image features from model
    def get_image_features(
        self,
        pixel_values: torch.FloatTensor,
        image_grid_thw: Optional[torch.LongTensor] = None,
    ):
        return self.model.get_image_features(pixel_values, image_grid_thw)

    # Make modules accessible through properties
    @property
    def language_model(self):
        return self.model.language_model

    @property
    def visual(self):
        return self.model.visual

    # Forward pass through model with input parameters
    # @check_model_inputs
    def forward(
        self,
        input_ids: torch.LongTensor = None,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.LongTensor] = None,
        past_key_values: Optional[Cache] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        pixel_values: Optional[torch.Tensor] = None,
        pixel_values_videos: Optional[torch.FloatTensor] = None,
        image_grid_thw: Optional[torch.LongTensor] = None,
        video_grid_thw: Optional[torch.LongTensor] = None,
        cache_position: Optional[torch.LongTensor] = None,
        logits_to_keep: Union[int, torch.Tensor] = 0,
        **kwargs: Unpack[TransformersKwargs],
    ) -> Union[tuple, Qwen3VLForEmbeddingOutput]:
        # Pass inputs through the model
        outputs = self.model(
            input_ids=input_ids,
            pixel_values=pixel_values,
            pixel_values_videos=pixel_values_videos,
            image_grid_thw=image_grid_thw,
            video_grid_thw=video_grid_thw,
            position_ids=position_ids,
            attention_mask=attention_mask,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            cache_position=cache_position,
            **kwargs,
        )
        # Return the model output
        return Qwen3VLForEmbeddingOutput(
            last_hidden_state=outputs.last_hidden_state,
            attention_mask=attention_mask,
        )


# Define embedder class for processing inputs and generating embeddings
class Qwen3VLEmbedder(Qwen3VLBase):
    """Qwen3-VL embedding model wrapper.

    Inherits shared pixel/frame configuration, token truncation,
    multimodal normalisation, and vision-info error handling from
    ``Qwen3VLBase``.
    """

    def __init__(
        self,
        model_name_or_path: str,
        max_length: int = MAX_LENGTH,
        min_pixels: int = MIN_PIXELS,
        max_pixels: int = MAX_PIXELS,
        total_pixels: int = MAX_TOTAL_PIXELS,
        fps: float = FPS,
        max_frames: int = MAX_FRAMES,
        default_instruction: str = "Represent the user's input.",
        **kwargs,
    ):
        super().__init__(
            min_pixels=min_pixels,
            max_pixels=max_pixels,
            total_pixels=total_pixels,
            fps=fps,
            max_frames=max_frames,
            default_instruction=default_instruction,
        )

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length

        self.model = Qwen3VLForEmbedding.from_pretrained(
            model_name_or_path, trust_remote_code=True, **kwargs
        ).to(device)
        self.processor = Qwen3VLProcessor.from_pretrained(  # nosec B615: Model path is user-configurable; revision pinning is optional
            model_name_or_path, padding_side="right"
        )
        self.model.eval()

    @torch.no_grad()
    def forward(self, inputs: Dict[str, Any]) -> Dict[str, torch.Tensor]:
        outputs = self.model(**inputs)
        return {
            "last_hidden_state": outputs.last_hidden_state,
            "attention_mask": inputs.get("attention_mask"),
        }

    def format_model_input(
        self,
        text: Optional[Union[List[str], str]] = None,
        image: Optional[Union[List[Union[str, Image.Image]], str, Image.Image]] = None,
        video: Optional[
            Union[
                List[Union[str, List[Union[str, Image.Image]]]],
                str,
                List[Union[str, Image.Image]],
            ]
        ] = None,
        instruction: Optional[str] = None,
        fps: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> List[Dict]:
        # Ensure instruction ends with punctuation
        if instruction:
            instruction = instruction.strip()
            if instruction and not unicodedata.category(instruction[-1]).startswith(
                "P"
            ):
                instruction = instruction + "."

        # Build conversation skeleton
        content: List[Dict] = []
        conversation = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": instruction or self.default_instruction}
                ],
            },
            {"role": "user", "content": content},
        ]

        # Normalise inputs via base class
        texts, images, videos = self._normalize_multimodal(text, image, video)

        if not texts and not images and not videos:
            content.append({"type": "text", "text": "NULL"})
            return conversation

        # Build media content (video + image dicts) via base class
        content.extend(self._build_media_content(images, videos, fps, max_frames))

        # Append text entries
        for txt in texts:
            content.append({"type": "text", "text": txt})

        return conversation

    def _preprocess_inputs(
        self, conversations: List[List[Dict]]
    ) -> Dict[str, torch.Tensor]:
        text = self.processor.apply_chat_template(
            conversations, add_generation_prompt=True, tokenize=False
        )

        images, video_inputs, video_kwargs, text_override = (
            self._safe_process_vision_info(conversations, self.processor)
        )
        if text_override:
            text = text_override

        if video_inputs is not None:
            videos, video_metadata = zip(*video_inputs)
            videos = list(videos)
            video_metadata = list(video_metadata)
        else:
            videos, video_metadata = None, None

        inputs = self.processor(
            text=text,
            images=images,
            videos=videos,
            video_metadata=video_metadata,
            truncation=True,
            max_length=self.max_length,
            padding=True,
            do_resize=False,
            return_tensors="pt",
            **video_kwargs,
        )
        return inputs

    @staticmethod
    def _pooling_last(
        hidden_state: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        """Pool the last non-padding hidden state for each sequence."""
        flipped_tensor = attention_mask.flip(dims=[1])
        last_one_positions = flipped_tensor.argmax(dim=1)
        col = attention_mask.shape[1] - last_one_positions - 1
        row = torch.arange(hidden_state.shape[0], device=hidden_state.device)
        return hidden_state[row, col]

    def process(
        self, inputs: List[Dict[str, Any]], normalize: bool = True, batch_size: int = 4
    ) -> torch.Tensor:
        """Process inputs in batches and return normalised embedding tensors."""
        all_embeddings = []

        for i in range(0, len(inputs), batch_size):
            batch_inputs = inputs[i : i + batch_size]

            conversations = [
                self.format_model_input(
                    text=ele.get("text"),
                    image=ele.get("image"),
                    video=ele.get("video"),
                    instruction=ele.get("instruction"),
                    fps=ele.get("fps"),
                    max_frames=ele.get("max_frames"),
                )
                for ele in batch_inputs
            ]

            processed_inputs = self._preprocess_inputs(conversations)
            processed_inputs = {
                k: v.to(self.model.device) for k, v in processed_inputs.items()
            }

            outputs = self.forward(processed_inputs)
            batch_embeddings = self._pooling_last(
                outputs["last_hidden_state"], outputs["attention_mask"]
            )

            if normalize:
                batch_embeddings = F.normalize(batch_embeddings, p=2, dim=-1)

            all_embeddings.append(batch_embeddings)
            torch.cuda.empty_cache()

        return torch.cat(all_embeddings, dim=0)
