"""Qwen3-VL 多模态嵌入模型，符合 LangChain Embeddings 接口。

支持混合输入（text + image），统一通过 str 或 dict 格式传入。
"""

import asyncio
from typing import Union

from langchain_core.embeddings import Embeddings

from src.custom.qwen3_vl_embedding import Qwen3VLEmbedder


class Qwen3VLEmbeddings(Embeddings):
    """Qwen3-VL 多模态嵌入模型，符合 LangChain Embeddings 接口。

    支持混合输入（text + image），统一通过 str 或 dict 格式传入。

    Examples:
        纯文本嵌入：
            embed_query("什么是机器学习？")
            embed_documents(["文本1", "文本2"])

        图片嵌入：
            embed_query({"image": "/path/to/image.jpg"})
            embed_documents([{"image": "/path/to/img1.jpg"}, {"image": "/path/to/img2.jpg"}])

        混合嵌入：
            embed_query({"text": "描述文字", "image": "/path/to/image.jpg"})
            embed_documents([
                {"text": "纯文本"},
                {"image": "/path/to/image.jpg"},
                {"text": "图文混合", "image": "/path/to/another.jpg"}
            ])
    """

    def __init__(
        self,
        model_name_or_path: str = "../models/Qwen3-VL-Embedding-2B",
        **kwargs,
    ):
        """初始化 Qwen3-VL 嵌入模型。

        Args:
            model_name_or_path: 模型路径或 HuggingFace 模型 ID
            **kwargs: 传递给 Qwen3VLEmbedder 的额外参数
        """
        self.model = Qwen3VLEmbedder(model_name_or_path=model_name_or_path, **kwargs)

    def _normalize_input(self, input: Union[str, dict]) -> dict:
        """将输入标准化为 Qwen3VL 所需的 dict 格式。

        Args:
            input: 纯文本字符串或已格式化的 dict

        Returns:
            标准化后的 dict，包含 text、image 等键
        """
        if isinstance(input, str):
            return {"text": input}
        return input

    def embed_documents(
        self,
        inputs: list[Union[str, dict]],
        instruction: str = None,
    ) -> list[list[float]]:
        """批量嵌入文档（支持混合输入）。

        Args:
            inputs: 字符串或 dict 的列表，dict 格式：
                - {"text": "描述文本"}
                - {"image": "/path/to/image.jpg"}
                - {"text": "描述", "image": "/path/to/image.jpg"}
                - {"text": "...", "image": "...", "video": "..."}  (支持视频)
            instruction: 可选嵌入指令，应用于所有输入

        Returns:
            嵌入向量列表，每个向量为 list[float]
        """
        normalized = [self._normalize_input(inp) for inp in inputs]
        if instruction:
            for item in normalized:
                item["instruction"] = instruction
        embeddings = self.model.process(normalized)
        return embeddings.tolist()

    def embed_query(
        self,
        input: Union[str, dict],
        instruction: str = "Retrieve images or text relevant to the user's query.",
    ) -> list[float]:
        """嵌入单个查询（支持混合输入）。

        Args:
            input: 纯文本字符串，或 dict 格式：
                - {"text": "描述文本"}
                - {"image": "/path/to/image.jpg"}
                - {"text": "描述", "image": "/path/to/image.jpg"}
                - {"text": "...", "image": "...", "video": "..."}  (支持视频)
            instruction: 嵌入指令，默认为检索指令

        Returns:
            嵌入向量 list[float]
        """
        normalized = self._normalize_input(input)
        normalized["instruction"] = instruction
        embeddings = self.model.process([normalized])
        return embeddings.tolist()[0]

    async def aembed_documents(
        self,
        inputs: list[Union[str, dict]],
        instruction: str = None,
    ) -> list[list[float]]:
        """异步版本的 embed_documents。

        使用线程池执行同步的嵌入操作，避免阻塞事件循环。
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.embed_documents, inputs, instruction
        )

    async def aembed_query(self, input: Union[str, dict]) -> list[float]:
        """异步版本的 embed_query。

        使用线程池执行同步的嵌入操作，避免阻塞事件循环。
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, input)
