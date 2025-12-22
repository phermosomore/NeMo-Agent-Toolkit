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

import requests
from bs4 import BeautifulSoup
from langchain.schema import Document
from langchain_community.document_loaders import BSHTMLLoader
from langchain_milvus import Milvus
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langchain_text_splitters import Language
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
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

# --- NEW: AST Splitter Logic ---

def get_node_source(code: str, node: ast.AST) -> str:
    """Extracts the source code for a specific AST node to preserve formatting."""
    return ast.get_source_segment(code, node) or ""

def process_notebook(content: str, filename: str, base_metadata: dict) -> list[Document]:
    """
    Parses a .ipynb JSON string and converts cells into Documents.
    - Markdown cells are treated as Markdown.
    - Code cells are treated as Python code.
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
            # Use your existing Markdown logic logic for consistency
            md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")])
            # We treat the cell as a standalone markdown doc
            cell_docs = md_splitter.split_text(cell_source)
            
            # Re-split if chunks are too large
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
            for d in cell_docs:
                # Merge metadata
                final_meta = {**cell_meta, **d.metadata}
                # Sanitize to ensure flat structure for Milvus
                final_meta = sanitize_metadata(final_meta)
                docs.extend(text_splitter.create_documents([d.page_content], metadatas=[final_meta]))

        elif cell['cell_type'] == 'code':
            # Treat code cells as Python chunks
            # Note: AST splitting might fail on small snippets, so we often default to recursive for cells
            # unless the cell is very large. Here we use Recursive for safety on snippets.
            code_splitter = RecursiveCharacterTextSplitter.from_language(
                language=Language.PYTHON,
                chunk_size=2000,
                chunk_overlap=200,
            )
            final_meta = sanitize_metadata(cell_meta)
            docs.extend(code_splitter.create_documents([cell_source], metadatas=[final_meta]))

    return docs

def split_python_using_ast(content: str, filename: str, min_chunk_size: int = 200) -> list[Document]:
    """
    Splits Python code by structural definitions (Classes and Functions) 
    AND captures module-level constants/variables.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    docs = []
    
    # 1. Extract Imports (Global context)
    imports = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(get_node_source(content, node))
    import_block = "\n".join(imports)

    # Track which nodes we have processed to identify "loose" code later
    processed_nodes = set()

    # 2. Iterate over body to find Classes and Functions
    for node in tree.body:
        # Handle Top-Level Classes
        if isinstance(node, ast.ClassDef):
            processed_nodes.add(node)
            class_name = node.name
            class_doc = ast.get_docstring(node) or ""
            class_header_source = f"class {class_name}:\n    \"\"\"{class_doc}\"\"\""
            
            for sub_node in node.body:
                if isinstance(sub_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_source = get_node_source(content, sub_node)
                    context_header = f"# File: {filename}\n# Class: {class_name}\n# Context: Imports included below\n"
                    full_content = f"{context_header}{import_block}\n\n{class_header_source}\n\n    # Method Implementation\n{method_source}"
                    
                    docs.append(Document(
                        page_content=full_content,
                        metadata={"type": "method", "name": sub_node.name, "parent_class": class_name}
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

    # 3. Capture Top-Level Constants / Assignments / Script Code (The Fix)
    # We collect all nodes that are NOT imports and weren't processed as classes/funcs
    loose_code_nodes = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node not in processed_nodes:
            loose_code_nodes.append(node)
            
    if loose_code_nodes:
        # Extract source for these nodes (assignments, if __name__, etc.)
        loose_code_content = ""
        for node in loose_code_nodes:
            seg = get_node_source(content, node)
            if seg:
                loose_code_content += seg + "\n"
        
        # Only add if substantial enough
        if loose_code_content.strip():
            context_header = f"# File: {filename}\n# Type: Module Constants / Script\n"
            full_content = f"{context_header}{import_block}\n\n{loose_code_content}"
            
            docs.append(Document(
                page_content=full_content,
                metadata={
                    "type": "module_code",
                    "name": "globals",
                    "parent_class": None
                }
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
    This avoids Milvus schema errors for missing/non-scalar fields.
    """
    # 1. Define ALL keys your Milvus schema might expect
    # "h1", "h2", "h3" are required by your schema based on the error
    # "type", "name", "parent_class" are new keys for the code agent
    required_keys = {
        "path", "module", "repo_sha", "commit_date", "symbols", 
        "h1", "h2", "h3", 
        "type", "name", "parent_class"
    }
    
    # 2. Filter out complex types (lists/dicts) from the input
    cleaned = {k: v for k, v in meta.items() if k in required_keys and not isinstance(v, (list, dict))}
    
    # 3. Backfill missing keys with empty strings to satisfy Milvus schema
    for key in required_keys:
        if key not in cleaned or cleaned[key] is None:
            cleaned[key] = ""
            
        # Ensure everything is a string (Milvus metadata is often string-only)
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
    # (Implementation remains same as original, omitted for brevity but assumed present)
    # ... Copy previous implementation if needed or assume user keeps it ...
    # For the sake of a runnable script, I will include the minimal logic required or the user keeps existing
    # Just copying the existing logic to ensure it runs:
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
    # Same as original
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
                             embedding_model: str = "nvidia/nv-embedqa-e5-v5",
                             repo_sha: str | None = None,
                             commit_date: str | None = None,
                             code_chunk_size: int = 4000,
                             code_chunk_overlap: int = 400,
                             text_chunk_size: int = 1200,
                             text_chunk_overlap: int = 150):
    
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

        # --- MODIFIED LOGIC START ---
        if ext == ".ipynb":
            # STRATEGY: JSON Parsing -> Cell Splitting
            nb_docs = process_notebook(content, path, base_metadata)
            docs.extend(nb_docs)

        elif ext == ".py":
            # STRATEGY 4: AST Based Splitting
            # We pass the relative path (base_metadata['path']) to the splitter for context
            ast_docs = split_python_using_ast(content, base_metadata['path'])
            
            if ast_docs:
                # Merge the AST metadata with the file metadata
                for d in ast_docs:
                    final_meta = {**base_metadata, **d.metadata}
                    d.metadata = sanitize_metadata(final_meta)
                    docs.append(d)
            else:
                # Fallback to naive splitting if AST failed (e.g. syntax error in file) or file was empty
                logger.info(f"AST parsing returned no docs for {path}, falling back to recursive splitter.")
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.PYTHON,
                    chunk_size=code_chunk_size,
                    chunk_overlap=code_chunk_overlap,
                )
                md = sanitize_metadata(base_metadata)
                docs.extend(splitter.create_documents([content], metadatas=[md]))

        # --- MODIFIED LOGIC END ---
        
        elif ext in {".md", ".markdown"}:
            md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")])
            md_docs = md_splitter.split_text(content)
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
    
    # Milvus/LangChain batching is usually automatic, but adding extremely large batches 
    # can sometimes timeout depending on the server settings.
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

async def main(*, urls, milvus_uri, collection_name, clean_cache, embedding_model="nvidia/nv-embedqa-e5-v5", base_path="./html_cache"):
    logger.info("Starting web documentation ingestion for %d URLs", len(urls))
    embedder = NVIDIAEmbeddings(model=embedding_model, truncate="END")
    vector_store = Milvus(embedding_function=embedder, collection_name=collection_name, connection_args={"uri": milvus_uri})
    
    # 1. Identify which URLs are already cached vs need scraping
    # We maintain a mapping of URL -> FilePath
    url_to_path_map = {url: get_file_path_from_url(url, base_path)[0] for url in urls}
    
    filenames_existing = [path for path in url_to_path_map.values() if os.path.exists(path)]
    urls_to_scrape = [url for url, path in url_to_path_map.items() if not os.path.exists(path)]
    
    logger.info("Found %d cached files, need to scrape %d URLs", len(filenames_existing), len(urls_to_scrape))
    
    # 2. Scrape missing URLs
    if len(urls_to_scrape) > 0:
        html_data, err = await scrape(urls_to_scrape)
        logger.info("Scraped %d pages (%d failures)", len(html_data), len(err))
        
        # Cache HTML
        for data in html_data:
            cache_html(data, base_path)

    # 3. Process URLs (Iterate URLs to preserve the Source link)
    logger.info("Processing HTML files...")
    doc_ids = []
    
    # We iterate over the URLs specifically so we can inject the URL back into the metadata
    for url in urls:
        filename, _ = get_file_path_from_url(url, base_path)
        
        if not filename or not os.path.exists(filename):
            logger.warning(f"Skipping invalid or missing file for URL {url}: {filename}")
            continue

        loader = BSHTMLLoader(filename)
        raw_docs = loader.load() # Loads with local filepath as source
        
        # --- CRITICAL FIX START ---
        # Overwrite the 'source' metadata with the actual URL
        for d in raw_docs:
            d.metadata['source'] = url 
            # Optional: Ensure other metadata fields exist to satisfy strict Milvus schemas
            if 'title' not in d.metadata: 
                d.metadata['title'] = url.split('/')[-1]
        # --- CRITICAL FIX END ---

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(raw_docs)
        
        if docs:
            ids = [str(uuid4()) for _ in range(len(docs))]
            doc_ids.extend(await vector_store.aadd_documents(documents=docs, ids=ids))
            
            if clean_cache: 
                os.remove(filename)
    
    logger.info("Web documentation ingestion complete. Added %d document chunks to collection '%s'", len(doc_ids), collection_name)
    return doc_ids

if __name__ == "__main__":
    import argparse
    import asyncio

    # Default URLs
    PHYSNEMO_START_URL = "https://docs.nvidia.com/physicsnemo/latest/index.html"
    PHYSNEMO_BASE_URL = "https://docs.nvidia.com/physicsnemo/latest/"
    PHYSNEMO_COLLECTION_NAME = "physicsnemo_docs"
    PHYSNEMO_CODE_COLLECTION_NAME = "physicsnemo_code"
    DEFAULT_URI = "http://localhost:19530"

    parser = argparse.ArgumentParser()
    # (Argument parsing remains identical to your original code)
    url_group = parser.add_argument_group('URL sources')
    url_group.add_argument("--urls", default=[], action="append")
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
        ))
    else:
        # Web scraping logic
        collection_name = args.collection_name or PHYSNEMO_COLLECTION_NAME
        if args.urls: urls = args.urls
        else:
            start_url = args.start_url or PHYSNEMO_START_URL
            base_url = args.base_url or PHYSNEMO_BASE_URL
            if args.crawl: urls = crawl_urls(start_url, base_url_filter=base_url, limit=args.limit)
            else: urls = discover_urls(start_url, args.sitemap, base_url, args.limit)
            
        if args.list_only:
            for u in urls: print(f"  - {u}")
        else:
            drop_collection_if_requested(collection_name, args.milvus_uri, args.reset_collection)
            asyncio.run(main(urls=urls, milvus_uri=args.milvus_uri, collection_name=collection_name, clean_cache=args.clean_cache))