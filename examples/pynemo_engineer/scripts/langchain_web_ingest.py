# SPDX-FileCopyrightText: Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import json
import os
import re
import sys
import ast
from urllib.parse import urljoin, urlparse
from uuid import uuid4
import argparse
import asyncio
import requests
from bs4 import BeautifulSoup
from langchain.schema import Document
from langchain_community.document_loaders import BSHTMLLoader
from langchain_milvus import Milvus
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_text_splitters import Language
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyMuPDFLoader
from pymilvus import Collection
from pymilvus import connections
from pymilvus import utility
from web_utils import cache_html
from web_utils import get_file_path_from_url
from web_utils import scrape

# Add parent scripts directory to path for sitemap_scraper
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts'))
from sitemap_scraper import get_urls_from_sitemap

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

def process_arxiv_url(url: str, chunk_size: int = 16000, chunk_overlap: int = 2000) -> list[Document]:
    """
    Downloads arXiv PDF, converts to text, and splits using large-context parameters.
    Default chunk_size 16000 chars ~= 4000 tokens (well within the 8k limit).
    """
    # 1. Normalize URL to PDF
    # Handles http/https, www, and query parameters
    clean_url = url.split('?')[0].strip()
    if "arxiv.org/abs/" in clean_url:
        pdf_url = clean_url.replace("/abs/", "/pdf/")
    elif "arxiv.org/pdf/" in clean_url:
        pdf_url = clean_url
    else:
        logger.warning(f"URL {url} does not look like a standard arXiv link. Attempting direct download.")
        pdf_url = clean_url
        
    if not pdf_url.endswith(".pdf"):
        pdf_url += ".pdf"

    logger.info(f"Processing arXiv Paper: {clean_url} -> {pdf_url}")

    try:
        # 2. Download
        response = requests.get(pdf_url, timeout=60)
        response.raise_for_status()
        
        temp_filename = f"temp_{uuid4()}.pdf"
        with open(temp_filename, "wb") as f:
            f.write(response.content)
            
        # 3. Load with PyMuPDF (Cleanest extraction for scientific layout)
        loader = PyMuPDFLoader(temp_filename)
        raw_docs = loader.load()
        
        # 4. Merge Page Content
        # PDFs split by page. We want to merge them first, THEN split by token/char limit
        # to avoid arbitrary splits at page footers.
        full_text = "\n\n".join([d.page_content for d in raw_docs])
        
        # 5. Clean up
        os.remove(temp_filename)
        
        # 6. Split with Large Context
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap,
            separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""] # Try to split on headers first
        )
        
        # Create docs
        chunks = text_splitter.create_documents([full_text])
        
        # 7. Apply Metadata
        for d in chunks:
            d.metadata['source'] = clean_url # Keep the original ABS url for the user reference
            d.metadata['title'] = f"arXiv:{clean_url.split('/')[-1]}"
            d.metadata = sanitize_metadata(d.metadata)
            
        return chunks

    except Exception as e:
        logger.error(f"Failed to process arXiv URL {url}: {e}")
        return []

# --- NEW: AST Splitter Logic (Optimized for 8k Context) ---

def get_node_source(code: str, node: ast.AST) -> str:
    """Extracts the source code for a specific AST node to preserve formatting."""
    return ast.get_source_segment(code, node) or ""

