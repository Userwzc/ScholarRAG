import torch
from PIL import Image
from typing import List, Union, Optional, Dict
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

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

# Reranker-specific max length (longer than embedding to handle query+doc pairs)
MAX_LENGTH = 10240


class Qwen3VLReranker(Qwen3VLBase):
    """Qwen3-VL reranker model wrapper.

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
        default_instruction: str = "Given a search query, retrieve relevant candidates that answer the query.",
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

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length

        # Load the language model
        lm = Qwen3VLForConditionalGeneration.from_pretrained(
            model_name_or_path, trust_remote_code=True, **kwargs
        ).to(self.device)

        self.model = lm.model
        self.processor = AutoProcessor.from_pretrained(
            model_name_or_path, trust_remote_code=True, padding_side="left"
        )
        self.model.eval()

        # Initialize binary classification head for yes/no scoring
        token_true_id = self.processor.tokenizer.get_vocab()["yes"]
        token_false_id = self.processor.tokenizer.get_vocab()["no"]
        self.score_linear = self.get_binary_linear(lm, token_true_id, token_false_id)
        self.score_linear.eval()
        self.score_linear.to(self.device).to(self.model.dtype)

    def get_binary_linear(
        self, model, token_yes: int, token_no: int
    ) -> torch.nn.Linear:
        lm_head_weights = model.lm_head.weight.data

        weight_yes = lm_head_weights[token_yes]
        weight_no = lm_head_weights[token_no]

        D = weight_yes.size()[0]
        linear_layer = torch.nn.Linear(D, 1, bias=False)
        with torch.no_grad():
            linear_layer.weight[0] = weight_yes - weight_no
        return linear_layer

    @torch.no_grad()
    def compute_scores(self, inputs: Dict) -> List[float]:
        batch_scores = self.model(**inputs).last_hidden_state[:, -1]
        scores = self.score_linear(batch_scores)
        scores = torch.sigmoid(scores).squeeze(-1).cpu().detach().tolist()
        return scores

    def tokenize(self, pairs: List[Dict], **kwargs) -> Dict:
        max_length = self.max_length
        text = self.processor.apply_chat_template(
            pairs, tokenize=False, add_generation_prompt=True
        )

        images, video_inputs, video_kwargs, text_override = (
            self._safe_process_vision_info(pairs, self.processor)
        )
        if text_override:
            text = text_override

        if video_inputs is not None:
            videos, video_metadatas = zip(*video_inputs)
            videos, video_metadatas = list(videos), list(video_metadatas)
        else:
            videos = None
            video_metadatas = None

        inputs = self.processor(
            text=text,
            images=images,
            videos=videos,
            video_metadata=video_metadatas,
            truncation=False,
            padding=False,
            do_resize=False,
            **video_kwargs,
        )

        # Truncate input IDs while preserving special tokens.
        # The last GENERATION_SUFFIX_LEN tokens are the assistant-turn prefix
        # added by add_generation_prompt=True (e.g. "<|im_start|>assistant\n").
        # We truncate only the body, then re-append the suffix.
        GENERATION_SUFFIX_LEN = 5
        special_ids = set(self.processor.tokenizer.all_special_ids)
        for i, ele in enumerate(inputs["input_ids"]):
            inputs["input_ids"][i] = (
                self._truncate_tokens(
                    ele[:-GENERATION_SUFFIX_LEN],
                    max_length,
                    special_ids,
                )
                + ele[-GENERATION_SUFFIX_LEN:]
            )

        # Apply padding
        temp_inputs = self.processor.tokenizer.pad(
            {"input_ids": inputs["input_ids"]},
            padding=True,
            return_tensors="pt",
            max_length=self.max_length,
        )
        for key in temp_inputs:
            inputs[key] = temp_inputs[key]

        return inputs

    def format_mm_content(
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
        prefix: str = "Query:",
        fps: Optional[float] = None,
        max_frames: Optional[int] = None,
    ) -> List[Dict]:
        content: List[Dict] = [{"type": "text", "text": prefix}]

        # Normalise inputs via base class
        texts, images, videos = self._normalize_multimodal(text, image, video)

        if not texts and not images and not videos:
            content.append({"type": "text", "text": "NULL"})
            return content

        # Build media content (video + image dicts) via base class
        content.extend(self._build_media_content(images, videos, fps, max_frames))

        # Append text entries
        for txt in texts:
            content.append({"type": "text", "text": txt})

        return content

    def format_mm_instruction(
        self,
        query_text: Optional[Union[str, tuple]] = None,
        query_image: Optional[
            Union[List[Union[str, Image.Image]], str, Image.Image]
        ] = None,
        query_video: Optional[
            Union[
                List[Union[str, List[Union[str, Image.Image]]]],
                str,
                List[Union[str, Image.Image]],
            ]
        ] = None,
        doc_text: Optional[Union[List[str], str]] = None,
        doc_image: Optional[
            Union[List[Union[str, Image.Image]], str, Image.Image]
        ] = None,
        doc_video: Optional[
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
        result = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": 'Judge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".',
                    }
                ],
            }
        ]

        # Handle query_text as tuple containing (instruction, text)
        if isinstance(query_text, tuple):
            instruct, query_text = query_text
        else:
            instruct = instruction

        contents: List[Dict] = [
            {
                "type": "text",
                "text": "<Instruct>: " + (instruct or self.default_instruction),
            }
        ]

        # Format query content
        contents.extend(
            self.format_mm_content(
                query_text,
                query_image,
                query_video,
                prefix="<Query>:",
                fps=fps,
                max_frames=max_frames,
            )
        )

        # Format document content
        contents.extend(
            self.format_mm_content(
                doc_text,
                doc_image,
                doc_video,
                prefix="\n<Document>:",
                fps=fps,
                max_frames=max_frames,
            )
        )

        result.append({"role": "user", "content": contents})
        return result

    def process(self, inputs: Dict) -> List[float]:
        """Score query-document pairs and return a list of relevance scores."""
        instruction = inputs.get("instruction", self.default_instruction)

        query = inputs.get("query", {})
        documents = inputs.get("documents", [])

        if not query or not documents:
            return []

        # Format each query-document pair
        pairs = [
            self.format_mm_instruction(
                query.get("text", None),
                query.get("image", None),
                query.get("video", None),
                document.get("text", None),
                document.get("image", None),
                document.get("video", None),
                instruction=instruction,
                fps=inputs.get("fps", self.fps),
                max_frames=inputs.get("max_frames", self.max_frames),
            )
            for document in documents
        ]

        # Tokenize all pairs in a single batch and score together.
        # This is significantly more efficient than one-at-a-time scoring.
        tokenized_inputs = self.tokenize(pairs)
        tokenized_inputs = {
            k: v.to(self.model.device) for k, v in tokenized_inputs.items()
        }
        return self.compute_scores(tokenized_inputs)
