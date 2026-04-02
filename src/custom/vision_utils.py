"""Shared vision-preprocessing utilities for embedding models."""

import os
from typing import Union
from urllib.parse import urlparse

import numpy as np
from PIL import Image

# Image file extensions recognised as valid image paths.
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg"}


def is_image_path(path: str) -> bool:
    """Return True if *path* has a recognised image file extension."""
    if path.startswith(("http://", "https://")):
        clean_path = urlparse(path).path
    else:
        clean_path = path
    _, ext = os.path.splitext(clean_path.lower())
    return ext in _IMAGE_EXTENSIONS


def is_video_input(video: object) -> bool:
    """Return True if *video* looks like a single video (path or frame list).

    Semantics:
    - A plain string is treated as a video file path.
    - A list whose first element is a PIL Image is treated as a video frame sequence.
    - A list whose first element is a string that is *not* an image path is treated
      as a list of video file paths (each element is one video).
    - A list whose first element is an image path is treated as an image list,
      so this function returns False.
    """
    if isinstance(video, str):
        return True
    if isinstance(video, list) and len(video) > 0:
        first = video[0]
        if isinstance(first, Image.Image):
            return True  # list of PIL frames → single video
        if isinstance(first, str):
            # image paths → NOT a video input
            return not is_image_path(first)
    return False


def sample_frames(
    frames: list[Union[str, Image.Image]], max_segments: int
) -> list[Union[str, Image.Image]]:
    """Uniformly sample up to *max_segments* frames from *frames*."""
    duration = len(frames)
    if duration <= max_segments:
        return frames
    indices = np.linspace(0, duration - 1, max_segments, dtype=int).tolist()
    return [frames[i] for i in indices]
