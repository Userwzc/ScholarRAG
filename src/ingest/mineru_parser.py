import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any
from langchain_text_splitters import MarkdownTextSplitter


try:
    from mineru.cli.common import do_parse, read_fn
    MINERU_AVAILABLE = True
except ImportError:
    MINERU_AVAILABLE = False
    print("WARNING: mineru package not fully installed or configured. Using mock parser for skeleton execution.")
    print("Ensure you have Python >= 3.10 and installed 'mineru'.")

class MinerUParser:
    """
    Parser utilizing local MinerU to extract text, figures, and structured data
    from Research PDF papers.
    """
    def __init__(self, output_dir: str = "./output", backend: str = "hybrid-auto-engine"):
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
                    f_dump_content_list=True # Ensure content_list.json is dumped
                )
                
                # Retrieve the generated content_list json and optionally markdown
                target_json = None
                target_md = None
                for root, _, files in os.walk(local_output_dir):
                    for file in files:
                        if file.endswith("_content_list.json"):
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
                    "content_list": raw_json_data
                }

            except Exception as e:
                print(f"MinerU parsing failed: {e}")
                return {
                    "pdf_name": pdf_name,
                    "title": pdf_name,
                    "markdown": f"MinerU parsing failed: {e}",
                    "content_list": []
                }
        else:
            # Fallback mock for testing the end-to-end pipeline without heavy models
            print(f"Mock analyzing PDF: {pdf_name}...")
            return {
                "pdf_name": pdf_name,
                "title": pdf_name,
                "markdown": f"# {pdf_name}\n\nMock data.",
                "content_list": [{"type": "text", "text": "Mock data.", "text_level": 0}]
            }

    def process_content_list(self, content_list: List[Dict[str, Any]], max_chunk_size: int = 1500) -> List[Dict[str, Any]]:
        """
        Custom granular chunking based on MinerU's native element types.
        Combines text maintaining heading contexts, keeps tables/images atomic.
        """
        chunks = []
        current_heading_path = [] # e.g. ["1. Intro", "1.1 Background"]
        current_text_chunk = []
        current_chunk_length = 0
        current_page_idx = 0

        def flush_text_chunk():
            nonlocal current_text_chunk, current_chunk_length
            if current_text_chunk:
                heading_prefix = " > ".join(current_heading_path)
                prefix = f"[{heading_prefix}]\n" if heading_prefix else ""
                combined_text = prefix + "\n".join(current_text_chunk)
                
                chunks.append({
                    "content": combined_text,
                    "type": "text",
                    "metadata": {
                        "heading": heading_prefix,
                        "page_idx": current_page_idx
                    }
                })
                current_text_chunk = []
                current_chunk_length = 0

        for item in content_list:
            item_type = item.get("type", "")
            page_idx = item.get("page_idx", current_page_idx)
            current_page_idx = page_idx
            
            if item_type == "text":
                text_content = item.get("text", "")
                text_level = item.get("text_level", 0)
                
                # It's a heading
                if text_level > 0:
                    flush_text_chunk() # Flush pending text before starting new section
                    # Update heading path hierarchy
                    # MinerU text_level starts from 1; truncate path to match level depth
                    layer = text_level - 1
                    if layer < len(current_heading_path):
                        current_heading_path = current_heading_path[:layer]
                    current_heading_path.append(text_content)
                else:
                    # It's a normal paragraph
                    import tiktoken
                    # Rough estimation using standard cl100k
                    tokenizer = tiktoken.get_encoding("cl100k_base")
                    token_count = len(tokenizer.encode(text_content))
                    
                    if current_chunk_length + token_count > max_chunk_size:
                        flush_text_chunk()
                    
                    current_text_chunk.append(text_content)
                    current_chunk_length += token_count

            elif item_type == "table":
                flush_text_chunk()
                caption = " ".join(item.get("table_caption", []))
                footnotes = " ".join(item.get("table_footnote", []))
                html_body = item.get("table_body", "")
                
                heading_prefix = " > ".join(current_heading_path)
                combined_content = f"[{heading_prefix}]\nTable Caption: {caption}\nData: {html_body}\nFootnotes: {footnotes}"
                chunks.append({
                    "content": combined_content,
                    "type": "table",
                    "metadata": {
                        "heading": heading_prefix,
                        "page_idx": page_idx,
                        "has_image": bool(item.get("img_path"))
                    }
                })

            elif item_type == "image":
                flush_text_chunk()
                caption = " ".join(item.get("image_caption", []))
                img_path = item.get("img_path", "")
                
                heading_prefix = " > ".join(current_heading_path)
                combined_content = f"[{heading_prefix}]\nImage Caption: {caption}\nImage Reference Path: {img_path}"
                chunks.append({
                    "content": combined_content,
                    "type": "image",
                    "metadata": {
                        "heading": heading_prefix,
                        "page_idx": page_idx,
                        "img_path": img_path
                    }
                })
                
            elif item_type == "equation":
                text_content = item.get("text", "")
                current_text_chunk.append(text_content) # Equation just appends to stream
                # Could format specially if needed

        # Flush any remaining text at the end
        flush_text_chunk()
        
        return chunks

    def chunk_content(self, parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Uses the granular json parsing if available, otherwise falls back to markdown splitting
        """
        content_list = parsed_data.get("content_list", [])
        if content_list:
            return self.process_content_list(content_list)
        else:
            # Fallback to pure string matching over markdown
            md_text = parsed_data.get("markdown", "")
            from langchain_text_splitters import MarkdownTextSplitter
            splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
            text_chunks = splitter.split_text(md_text)
            return [{"content": chunk, "type": "text", "metadata": {}} for chunk in text_chunks]
