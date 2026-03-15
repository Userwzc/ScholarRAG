import os
import re
import json
import tiktoken
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_text_splitters import MarkdownTextSplitter
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from mineru.cli.common import do_parse, read_fn

    MINERU_AVAILABLE = True
except ImportError:
    do_parse = None  # type: ignore[assignment]
    read_fn = None  # type: ignore[assignment]
    MINERU_AVAILABLE = False
    logger.warning(
        "mineru package not fully installed or configured. Using mock parser for skeleton execution."
    )
    logger.warning("Ensure you have Python >= 3.10 and installed 'mineru'.")

# 参考文献节标题的常见写法
_REFERENCE_HEADINGS = frozenset(
    [
        "REFERENCES",
        "REFERENCE",
        "BIBLIOGRAPHY",
        "WORKS CITED",
        "LITERATURE CITED",
        "CITED LITERATURE",
    ]
)

# 正文开始的常见标题关键词
_MAIN_CONTENT_HEADINGS = frozenset(
    [
        "ABSTRACT",
        "INTRODUCTION",
        "SUMMARY",
        "OVERVIEW",
    ]
)

# 提取前导章节编号，如 "4", "4.1", "4.1.1"（允许编号后直接跟文字，无需空格）
_SECTION_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)")

# 疑似内联子标题：如 "5.1.3 Compared baselines."
_INLINE_SUBHEADING_RE = re.compile(
    r"^(\d+(\.\d+)+\s*[^.\n?]{1,150}?[.?!])(.*)$", flags=re.DOTALL
)

# 仅匹配行尾连字符断词（连字符后紧跟空白符），用于拼接跨行单词
_EOL_HYPHEN_RE = re.compile(r"-\s+")


def _merge_hyphen_lines(lines: List[str]) -> str:
    """将多行文本合并，并修复行尾连字符造成的断词。

    例：["state-of-the-", "art method"] → "state-of-the-art method"
    注意：仅去除行末连字符后的空白，保留词中连字符（如 "self-attention"）。
    """
    result = ""
    for i, line in enumerate(lines):
        if i == 0:
            result = line
        elif result.endswith("-"):
            # 行尾是连字符：直接拼接（去掉连字符后的空白）
            result = result + line.lstrip()
        else:
            result = result + " " + line
    return result