def process_notebook(content: str, filename: str, base_metadata: dict, chunk_size: int = 24000) -> list[Document]:
    """
    Parses a .ipynb JSON string and converts cells into Documents.
    Updated to use larger chunk sizes for the new embedding model.
    """
    try:
        notebook = json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse {filename} as JSON/Notebook.")
        return []

    docs = []
    
    # Iterate through cells
    for i, cell in enumerate(notebook.get('cells', [])):
        cell_source = "".join(cell.get('source', []))
        if not cell_source.strip():
            continue

        # Create specific metadata for the cell
        cell_meta = base_metadata.copy()
        cell_meta.update({
            "cell_index": str(i),
            "cell_type": cell.get('cell_type', 'unknown')
        })

        if cell['cell_type'] == 'markdown':
            # Use existing Markdown logic
            md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2")])
            cell_docs = md_splitter.split_text(cell_source)
            
            # Re-split with larger chunks for 8k model
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_size // 10)
            for d in cell_docs:
                final_meta = {**cell_meta, **d.metadata}
                final_meta = sanitize_metadata(final_meta)
                docs.extend(text_splitter.create_documents([d.page_content], metadatas=[final_meta]))

        elif cell['cell_type'] == 'code':
            # Treat code cells as Python chunks
            # If the cell is massive, split it, otherwise keep it whole
            if len(cell_source) > chunk_size:
                code_splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.PYTHON,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_size // 10,
                )
                final_meta = sanitize_metadata(cell_meta)
                docs.extend(code_splitter.create_documents([cell_source], metadatas=[final_meta]))
            else:
                final_meta = sanitize_metadata(cell_meta)
                docs.append(Document(page_content=cell_source, metadata=final_meta))

    return docs

