import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any
from langchain_text_splitters import MarkdownTextSplitter
from src.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from mineru.cli.common import do_parse, read_fn
    MINERU_AVAILABLE = True
except ImportError:
    MINERU_AVAILABLE = False
    logger.warning("mineru package not fully installed or configured. Using mock parser for skeleton execution.")
    logger.warning("Ensure you have Python >= 3.10 and installed 'mineru'.")

class MinerUParser:
    """
    Parser utilizing local MinerU to extract text, figures, and structured data
    from Research PDF papers.
    """
    def __init__(self, output_dir: str = "./output", backend: str = "auto"):
        self.output_dir = output_dir
        self.backend = backend
        os.makedirs(self.output_dir, exist_ok=True)

    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extracts content from a given PDF using MinerU.
        Returns a dictionary with raw markdown, parsed blocks, and metadata.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found at {pdf_path}")
        
        pdf_name = os.path.basename(pdf_path).split('.')[0]
        # MinerU 会在指定的 output_dir 下自动创建一个名为 pdf_name 的文件夹
        # 所以我们直接使用 self.output_dir 作为输出根目录，避免子目录重复
        local_output_dir = os.path.join(self.output_dir, pdf_name)
        
        # Using local MinerU
        if MINERU_AVAILABLE:
            try:
                pdf_bytes = read_fn(Path(pdf_path))
                # Execute direct python api parsing
                do_parse(
                    output_dir=self.output_dir, # <-- Pass root directly so MinerU creates `output_dir/pdf_name`
                    pdf_file_names=[pdf_name],
                    pdf_bytes_list=[pdf_bytes],
                    p_lang_list=["ch"], # Assume mixed Chinese/English as base
                    backend=self.backend,
                    parse_method="auto",
                    f_dump_md=True,
                    f_dump_orig_pdf=False,
                    f_dump_content_list=False,
                    f_dump_middle_json=True # Ensure middle.json is dumped
                )
                
                # Retrieve the generated middle json and optionally markdown
                target_json = None
                target_md = None
                for root, _, files in os.walk(local_output_dir):
                    for file in files:
                        if file.endswith("_middle.json"):
                            target_json = os.path.join(root, file)
                        elif file.endswith(".md") and not target_md:
                            target_md = os.path.join(root, file)
                
                raw_json_data = []
                if target_json and os.path.exists(target_json):
                    with open(target_json, "r", encoding="utf-8") as f:
                        raw_json_data = json.load(f)

                md_content = ""
                if target_md and os.path.exists(target_md):
                    with open(target_md, "r", encoding="utf-8") as f:
                        md_content = f.read()

                return {
                    "pdf_name": pdf_name,
                    "title": pdf_name, # Can map later
                    "markdown": md_content,
                    "middle_json": raw_json_data
                }

            except Exception as e:
                logger.error(f"MinerU parsing failed: {e}")
                return {
                    "pdf_name": pdf_name,
                    "title": pdf_name,
                    "markdown": f"MinerU parsing failed: {e}",
                    "middle_json": {}
                }
        else:
            # Fallback mock for testing the end-to-end pipeline without heavy models
            logger.info(f"Mock analyzing PDF: {pdf_name}...")
            return {
                "pdf_name": pdf_name,
                "title": pdf_name,
                "markdown": f"# {pdf_name}\n\nMock data.",
                "middle_json": {"pdf_info": [{"page_idx": 0, "para_blocks": [{"type": "text", "lines": [{"spans": [{"content": "Mock data."}]}]}]}]}
            }

    def chunk_content(self, parsed_data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Uses the granular json parsing if available, otherwise falls back to markdown splitting
        """
        middle_json = parsed_data.get("middle_json", {})
        if middle_json:
            return self.process_middle_json(middle_json)
        else:
            # Fallback to pure string matching over markdown
            md_text = parsed_data.get("markdown", "")
            from langchain_text_splitters import MarkdownTextSplitter
            splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
            text_chunks = splitter.split_text(md_text)
            chunks = [{"content": chunk, "type": "text", "metadata": {}} for chunk in text_chunks]
            return chunks, {}

    def process_middle_json(self, middle_data: Dict[str, Any], max_chunk_size: int = 1500) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        chunks = []
        doc_metadata = {
            "pre_abstract_meta": [],
            "footnotes_and_discarded": [],
            "references": [],
            "title_extracted": ""
        }
        
        current_text_chunk = []
        current_chunk_length = 0
        current_equation_imgs = []
        current_page_idx = 0
        current_heading_path = []
        
        main_content_started = False
        in_references = False
        
        import tiktoken
        try:
            tokenizer = tiktoken.get_encoding("cl100k_base")
        except:
            tokenizer = None

        def get_text(block):
            text_parts = []
            if 'blocks' in block:
                for b in block['blocks']:
                    text_parts.append(get_text(b))
            elif 'lines' in block:
                for l in block['lines']:
                    line_parts = []
                    for s in l.get('spans', []):
                        content = s.get('content', '')
                        if s.get('type') == 'inline_equation':
                            content = content.strip()
                            if content:
                                content = f"\\({content}\\)"
                        line_parts.append(content)
                    text_parts.append("".join(line_parts))
            elif 'spans' in block:
                line_parts = []
                for s in block['spans']:
                    content = s.get('content', '')
                    if s.get('type') == 'inline_equation':
                        content = content.strip()
                        if content:
                            content = f"\\({content}\\)"
                        line_parts.append(content)
                text_parts.append("".join(line_parts))
            return "\n".join(p for p in text_parts if p)

        def count_tokens(text):
            if tokenizer:
                return len(tokenizer.encode(text))
            return len(text) // 4
            
        def flush_text_chunk():
            nonlocal current_text_chunk, current_chunk_length, current_equation_imgs
            if current_text_chunk:
                heading_prefix = " > ".join(current_heading_path)
                prefix = f"[{heading_prefix}]\n" if heading_prefix else ""
                combined_text = prefix + "\n".join(current_text_chunk)
                
                meta = {
                    "heading": heading_prefix,
                    "page_idx": current_page_idx
                }
                if current_equation_imgs:
                    meta["equation_imgs"] = current_equation_imgs.copy()
                
                chunks.append({
                    "content": combined_text,
                    "type": "text",
                    "metadata": meta
                })
                current_text_chunk = []
                current_chunk_length = 0
                current_equation_imgs = []

        def get_image_path(block):
            if 'image_path' in block:
                return block['image_path']
            if 'spans' in block:
                for s in block['spans']:
                    if 'image_path' in s:
                        return s['image_path']
            if 'lines' in block:
                for l in block['lines']:
                    for s in l.get('spans', []):
                        if 'image_path' in s:
                            return s['image_path']
            if 'blocks' in block:
                for b in block['blocks']:
                    res = get_image_path(b)
                    if res: return res
            return ""

        pdf_info = middle_data.get('pdf_info', [])
        for page_data in pdf_info:
            current_page_idx = page_data.get('page_idx', current_page_idx)
            
            for discard in page_data.get('discarded_blocks', []):
                doc_metadata["footnotes_and_discarded"].append(get_text(discard))
                
            for block in page_data.get('para_blocks', []):
                b_type = block.get('type', '')
                text_content = get_text(block)
                
                if b_type == 'title':
                    is_main_heading = False
                    if text_content.strip() and not doc_metadata["title_extracted"]:
                        doc_metadata["title_extracted"] = text_content.strip()
                        chunks.append({
                            "content": f"# {text_content.strip()}",
                            "type": "title",
                            "metadata": {
                                "heading": "Title",
                                "page_idx": current_page_idx
                            }
                        })
                        continue
                    
                    if "ABSTRACT" in text_content.upper() or "INTRODUCTION" in text_content.upper():
                        main_content_started = True
                        
                    if text_content.strip().upper() in ["REFERENCES", "REFERENCE"]:
                        in_references = True
                        flush_text_chunk()
                        continue
                        
                    flush_text_chunk()
                    current_heading_path = [text_content.strip()]
                    continue
                
                if in_references:
                    if text_content.strip():
                        doc_metadata["references"].append(text_content.strip())
                    continue
                    
                if not main_content_started:
                    doc_metadata["pre_abstract_meta"].append(text_content)
                    continue

                if b_type == 'table':
                    flush_text_chunk()
                    img_path = get_image_path(block)
                    heading_prefix = " > ".join(current_heading_path)
                    combined_content = f"[{heading_prefix}]\nTable Content Placeholder\nTable Reference Path: {img_path}"
                    chunks.append({
                        "content": combined_content,
                        "type": "table",
                        "metadata": {
                            "heading": heading_prefix,
                            "page_idx": current_page_idx,
                            "img_path": img_path
                        }
                    })
                elif b_type == 'image':
                    flush_text_chunk()
                    img_path = get_image_path(block)
                    heading_prefix = " > ".join(current_heading_path)
                    combined_content = f"[{heading_prefix}]\nImage Content Placeholder\nImage Reference Path: {img_path}"
                    chunks.append({
                        "content": combined_content,
                        "type": "image",
                        "metadata": {
                            "heading": heading_prefix,
                            "page_idx": current_page_idx,
                            "img_path": img_path
                        }
                    })
                elif b_type == 'interline_equation' or b_type == 'equation':
                    if text_content.strip():
                        # Wrap block-level equations in standard Markdown math block
                        math_text = f"\n$$\n{text_content.strip()}\n$$\n"
                        current_text_chunk.append(math_text)
                    eq_img = get_image_path(block)
                    if eq_img:
                        current_equation_imgs.append(eq_img)
                else: 
                    # text
                    token_count = count_tokens(text_content)
                    if current_chunk_length + token_count > max_chunk_size:
                        flush_text_chunk()
                    current_text_chunk.append(text_content)
                    current_chunk_length += token_count

        flush_text_chunk()
        return chunks, doc_metadata