class MinerUParser:
    """
    Parser utilizing local MinerU to extract text, figures, and structured data
    from Research PDF papers.
    """

    def __init__(
        self, output_dir: str = "./output", backend: str = "hybrid-auto-engine"
    ):
        self.output_dir = output_dir
        self.backend = backend
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def backend_subdir(self) -> str:
        """返回 backend 对应的输出子目录名称。"""
        if self.backend in ("vlm", "hybrid-auto-engine"):
            return "hybrid_auto"
        return "auto"

    def _scan_output_files(
        self, local_output_dir: str
    ) -> tuple[Optional[str], Optional[str]]:
        """扫描 MinerU 输出目录，返回 (middle_json_path, md_path)。"""
        target_json: Optional[str] = None
        target_md: Optional[str] = None
        for root, _, files in os.walk(local_output_dir):
            for file in files:
                if file.endswith("_middle.json"):
                    target_json = os.path.join(root, file)
                elif (
                    file.endswith(".md")
                    and not file.endswith("_clean.md")
                    and not target_md
                ):
                    target_md = os.path.join(root, file)
        return target_json, target_md

    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extracts content from a given PDF using MinerU.

        若输出文件已存在则直接读取，跳过重新解析（幂等设计）。
        Returns a dictionary with raw markdown, parsed blocks, and metadata.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found at {pdf_path}")

        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        # MinerU 会在指定的 output_dir 下自动创建一个名为 pdf_name 的文件夹
        local_output_dir = os.path.join(self.output_dir, pdf_name)

        if MINERU_AVAILABLE:
            try:
                # 先检查输出文件是否已存在，避免重复解析
                target_json, target_md = self._scan_output_files(local_output_dir)
                if not target_json:
                    logger.info(
                        f"Parsing {pdf_name} with MinerU ({self.backend} backend)..."
                    )
                    assert read_fn is not None and do_parse is not None
                    pdf_bytes = read_fn(Path(pdf_path))
                    do_parse(
                        output_dir=self.output_dir,
                        pdf_file_names=[pdf_name],
                        pdf_bytes_list=[pdf_bytes],
                        p_lang_list=["en"],
                        backend=self.backend,
                        parse_method="auto",
                        f_dump_md=True,
                        f_dump_orig_pdf=False,
                        f_dump_content_list=True,
                        f_dump_middle_json=True,
                    )
                    target_json, target_md = self._scan_output_files(local_output_dir)
                else:
                    logger.info(
                        f"Found existing MinerU output for {pdf_name}, skipping re-parse."
                    )

                raw_json_data: Dict[str, Any] = {}
                if target_json and os.path.exists(target_json):
                    with open(target_json, "r", encoding="utf-8") as f:
                        raw_json_data = json.load(f)

                md_content = ""
                if target_md and os.path.exists(target_md):
                    with open(target_md, "r", encoding="utf-8") as f:
                        md_content = f.read()

                return {
                    "pdf_name": pdf_name,
                    "title": pdf_name,
                    "markdown": md_content,
                    "middle_json": raw_json_data,
                }

            except Exception as e:
                logger.error(f"MinerU parsing failed: {e}")
                return {
                    "pdf_name": pdf_name,
                    "title": pdf_name,
                    "markdown": f"MinerU parsing failed: {e}",
                    "middle_json": {},
                }
        else:
            logger.info(f"Mock analyzing PDF: {pdf_name}...")
            return {
                "pdf_name": pdf_name,
                "title": pdf_name,
                "markdown": f"# {pdf_name}\n\nMock data.",
                "middle_json": {
                    "pdf_info": [
                        {
                            "page_idx": 0,
                            "para_blocks": [
                                {
                                    "type": "text",
                                    "lines": [
                                        {
                                            "spans": [
                                                {
                                                    "type": "text",
                                                    "content": "Mock data.",
                                                }
                                            ]
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
            }

    def chunk_content(
        self, parsed_data: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Uses the granular json parsing if available, otherwise falls back to markdown splitting.
        """
        middle_json = parsed_data.get("middle_json", {})
        if middle_json:
            return self.process_middle_json(middle_json)

        md_text = parsed_data.get("markdown", "")
        splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
        text_chunks = splitter.split_text(md_text)
        chunks = [
            {"content": chunk, "type": "text", "metadata": {}} for chunk in text_chunks
        ]
        return chunks, {}

    def process_middle_json(
        self,
        middle_data: Dict[str, Any],
        max_chunk_size: int = 1500,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        将 middle.json 转换为可检索的 chunk 列表。

        修复内容：
        - [P0] 消除 heading breadcrumb 和 section header 双重输出
        - [P0] 修复图表 chunk 的 breadcrumb 在 heading 更新前被记录的问题
        - [P0] 修复 References 完全丢失（list block 在 in_references 时被跳过）
        - [P1] 修复 heading_stack 层级推断：正则改为提取纯数字前缀，支持无空格格式
        - [P1] 非章节标题（如 Algorithm 1:）不更新 heading_stack，作为局部标签
        - [P1] list block 正确处理：合并多行为单个条目，references 中也收集
        - [P2] 去掉图表 chunk 中冗余的 "Figure"/"Table" 原始类型标签
        """
        chunks: List[Dict[str, Any]] = []
        doc_metadata: Dict[str, Any] = {
            "pre_abstract_meta": [],
            "footnotes_and_discarded": [],
            "references": [],
            "title_extracted": "",
        }

        # 累积文本 chunk 的状态
        current_text_chunk: List[str] = []
        current_chunk_length: int = 0
        current_equation_imgs: List[str] = []
        current_page_idx: int = 0

        # 多级标题栈：[(level, heading_text), ...]
        # level 由数字前缀推断（"4" → 1, "4.1" → 2, "4.1.1" → 3）
        # 非数字标题（如 "Algorithm 1:"）level=0，不入栈，只作局部标签
        heading_stack: List[tuple[int, str]] = []

        # 当前局部标签（非章节号标题），随下一个章节标题清除
        local_label: str = ""

        main_content_started: bool = False
        in_references: bool = False

        try:
            tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            tokenizer = None

        # ------------------------------------------------------------------ #
        # 辅助函数                                                             #
        # ------------------------------------------------------------------ #

        def count_tokens(text: str) -> int:
            if tokenizer:
                return len(tokenizer.encode(text))
            return len(text) // 4

        def _spans_to_text(spans: List[Dict[str, Any]]) -> str:
            """将一个 spans 列表拼接为文本，正确处理行内公式。"""
            parts: List[str] = []
            for s in spans:
                content = s.get("content", "")
                if s.get("type") == "inline_equation":
                    content = content.strip()
                    if content:
                        content = f" ${content}$ "
                parts.append(content)
            return "".join(parts)

        def get_text(block: Dict[str, Any]) -> str:
            """
            递归提取 block 的纯文本内容。
            处理层次：blocks → lines → spans
            """
            text_parts: List[str] = []

            if "blocks" in block:
                for b in block["blocks"]:
                    t = get_text(b)
                    if t:
                        text_parts.append(t)
            elif "lines" in block:
                for line in block["lines"]:
                    line_text = _spans_to_text(line.get("spans", []))
                    if line_text:
                        text_parts.append(line_text)
            elif "spans" in block:
                line_text = _spans_to_text(block["spans"])
                if line_text:
                    text_parts.append(line_text)

            raw_text = "\n".join(text_parts)

            b_type = block.get("type", "")
            if b_type in (
                "text",
                "title",
                "image_caption",
                "table_caption",
                "image_footnote",
                "table_footnote",
            ):
                # 合并连字符换行（英文断词）
                raw_text = re.sub(r"-\n\s*", "", raw_text)
                # 合并中文换行
                raw_text = re.sub(r"([^\x00-\x7F])\n([^\x00-\x7F])", r"\1\2", raw_text)
                raw_text = raw_text.replace("\n", " ")

            return raw_text.strip()

        def get_list_items(block: Dict[str, Any]) -> List[str]:
            """
            从 list block 中提取每个列表条目的完整文本。
            支持两种结构：
            - Pipeline: block 直接包含 lines
            - VLM: block 包含二级 blocks（每个 block 含 lines）
            MinerU 的 list block 使用 is_list_start_line 标记条目起始行，
            同一条目的多行（缩进续行）需要合并。
            """
            items: List[str] = []
            current_item_lines: List[str] = []

            # VLM backend: 二级 blocks 结构
            if "blocks" in block:
                for sub_block in block.get("blocks", []):
                    sub_lines = sub_block.get("lines", [])
                    for line in sub_lines:
                        line_text = _spans_to_text(line.get("spans", [])).strip()
                        if not line_text:
                            continue
                        is_start = line.get("is_list_start_line", False)
                        if is_start and current_item_lines:
                            merged = _merge_hyphen_lines(current_item_lines)
                            items.append(merged.strip())
                            current_item_lines = []
                        current_item_lines.append(line_text)
                # 最后一个条目
                if current_item_lines:
                    merged = _merge_hyphen_lines(current_item_lines)
                    items.append(merged.strip())
            else:
                # Pipeline backend: 直接 lines 结构
                lines = block.get("lines", [])
                for line in lines:
                    line_text = _spans_to_text(line.get("spans", [])).strip()
                    if not line_text:
                        continue
                    is_start = line.get("is_list_start_line", False)
                    if is_start and current_item_lines:
                        merged = _merge_hyphen_lines(current_item_lines)
                        items.append(merged.strip())
                        current_item_lines = []
                    current_item_lines.append(line_text)

                # 最后一个条目
                if current_item_lines:
                    merged = _merge_hyphen_lines(current_item_lines)
                    items.append(merged.strip())

            return [it for it in items if it]

        def get_image_path(block: Dict[str, Any]) -> str:
            """
            在 block 的各层级中查找图片路径。
            兼容 'img_path'（MinerU 官方文档）和 'image_path'（旧字段名）。
            """
            for key in ("img_path", "image_path"):
                if key in block:
                    return block[key]
            if "spans" in block:
                for s in block["spans"]:
                    for key in ("img_path", "image_path"):
                        if key in s:
                            return s[key]
            if "lines" in block:
                for line in block["lines"]:
                    for s in line.get("spans", []):
                        for key in ("img_path", "image_path"):
                            if key in s:
                                return s[key]
            if "blocks" in block:
                for b in block["blocks"]:
                    res = get_image_path(b)
                    if res:
                        return res
            return ""

        def get_caption_and_footnote(block: Dict[str, Any]) -> tuple[str, str]:
            """
            从 image / table 一级块中提取所有 caption 和 footnote 文本。
            返回 (caption_text, footnote_text)。
            """
            captions: List[str] = []
            footnotes: List[str] = []
            for sub in block.get("blocks", []):
                sub_type = sub.get("type", "")
                text = get_text(sub)
                if not text:
                    continue
                if "caption" in sub_type:
                    captions.append(text)
                elif "footnote" in sub_type:
                    footnotes.append(text)
            return " ".join(captions), " ".join(footnotes)

        def infer_heading_level(heading_text: str) -> int:
            """
            根据数字前缀推断标题层级（1-based）。
            '1INTRODUCTION'    → 1  (前缀 "1"，0 个点)
            '2.1 Method'       → 2  (前缀 "2.1"，1 个点)
            '4.1.1Details'     → 3  (前缀 "4.1.1"，2 个点)
            无数字前缀          → 0  (非章节标题，不入栈)
            """
            m = _SECTION_NUM_RE.match(heading_text.strip())
            if not m:
                return 0  # 非章节号标题
            number_part = m.group(1)
            return number_part.count(".") + 1

        def update_heading_stack(heading_text: str) -> bool:
            """
            维护多级标题栈，弹出同级及子级后压入新标题。
            返回 True 表示已入栈（章节标题），False 表示未入栈（非章节标题）。
            """
            nonlocal local_label
            level = infer_heading_level(heading_text)
            if level == 0:
                # 非章节号标题（如 "Algorithm 1:"）：记为局部标签，不修改栈
                local_label = heading_text.strip()
                return False
            # 章节标题：清除局部标签，更新栈
            local_label = ""
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading_text.strip()))
            return True

        def current_heading_path() -> str:
            """返回当前标题路径字符串，如 '4METHODOLOGY > 4.1 Background'。"""
            path = " > ".join(h for _, h in heading_stack)
            if local_label:
                return f"{path} > {local_label}" if path else local_label
            return path

        def split_large_text(text: str) -> List[str]:
            """
            对超过 max_chunk_size 的单段文本做 tiktoken 感知的二次分割。
            """
            if count_tokens(text) <= max_chunk_size:
                return [text]
            sentences = re.split(r"(?<=[.!?])\s+", text)
            sub_chunks: List[str] = []
            buf: List[str] = []
            buf_len = 0
            for sent in sentences:
                sent_len = count_tokens(sent)
                if buf_len + sent_len > max_chunk_size and buf:
                    sub_chunks.append(" ".join(buf))
                    buf, buf_len = [], 0
                buf.append(sent)
                buf_len += sent_len
            if buf:
                sub_chunks.append(" ".join(buf))
            return sub_chunks if sub_chunks else [text]

        def flush_text_chunk() -> None:
            nonlocal current_text_chunk, current_chunk_length, current_equation_imgs
            if not current_text_chunk:
                return
            heading_prefix = current_heading_path()

            # heading_prefix 作为前缀，不重复写入 chunk 内容
            prefix = f"[{heading_prefix}]\n\n" if heading_prefix else ""
            combined_text = prefix + "\n\n".join(current_text_chunk)

            meta: Dict[str, Any] = {
                "heading": heading_prefix,
                "page_idx": current_page_idx,
            }
            if current_equation_imgs:
                meta["equation_imgs"] = current_equation_imgs.copy()

            chunks.append(
                {
                    "content": combined_text,
                    "type": "text",
                    "metadata": meta,
                }
            )
            current_text_chunk = []
            current_chunk_length = 0
            current_equation_imgs = []

        # ------------------------------------------------------------------ #
        # 主遍历逻辑                                                           #
        # ------------------------------------------------------------------ #

        pdf_info = middle_data.get("pdf_info", [])
        for page_data in pdf_info:
            current_page_idx = page_data.get("page_idx", current_page_idx)

            # pipeline 后端：通过关键词触发；超过第3页强制开启
            if current_page_idx >= 3:
                main_content_started = True

            for discard in page_data.get("discarded_blocks", []):
                t = get_text(discard)
                if t:
                    doc_metadata["footnotes_and_discarded"].append(t)

            for block in page_data.get("para_blocks", []):
                b_type = block.get("type", "")

                # -------- title -------- #
                if b_type == "title":
                    text_content = get_text(block)
                    if not text_content:
                        continue

                    # 第一个 title（页0或页1）视为论文标题
                    if not doc_metadata["title_extracted"]:
                        doc_metadata["title_extracted"] = text_content
                        chunks.append(
                            {
                                "content": f"# {text_content}",
                                "type": "title",
                                "metadata": {
                                    "heading": "Title",
                                    "page_idx": current_page_idx,
                                },
                            }
                        )
                        continue

                    # 检测主内容开始（ABSTRACT / INTRODUCTION 等关键词）
                    if text_content.strip().upper() in _MAIN_CONTENT_HEADINGS:
                        main_content_started = True

                    # 检测参考文献节
                    if text_content.strip().upper() in _REFERENCE_HEADINGS:
                        in_references = True
                        flush_text_chunk()
                        update_heading_stack(text_content.strip())
                        # References 节标题单独作为一个文字 chunk 的起点
                        # （不推入 current_text_chunk，由后续条目填充）
                        continue

                    # 普通章节标题：先 flush 旧 chunk，再更新 heading_stack
                    # 注意：heading 本身不推入 current_text_chunk，
                    # flush_text_chunk() 会自动把 current_heading_path() 作为前缀写入
                    flush_text_chunk()
                    update_heading_stack(text_content.strip())
                    continue

                # -------- references 区域 -------- #
                if in_references:
                    # text 和 list 类型都收集为参考文献条目
                    if b_type == "list":
                        items = get_list_items(block)
                        doc_metadata["references"].extend(items)
                    else:
                        text_content = get_text(block)
                        if text_content:
                            doc_metadata["references"].append(text_content)
                    continue

                # -------- pre-abstract metadata -------- #
                if not main_content_started:
                    text_content = get_text(block)
                    if text_content:
                        doc_metadata["pre_abstract_meta"].append(text_content)
                    continue

                # -------- table -------- #
                if b_type == "table":
                    flush_text_chunk()
                    img_path = get_image_path(block)
                    caption, footnote = get_caption_and_footnote(block)
                    heading_prefix = current_heading_path()
                    # [P2] 去掉冗余的 "Table" 原始类型标签
                    parts: List[str] = [f"[{heading_prefix}]"]
                    if caption:
                        parts.append(f"Caption: {caption}")
                    if footnote:
                        parts.append(f"Footnote: {footnote}")
                    if img_path:
                        parts.append(f"Image Path: {img_path}")
                    chunks.append(
                        {
                            "content": "\n".join(parts),
                            "type": "table",
                            "metadata": {
                                "heading": heading_prefix,
                                "page_idx": current_page_idx,
                                "img_path": img_path,
                                "caption": caption,
                                "footnote": footnote,
                            },
                        }
                    )

                # -------- image -------- #
                elif b_type == "image":
                    flush_text_chunk()
                    img_path = get_image_path(block)
                    caption, footnote = get_caption_and_footnote(block)
                    heading_prefix = current_heading_path()
                    # [P2] 去掉冗余的 "Figure" 原始类型标签
                    parts = [f"[{heading_prefix}]"]
                    if caption:
                        parts.append(f"Caption: {caption}")
                    if footnote:
                        parts.append(f"Footnote: {footnote}")
                    if img_path:
                        parts.append(f"Image Path: {img_path}")
                    chunks.append(
                        {
                            "content": "\n".join(parts),
                            "type": "image",
                            "metadata": {
                                "heading": heading_prefix,
                                "page_idx": current_page_idx,
                                "img_path": img_path,
                                "caption": caption,
                                "footnote": footnote,
                            },
                        }
                    )

                # -------- interline equation -------- #
                elif b_type in ("interline_equation", "equation"):
                    text_content = get_text(block)
                    if text_content:
                        current_text_chunk.append(f"\n$$\n{text_content}\n$$\n")
                        current_chunk_length += count_tokens(text_content)
                    eq_img = get_image_path(block)
                    if eq_img:
                        current_equation_imgs.append(eq_img)

                # -------- list block -------- #
                elif b_type == "list":
                    # [P1] 使用 get_list_items 正确合并多行条目
                    items = get_list_items(block)
                    if not items:
                        continue
                    list_text = "\n".join(f"- {item}" for item in items)
                    token_count = count_tokens(list_text)
                    if current_chunk_length + token_count > max_chunk_size:
                        flush_text_chunk()
                    current_text_chunk.append(list_text)
                    current_chunk_length += token_count

                # -------- code / algorithm (VLM backend) -------- #
                elif b_type == "code":
                    flush_text_chunk()
                    sub_type = block.get("sub_type", "code")
                    code_body = ""
                    code_caption = ""
                    for sub in block.get("blocks", []):
                        sub_block_type = sub.get("type", "")
                        if sub_block_type == "code_body":
                            code_body = get_text(sub)
                        elif sub_block_type == "code_caption":
                            code_caption = get_text(sub)
                    heading_prefix = current_heading_path()
                    lang = "text" if sub_type == "algorithm" else "python"
                    parts = [f"[{heading_prefix}]"]
                    if code_caption:
                        parts.append(code_caption)
                    parts.append(f"```{lang}\n{code_body}\n```")
                    chunks.append(
                        {
                            "content": "\n".join(parts),
                            "type": "code",
                            "metadata": {
                                "heading": heading_prefix,
                                "page_idx": current_page_idx,
                                "sub_type": sub_type,
                                "caption": code_caption,
                            },
                        }
                    )

                # -------- plain text -------- #
                else:
                    text_content = get_text(block)
                    if not text_content:
                        continue

                    # 检测疑似内联子标题（如 "5.1.3 Compared baselines."）
                    m_sub = _INLINE_SUBHEADING_RE.match(text_content)
                    if m_sub:
                        text_content = f"[{m_sub.group(1)}] {m_sub.group(3).lstrip()}"

                    for part in split_large_text(text_content):
                        part_tokens = count_tokens(part)
                        if current_chunk_length + part_tokens > max_chunk_size:
                            flush_text_chunk()
                        current_text_chunk.append(part)
                        current_chunk_length += part_tokens

        flush_text_chunk()
        return chunks, doc_metadata