def split_python_using_ast(content: str, filename: str, max_chunk_char_size: int = 24000) -> list[Document]:
    """
    Splits Python code for an 8k context window embedding model.
    Strategy:
    1. Try to keep whole Classes intact.
    2. If a Class is too large (> max_chunk_char_size), split it into methods.
    3. Keep top-level functions intact.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        logger.warning(f"Syntax error parsing {filename}, skipping AST split.")
        return []

    docs = []
    
    # 1. Extract Imports (Global context)
    imports = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(get_node_source(content, node))
    import_block = "\n".join(imports)

    processed_nodes = set()

    # 2. Iterate over body to find Classes and Functions
    for node in tree.body:
        # Handle Classes
        if isinstance(node, ast.ClassDef):
            processed_nodes.add(node)
            class_source = get_node_source(content, node)
            
            # STRATEGY: Whole Class vs. Method Splitting
            # Check if the whole class fits in one vector chunk (including imports)
            total_content = f"# File: {filename}\n# Context: Whole Class\n{import_block}\n\n{class_source}"
            
            if len(total_content) <= max_chunk_char_size:
                # OPTION A: Embed the WHOLE class
                docs.append(Document(
                    page_content=total_content,
                    metadata={"type": "class", "name": node.name, "parent_class": None}
                ))
            else:
                # OPTION B: Class is too big, break it down by methods
                logger.info(f"Class '{node.name}' in {filename} is too large ({len(total_content)} chars). Splitting by methods.")
                
                class_doc = ast.get_docstring(node) or ""
                class_header = f"class {node.name}:\n    \"\"\"{class_doc}\"\"\""
                
                for sub_node in node.body:
                    if isinstance(sub_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_source = get_node_source(content, sub_node)
                        context_header = f"# File: {filename}\n# Class: {node.name}\n# Context: Split Method\n"
                        full_method = f"{context_header}{import_block}\n\n{class_header}\n\n    # Method Implementation\n{method_source}"
                        
                        docs.append(Document(
                            page_content=full_method,
                            metadata={"type": "method", "name": sub_node.name, "parent_class": node.name}
                        ))

        # Handle Top-Level Functions
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            processed_nodes.add(node)
            func_source = get_node_source(content, node)
            context_header = f"# File: {filename}\n# Type: Top-Level Function\n"
            full_content = f"{context_header}{import_block}\n\n{func_source}"
            
            docs.append(Document(
                page_content=full_content,
                metadata={"type": "function", "name": node.name, "parent_class": None}
            ))

    # 3. Capture Top-Level Constants / Assignments / Script Code
    loose_code_nodes = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node not in processed_nodes:
            loose_code_nodes.append(node)
            
    if loose_code_nodes:
        loose_code_content = ""
        for node in loose_code_nodes:
            seg = get_node_source(content, node)
            if seg:
                loose_code_content += seg + "\n"
        
        if loose_code_content.strip():
            context_header = f"# File: {filename}\n# Type: Module Constants / Script\n"
            full_content = f"{context_header}{import_block}\n\n{loose_code_content}"
            
            # Check size for massive scripts
            if len(full_content) > max_chunk_char_size:
                 splitter = RecursiveCharacterTextSplitter(chunk_size=max_chunk_char_size, chunk_overlap=200)
                 chunks = splitter.split_text(full_content)
                 for chunk in chunks:
                     docs.append(Document(
                        page_content=chunk,
                        metadata={"type": "module_code", "name": "globals", "parent_class": None}
                    ))
            else:
                docs.append(Document(
                    page_content=full_content,
                    metadata={"type": "module_code", "name": "globals", "parent_class": None}
                ))
            
    return docs

# --- END NEW Logic ---

def discover_urls_from_sitemap(sitemap_url: str, base_url_filter: str = None, limit: int = None) -> list[str]:
    logger.info("Discovering URLs from sitemap: %s", sitemap_url)
    url_entries = get_urls_from_sitemap(sitemap_url, limit=limit)
    urls = [entry['url'] for entry in url_entries if entry.get('url')]
    
    if base_url_filter:
        urls = [url for url in urls if url.startswith(base_url_filter)]
        logger.info("Filtered to %d URLs under %s", len(urls), base_url_filter)
    else:
        logger.info("Found %d URLs in sitemap", len(urls))
    return urls

def collect_file_paths(base_dir: str,
                       include_ext: list[str] | None = None,
                       exclude_dirs: list[str] | None = None,
                       limit: int | None = None) -> list[str]:
    include_ext = [ext.lower() for ext in include_ext] if include_ext else []
    exclude_dirs = set(exclude_dirs or [])

    collected = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if include_ext:
                if not any(file.lower().endswith(ext) for ext in include_ext):
                    continue
            full_path = os.path.join(root, file)
            collected.append(full_path)
            if limit and len(collected) >= limit:
                return collected
    return collected

def extract_python_symbols(content: str) -> list[str]:
    try:
        tree = ast.parse(content)
        symbols = []
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(node.name)
        return symbols
    except Exception:
        return []

def build_metadata(path: str,
                   base_dir: str,
                   repo_sha: str | None,
                   commit_date: str | None,
                   symbols: list[str] | None) -> dict:
    rel_path = os.path.relpath(path, base_dir)
    module = rel_path.replace(os.sep, ".")
    if module.endswith(".py"):
        module = module[:-3]
    meta = {
        "path": rel_path,
        "module": module,
    }
    if repo_sha is not None:
        meta["repo_sha"] = str(repo_sha)
    if commit_date is not None:
        meta["commit_date"] = str(commit_date)
    if symbols:
        meta["symbols"] = ", ".join(str(s) for s in symbols)
    return meta

def sanitize_metadata(meta: dict) -> dict:
    """
    Ensure metadata only has scalar fields and always includes ALL required schema keys.
    """
    required_keys = {
        "path", "module", "repo_sha", "commit_date", "symbols", 
        "h1", "h2", "h3", 
        "type", "name", "parent_class"
    }
    
    cleaned = {k: v for k, v in meta.items() if k in required_keys and not isinstance(v, (list, dict))}
    
    for key in required_keys:
        if key not in cleaned or cleaned[key] is None:
            cleaned[key] = ""
        cleaned[key] = str(cleaned[key])
        
    return cleaned

def drop_collection_if_requested(collection_name: str, uri: str, reset: bool):
    if not reset:
        return
    try:
        connections.connect(uri=uri)
        if utility.has_collection(collection_name):
            Collection(collection_name).drop()
            logger.info("Dropped existing collection '%s' at %s", collection_name, uri)
        else:
            logger.info("Collection '%s' does not exist; nothing to drop", collection_name)
    except Exception as e:
        logger.warning("Failed to drop collection '%s': %s", collection_name, e)

def crawl_urls(start_url: str, base_url_filter: str = None, limit: int = None, extensions: list[str] = None) -> list[str]:
    base_url_filter = base_url_filter or start_url
    extensions = extensions or ['.html', '.htm', '']
    visited = set()
    to_visit = [start_url]
    discovered = []
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    while to_visit:
        if limit and len(discovered) >= limit: break
        url = to_visit.pop(0)
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip('/')
        if normalized in visited: continue
        visited.add(normalized)
        if not url.startswith(base_url_filter): continue
        
        try:
            resp = session.get(url, timeout=10)
            if 'text/html' not in resp.headers.get('content-type', ''): continue
            discovered.append(url)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for link in soup.find_all('a', href=True):
                full = urljoin(url, link['href']).split('#')[0]
                if full.startswith(base_url_filter) and full not in visited:
                    to_visit.append(full)
        except: pass
    return discovered

def discover_urls(start_url: str, sitemap_url: str = None, base_url_filter: str = None, limit: int = None) -> list[str]:
    if sitemap_url:
        try:
            return discover_urls_from_sitemap(sitemap_url, base_url_filter, limit)
        except: pass
    return crawl_urls(start_url, base_url_filter, limit)

async def ingest_local_files(*,
                             file_paths: list[str],
                             base_dir: str,
                             milvus_uri: str,
                             collection_name: str,
                             embedding_model: str = "nvidia/llama-3.2-nemoretriever-300m-embed-v2", # UPDATED DEFAULT
                             repo_sha: str | None = None,
                             commit_date: str | None = None,
                             # UPDATED DEFAULTS FOR 8K MODEL (~24k chars)
                             code_chunk_size: int = 24000, 
                             code_chunk_overlap: int = 2400,
                             text_chunk_size: int = 8000,
                             text_chunk_overlap: int = 800):
    
    if not file_paths:
        logger.error("No local files found to ingest.")
        return []

    embedder = NVIDIAEmbeddings(model=embedding_model, truncate="END")
    vector_store = Milvus(
        embedding_function=embedder,
        collection_name=collection_name,
        connection_args={"uri": milvus_uri},
    )

    docs: list[Document] = []

    for path in file_paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Skipping %s due to read error: %s", path, e)
            continue

        ext = os.path.splitext(path)[1].lower()
        symbols = extract_python_symbols(content) if ext == ".py" else []
        base_metadata = build_metadata(path, base_dir, repo_sha, commit_date, symbols)

        if ext == ".ipynb":
            # Pass larger chunk size to notebook processor
            nb_docs = process_notebook(content, path, base_metadata, chunk_size=code_chunk_size)
            docs.extend(nb_docs)

        elif ext == ".py":
            # Use updated AST logic with larger chunk size
            ast_docs = split_python_using_ast(content, base_metadata['path'], max_chunk_char_size=code_chunk_size)
            
            if ast_docs:
                for d in ast_docs:
                    final_meta = {**base_metadata, **d.metadata}
                    d.metadata = sanitize_metadata(final_meta)
                    docs.append(d)
            else:
                logger.info(f"AST parsing returned no docs for {path}, falling back to recursive splitter.")
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.PYTHON,
                    chunk_size=code_chunk_size,
                    chunk_overlap=code_chunk_overlap,
                )
                md = sanitize_metadata(base_metadata)
                docs.extend(splitter.create_documents([content], metadatas=[md]))
        
        elif ext in {".md", ".markdown"}:
            # STRATEGY: Whole File vs. Header Splitting
            # We use code_chunk_size (approx 24k chars) as the safety limit for the 8k token model
            
            if len(content) <= code_chunk_size:
                # OPTION A: Embed the WHOLE file
                # This preserves global context (Intro + Body + Conclusion)
                final_meta = sanitize_metadata(base_metadata)
                docs.append(Document(page_content=content, metadata=final_meta))
            
            else:
                # OPTION B: File is too massive, fall back to semantic splitting
                logger.info(f"Markdown file {path} is too large ({len(content)} chars). Splitting by headers.")
                
                md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2")])
                md_docs = md_splitter.split_text(content)
                
                # We use text_chunk_size here for the sub-chunks
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=text_chunk_size, chunk_overlap=text_chunk_overlap)
                
                for d in md_docs:
                    md_meta = {**base_metadata, **d.metadata}
                    md_meta = sanitize_metadata(md_meta)
                    docs.extend(text_splitter.create_documents([d.page_content], metadatas=[md_meta]))
        else:
            splitter = RecursiveCharacterTextSplitter(chunk_size=text_chunk_size, chunk_overlap=text_chunk_overlap)
            md = sanitize_metadata(base_metadata)
            docs.extend(splitter.create_documents([content], metadatas=[md]))

    if not docs:
        logger.error("No documents produced from local files.")
        return []

    ids = [str(uuid4()) for _ in range(len(docs))]
    logger.info("Adding %s chunks from %s files to collection %s", len(docs), len(file_paths), collection_name)
    
    batch_size = 500
    doc_ids = []
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        batch_ids = ids[i:i+batch_size]
        logger.info(f"Pushing batch {i//batch_size + 1}...")
        res = await vector_store.aadd_documents(documents=batch, ids=batch_ids)
        doc_ids.extend(res)

    logger.info("Ingestion complete. Added %s documents.", len(doc_ids))
    return doc_ids

async def main(*, urls, milvus_uri, collection_name, clean_cache, embedding_model="nvidia/llama-3.2-nemoretriever-300m-embed-v2", base_path="./html_cache"):
    logger.info("Starting web documentation ingestion for %d URLs", len(urls))
    embedder = NVIDIAEmbeddings(model=embedding_model, truncate="END")
    vector_store = Milvus(embedding_function=embedder, collection_name=collection_name, connection_args={"uri": milvus_uri})
    
    # 1. Identify which URLs are already cached vs need scraping
    url_to_path_map = {url: get_file_path_from_url(url, base_path)[0] for url in urls}
    
    filenames_existing = [path for path in url_to_path_map.values() if os.path.exists(path)]
    urls_to_scrape = [url for url, path in url_to_path_map.items() if not os.path.exists(path)]
    
    logger.info("Found %d cached files, need to scrape %d URLs", len(filenames_existing), len(urls_to_scrape))
    
    # 2. Scrape missing URLs
    if len(urls_to_scrape) > 0:
        html_data, err = await scrape(urls_to_scrape)
        logger.info("Scraped %d pages (%d failures)", len(html_data), len(err))
        
        for data in html_data:
            cache_html(data, base_path)

    # 3. Process URLs
    logger.info("Processing HTML files...")
    doc_ids = []
    
    for url in urls:
        # --- NEW LOGIC START ---
        if "arxiv.org" in url:
            docs = process_arxiv_url(url)
            if docs:
                ids = [str(uuid4()) for _ in range(len(docs))]
                doc_ids.extend(await vector_store.aadd_documents(documents=docs, ids=ids))
            continue
        # --- NEW LOGIC END ---

        filename, _ = get_file_path_from_url(url, base_path)
        
        if not filename or not os.path.exists(filename):
            logger.warning(f"Skipping invalid or missing file for URL {url}: {filename}")
            continue

        loader = BSHTMLLoader(filename)
        raw_docs = loader.load()
        
        # Overwrite the 'source' metadata with the actual URL
        for d in raw_docs:
            d.metadata['source'] = url 
            if 'title' not in d.metadata: 
                d.metadata['title'] = url.split('/')[-1]

        # UPDATED: Increased web text chunk size for 8k model
        splitter = RecursiveCharacterTextSplitter(chunk_size=8000, chunk_overlap=800)
        docs = splitter.split_documents(raw_docs)
        
        if docs:
            ids = [str(uuid4()) for _ in range(len(docs))]
            doc_ids.extend(await vector_store.aadd_documents(documents=docs, ids=ids))
            
            if clean_cache: 
                os.remove(filename)
    
    logger.info("Web documentation ingestion complete. Added %d document chunks to collection '%s'", len(doc_ids), collection_name)
    return doc_ids

if __name__ == "__main__":
    PHYSNEMO_START_URL = "https://docs.nvidia.com/physicsnemo/latest/index.html"
    PHYSNEMO_BASE_URL = "https://docs.nvidia.com/physicsnemo/latest/"
    PHYSNEMO_COLLECTION_NAME = "physicsnemo_docs"
    PHYSNEMO_CODE_COLLECTION_NAME = "physicsnemo_code"
    DEFAULT_URI = "http://localhost:19530"

    parser = argparse.ArgumentParser()
    
    url_group = parser.add_argument_group('URL sources')
    url_group.add_argument("--urls", default=[], action="append")
    url_group.add_argument("--url_file", default=None, help="Path to a .txt file containing a list of URLs")
    url_group.add_argument("--start_url", default=None)
    url_group.add_argument("--sitemap", default=None)
    url_group.add_argument("--base_url", default=None)
    url_group.add_argument("--limit", type=int, default=None)
    url_group.add_argument("--crawl", default=False, action="store_true")

    local_group = parser.add_argument_group('Local sources')
    local_group.add_argument("--base_dir", default=None)
    local_group.add_argument("--include_ext", default=".py,.ipynb,.md,.rst,.txt,.yaml,.yml,.json")
    local_group.add_argument("--exclude_dirs", default=".git,.github,.venv,__pycache__,.mypy_cache,.tox,node_modules,build,dist")
    local_group.add_argument("--max_files", type=int, default=None)
    local_group.add_argument("--repo_sha", default=None)
    local_group.add_argument("--commit_date", default=None)
    
    parser.add_argument("--collection_name", "-n", default=None)
    parser.add_argument("--milvus_uri", "-u", default=DEFAULT_URI)
    parser.add_argument("--clean_cache", default=False, action="store_true")
    parser.add_argument("--list_only", default=False, action="store_true")
    parser.add_argument("--reset_collection", action="store_true")
    parser.add_argument("--embedding_model", default="nvidia/llama-3.2-nemoretriever-300m-embed-v2")
    args = parser.parse_args()

    if args.base_dir:
        collection_name = args.collection_name or PHYSNEMO_CODE_COLLECTION_NAME
        include_ext = [ext.strip() for ext in args.include_ext.split(",") if ext.strip()]
        exclude_dirs = [d.strip() for d in args.exclude_dirs.split(",") if d.strip()]

        file_paths = collect_file_paths(
            base_dir=args.base_dir, include_ext=include_ext, exclude_dirs=exclude_dirs, limit=args.max_files
        )
        logger.info("Discovered %d local files", len(file_paths))

        if args.list_only:
            for p in file_paths: print(f"  - {p}")
            sys.exit(0)

        drop_collection_if_requested(collection_name, args.milvus_uri, args.reset_collection)

        asyncio.run(ingest_local_files(
            file_paths=file_paths,
            base_dir=args.base_dir,
            milvus_uri=args.milvus_uri,
            collection_name=collection_name,
            repo_sha=args.repo_sha,
            commit_date=args.commit_date,
            embedding_model=args.embedding_model,
        ))
    else:
        urls = []
        if args.url_file:
            if os.path.exists(args.url_file):
                with open(args.url_file, 'r') as f:
                    urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                logger.info(f"Loaded {len(urls)} URLs from {args.url_file}")
            else:
                logger.error(f"URL file not found: {args.url_file}")
                sys.exit(1)

        if args.urls:
            urls.extend(args.urls)
        
        collection_name = args.collection_name or PHYSNEMO_COLLECTION_NAME

        # Logic: If no specific URLs provided, fall back to crawl mode
        if not urls:
            start_url = args.start_url or PHYSNEMO_START_URL
            base_url = args.base_url or PHYSNEMO_BASE_URL
            if args.crawl: 
                urls = crawl_urls(start_url, base_url_filter=base_url, limit=args.limit)
            else: 
                urls = discover_urls(start_url, args.sitemap, base_url, args.limit)
            
        if args.list_only:
            for u in urls: print(f"  - {u}")
        else:
            drop_collection_if_requested(collection_name, args.milvus_uri, args.reset_collection)
            asyncio.run(main(urls=urls, 
                             milvus_uri=args.milvus_uri, 
                             collection_name=collection_name, 
                             clean_cache=args.clean_cache,
                             embedding_model=args.embedding_model))