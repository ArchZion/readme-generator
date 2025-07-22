import os
import re
import json
import click
from google import genai
import hashlib
import fnmatch
from pathlib import Path
from collections import defaultdict

try:
    import tiktoken
except ImportError:
    tiktoken = None

MODEL_NAME = "gemini-2.5-flash"

###############################################################################
# Pattern matching utilities
###############################################################################

def should_ignore_path(path_str, ignore_patterns):
    """
    Check if a path should be ignored based on ignore patterns.
    Supports both exact matches and wildcard patterns.
    """
    path_parts = Path(path_str).parts

    for pattern in ignore_patterns:
        # Handle wildcard patterns
        if '*' in pattern or '?' in pattern:
            if fnmatch.fnmatch(path_str, pattern):
                return True
            # Also check individual path parts
            for part in path_parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        else:
            # Simple substring matching for non-wildcard patterns
            if pattern in path_str:
                return True

    return False

###############################################################################
# Directory management
###############################################################################

def ensure_docs_directory(directory):
    """
    Ensure the docs/readme-generator directory exists in the target directory.
    Returns the path to the docs directory.
    """
    docs_dir = Path(directory) / "docs" / "readme-generator"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir

def get_docs_path(directory, filename):
    """
    Get the full path for a file in the docs/readme-generator directory.
    """
    docs_dir = ensure_docs_directory(directory)
    return docs_dir / filename

def load_custom_ignore_patterns(directory):
    """
    Load custom ignore patterns from .readme-generator.ignore file.
    Returns a list of patterns, or empty list if file doesn't exist.
    """
    ignore_file = get_docs_path(directory, ".readme-generator.ignore")

    if not ignore_file.exists():
        return []

    try:
        patterns = []
        with open(ignore_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    patterns.append(line)
        return patterns
    except Exception as e:
        click.echo(f"Warning: Could not read ignore file {ignore_file}: {str(e)}")
        return []

###############################################################################
# Predefined installation guides
###############################################################################
TOOL_INSTALL_GUIDES = {
    "Python": {
        "Windows": "Download and install from https://www.python.org/downloads/ ",
        "Mac": "Use Homebrew: `brew install python3`",
        "Ubuntu": "Use apt: `sudo apt-get update && sudo apt-get install python3`"
    },
    "Terraform": {
        "Windows": "Download from https://developer.hashicorp.com/terraform/downloads",
        "Mac": "Use Homebrew: `brew tap hashicorp/tap && brew install hashicorp/tap/terraform`",
        "Ubuntu": "Use apt: `sudo apt-get update && sudo apt-get install terraform` (or download a .zip from HashiCorp)"
    },
    "Bash/Shell": {
        "Windows": "Use Git Bash or WSL (Windows Subsystem for Linux)",
        "Mac": "Pre-installed by default (bash/zsh)",
        "Ubuntu": "Pre-installed by default"
    },
    "Node.js / JavaScript": {
        "Windows": "Download from https://nodejs.org/en",
        "Mac": "Use Homebrew: `brew install node`",
        "Ubuntu": "Use apt: `sudo apt-get update && sudo apt-get install nodejs npm`"
    },
    "TypeScript": {
        "Windows": "Install Node.js from https://nodejs.org/, then `npm install -g typescript`",
        "Mac": "Install Node.js via Homebrew, then `npm install -g typescript`",
        "Ubuntu": "Install Node.js via apt, then `npm install -g typescript`"
    },
    "Docker": {
        "Windows": "Install Docker Desktop for Windows: https://www.docker.com/products/docker-desktop/",
        "Mac": "Install Docker Desktop for Mac: https://www.docker.com/products/docker-desktop/",
        "Ubuntu": "Follow https://docs.docker.com/engine/install/ubuntu/"
    }
}

###############################################################################
# Default ignore patterns
###############################################################################
DEFAULT_IGNORE_PATTERNS = [
    # Version control
    ".git", ".svn", ".hg",

    # Virtual environments and package managers
    ".venv", "venv", "env", "ENV", "node_modules", ".npm", ".yarn",

    # Python
    "__pycache__", "*.pyc", "*.pyo", "*.pyd", ".pytest_cache", ".coverage",

    # IDE and editor files
    ".vscode", ".idea", ".vs", "*.swp", "*.swo", "*~", ".DS_Store",

    # Build and cache directories
    "build", "dist", "target", "out", ".gradle", ".mvn", "bin", "obj",

    # Package lock files
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",

    # Infrastructure and deployment
    ".terraform", ".terraform.lock.hcl", "terraform.tfstate*",

    # Logs and temporary files
    "*.log", "logs", "tmp", "temp", ".tmp",

    # Documentation and config files that don't need summarization
    ".dockerignore", ".gitignore", ".gitattributes", ".editorconfig",
    "Makefile", "CMakeLists.txt", "*.cmake",

    # Configuration files
    ".env", ".env.*", "config.json", "settings.json",

    # Database files
    "*.db", "*.sqlite", "*.sqlite3",

    # Backup files
    "*.bak", "*.backup", "*.old",

    # OS generated files
    "Thumbs.db", ".DS_Store", ".Trashes",

    # Readme generator's own files
    "docs/readme-generator", "readme.md5s", "readme-generator.template"
]

###############################################################################
# Default ignore extensions
###############################################################################
DEFAULT_IGNORE_EXTENSIONS = [
    # Binary files
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o", ".a",

    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".ico", ".webp",

    # Videos and audio
    ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mp3", ".wav", ".flac",

    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",

    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",

    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",

    # Compiled files
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",

    # Data files
    ".csv", ".tsv", ".json", ".xml",

    # Logs and temporary
    ".log", ".tmp", ".temp", ".cache",

    # OS files
    ".DS_Store", "Thumbs.db"
]


@click.command()
@click.option("--directory", "-d", default=".",
              help="Directory of the repository to analyze (default: current directory).")
@click.option("--output-file", "-o", default="README.md",
              help="Output filename for the generated README (default: README.md).")
@click.option("--existing-readme-file", default=None,
              help="Path to an existing README to merge. If not provided, defaults to the output-file path.")
@click.option("--template-file", default=None,
              help="Path to a custom template file with headers or instructions. Defaults to docs/readme-generator/readme-generator.template")
@click.option("--append/--overwrite", default=False,
              help="Append to existing README instead of overwriting (default: overwrite).")
@click.option("--max-tokens", default=8000,
              help="Max tokens for the final combined summary (default: 8000).")
@click.option("--directory-summary/--no-directory-summary", "dir_summary",
              default=True,
              help="Enable or disable directory-level summaries (default: enabled).")
@click.option("--temperature", default=0.3,
              help="Temperature for Gemini calls (0.0 => deterministic, 1.0 => creative).")
@click.option("--force", is_flag=True,
              help="Force re-generation even if the code digest hasn't changed.")
@click.option("--ignore", multiple=True,
              help="Ignore paths or substrings (e.g. '.git', '.vscode'). Can be repeated.")
@click.option("--ignore-ext", multiple=True,
              help="Ignore file extensions (e.g. '.png', '.exe'). Can be repeated.")
@click.option("--digest-file", default=None,
              help="Where to store/load MD5 digests. Default: docs/readme-generator/readme.md5s")
def main(directory,
         output_file,
         existing_readme_file,
         template_file,
         append,
         max_tokens,
         dir_summary,
         temperature,
         force,
         ignore,
         ignore_ext,
         digest_file):
    """
    Analyzes the code in the specified directory (multi-step),
    merges with an existing README (if any), and uses a custom template file
    containing extra headers or instructions.

    - Summarizes each file, skipping unchanged or ignored files/folders.
    - Summarizes each directory (optional).
    - Summarizes the entire repo.
    - Stores digests in a separate JSON file (readme.md5s by default) to skip
      regeneration if nothing changes.
    - Collects lines with !important.
    - Generates tool installation instructions.
    - If an existing README is found, merges it into the final doc.
    - Also loads a user-provided template for extra sections or instructions.
    """
    # Check for Gemini API key (try both environment variable names)
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        click.echo("Error: The environment variable GEMINI_API_KEY or GOOGLE_API_KEY is not set.")
        click.echo("Please set it with: export GEMINI_API_KEY='your-api-key'")
        click.echo("Get your API key from: https://makersuite.google.com/app/apikey")
        return

    # Validate API key format
    if not api_key.startswith("AI"):
        click.echo("Warning: API key doesn't start with 'AI'. This might indicate an invalid key format.")
        click.echo("Valid Gemini API keys typically start with 'AI'.")

    # Initialize Gemini client with new format
    try:
        client = genai.Client()
        click.echo("Gemini client initialized successfully.")
    except Exception as e:
        click.echo(f"Error initializing Gemini client: {str(e)}")
        return

    # Test Gemini connection with a simple call
    try:
        click.echo("Testing Gemini API connection...")
        test_response = call_gemini_chat(
            client,
            system_prompt="Test",
            user_prompt="Hello",
            max_tokens=50,
            temperature=0.1
        )
        if test_response == "(Response blocked by safety filters)":
            click.echo("Warning: Gemini is blocking even simple test calls. This may indicate API issues.")
            click.echo("Possible causes:")
            click.echo("1. API key issues or quota exceeded")
            click.echo("2. Gemini service problems")
            click.echo("3. Network/connectivity issues")
            click.echo("4. Model availability issues")
        else:
            click.echo("Gemini API connection test successful.")
    except Exception as e:
        click.echo(f"Warning: Gemini test call failed: {str(e)}")
        click.echo("This indicates a fundamental API issue.")

    # Set up default paths in docs directory
    if template_file is None:
        template_file = str(get_docs_path(directory, "readme-generator.template"))

    if digest_file is None:
        digest_file = str(get_docs_path(directory, "readme.md5s"))

        # Load custom ignore patterns from file
    custom_ignore_patterns = load_custom_ignore_patterns(directory)
    if custom_ignore_patterns:
        click.echo(f"Loaded {len(custom_ignore_patterns)} custom ignore patterns from .readme-generator.ignore")

    # Combine default patterns + custom patterns + user-specified ignores
    ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
    ignore_patterns.extend(custom_ignore_patterns)
    if ignore:
        ignore_patterns.extend(ignore)

    # Combine default extensions + user-specified ignores
    ignore_extensions = list(DEFAULT_IGNORE_EXTENSIONS)
    if ignore_ext:
        ignore_extensions.extend(ignore_ext)

    # 1) Load old digests from separate file
    old_repo_digest, old_dir_digests, old_file_digests = load_digests(digest_file)

    # 2) Compute new digests
    new_file_digests = compute_file_digests(directory, ignore_patterns, ignore_extensions)
    new_dir_digests = compute_directory_digests(new_file_digests)
    new_repo_digest = compute_repo_digest_from_file_digests(new_file_digests)

    # If no changes in entire repo => skip
    if (not force) and (old_repo_digest == new_repo_digest) and (old_repo_digest is not None):
        click.echo("No code changes detected (repo digest matches). Skipping README generation.")
        return

    # read optional repo.intro
    repo_intro = read_repo_intro(directory)

    # detect Tools from file extensions (ignoring certain dirs if needed)
    detected_tools = detect_tools(directory, ignore_patterns, ignore_extensions)

    # gather directories -> file paths
    dir_to_files = gather_files_by_directory(directory, ignore_patterns, ignore_extensions)
    if not dir_to_files and not repo_intro.strip():
        click.echo("No textual files found and no repo.intro content. Aborting.")
        return

    # Summarize files
    click.echo("Summarizing files (multi-step) ...")
    directory_file_summaries = {}
    annotated_lines_map = defaultdict(list)

    for dir_path, file_paths in dir_to_files.items():
        file_summaries = {}
        for fpath in file_paths:
            old_digest = old_file_digests.get(str(fpath), None)
            new_digest = new_file_digests.get(str(fpath), None)

            # skip if unchanged
            if not force and old_digest == new_digest and old_digest is not None:
                click.echo(f" - No changes in {fpath}, skipping file summary.")
                summary = "(Unchanged since last analysis)"
                annotated_lines = []
            else:
                summary, annotated_lines = summarize_file_and_collect_annotations(
                    client,
                    fpath,
                    temperature=temperature
                )
                click.echo(f" - Summarized file {fpath}")

            file_summaries[fpath] = summary
            if annotated_lines:
                annotated_lines_map[fpath].extend(annotated_lines)

        directory_file_summaries[dir_path] = file_summaries

    # Summarize directories (if enabled)
    click.echo("\nSummarizing directories ...")
    dir_summaries = {}
    if dir_summary:
        for dir_path, file_summaries in directory_file_summaries.items():
            old_d_digest = old_dir_digests.get(str(dir_path), None)
            new_d_digest = new_dir_digests.get(str(dir_path), None)

            if not force and (old_d_digest == new_d_digest) and old_d_digest is not None:
                click.echo(f" - No changes in directory {dir_path}, skipping directory summary.")
                dir_summaries[dir_path] = "(Unchanged since last analysis)"
            else:
                ds = summarize_directory(client, dir_path, file_summaries, temperature=temperature)
                dir_summaries[dir_path] = ds
                click.echo(f" - Summarized directory {dir_path}")
    else:
        dir_summaries = {}

    # 3) If there's an existing README, or a separate user-provided file
    #    for "existing_readme_file", load it so we can merge content
    if not existing_readme_file:
        # If not explicitly provided, default to the same as output_file
        existing_readme_file = output_file

    existing_readme_content = ""
    existing_readme_path = Path(existing_readme_file)
    if existing_readme_path.exists():
        try:
            existing_readme_content = existing_readme_path.read_text(encoding="utf-8")
        except Exception:
            existing_readme_content = ""

    # 4) Load template file (if it exists)
    template_content = ""
    template_path = Path(template_file)
    if template_path.exists():
        try:
            template_content = template_path.read_text(encoding="utf-8")
        except Exception:
            template_content = ""

    # Summarize final repo + merge with existing README + template
    click.echo("\nGenerating final repo summary ...")
    final_repo_readme = generate_final_readme(
        client,
        repo_intro=repo_intro,
        tools=detected_tools,
        directory_summaries=dir_summaries,
        annotated_lines_map=annotated_lines_map,
        file_summaries=directory_file_summaries if not dir_summary else None,
        max_tokens=max_tokens,
        temperature=temperature,
        repo_digest=new_repo_digest,
        existing_readme=existing_readme_content,
        template_content=template_content
    )

    # Write or append README
    mode = "a" if append else "w"
    with open(output_file, mode, encoding="utf-8") as f:
        if not append:
            pass  # Overwrite scenario
        else:
            f.write("\n\n## AI-Generated Repository Analysis\n\n")

        f.write(final_repo_readme)

    click.echo(f"\nREADME has been {'appended' if append else 'updated'} at: {output_file}")

    # 5) Save new digests to `digest_file`
    save_digests(digest_file, new_repo_digest, new_dir_digests, new_file_digests)


###############################################################################
# 1) Load & Save Digests from a separate JSON file
###############################################################################

def load_digests(digest_file):
    """
    Load old_repo_digest, old_dir_digests, old_file_digests from a JSON file (digest_file).
    If the file doesn't exist or is invalid, return (None, {}, {}).
    Example JSON structure:
    {
      "repo_digest": "...",
      "directory_digests": { "path/to/dir": "...", ... },
      "file_digests": { "path/to/file": "...", ... }
    }
    """
    digest_path = Path(digest_file)
    if not digest_path.exists():
        return None, {}, {}

    try:
        data = json.loads(digest_path.read_text(encoding="utf-8"))
        return (
            data.get("repo_digest"),
            data.get("directory_digests", {}),
            data.get("file_digests", {})
        )
    except Exception:
        return None, {}, {}

def save_digests(digest_file, repo_digest, directory_digests, file_digests):
    """
    Save the new repo_digest, directory_digests, file_digests to a JSON file (digest_file).
    """
    data = {
        "repo_digest": repo_digest,
        "directory_digests": directory_digests,
        "file_digests": file_digests
    }
    digest_path = Path(digest_file)
    # Ensure parent directory exists
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(f"Saved new digests to {digest_file}")


###############################################################################
# 2) Compute new digests
###############################################################################

def compute_file_digests(directory, ignore_patterns, ignore_ext):
    file_digests = {}
    for root, dirs, files in os.walk(directory):
        # skip if pattern is in 'root'
        if should_ignore_path(root, ignore_patterns):
            continue

        for file_name in files:
            # Check file extensions
            if any(file_name.endswith(ext) for ext in ignore_ext):
                continue

            # Check file name patterns
            if should_ignore_path(file_name, ignore_patterns):
                continue

            if file_name == "repo.intro":
                continue

            file_path = Path(root) / file_name
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            md5_hash = hashlib.md5()
            md5_hash.update(content.encode("utf-8", errors="ignore"))
            rel_path = os.path.relpath(str(file_path), directory)
            md5_hash.update(rel_path.encode("utf-8", errors="ignore"))

            file_digests[str(file_path)] = md5_hash.hexdigest()
    return file_digests

def compute_directory_digests(file_digests):
    dir_map = defaultdict(list)
    for fpath, fhash in file_digests.items():
        dpath = str(Path(fpath).parent)
        dir_map[dpath].append(fhash)

    dir_digests = {}
    for dpath, hashes in dir_map.items():
        md5_hash = hashlib.md5()
        for h in sorted(hashes):
            md5_hash.update(h.encode("utf-8"))
        dir_digests[dpath] = md5_hash.hexdigest()

    return dir_digests

def compute_repo_digest_from_file_digests(file_digests):
    md5_hash = hashlib.md5()
    for path, digest in sorted(file_digests.items()):
        md5_hash.update(digest.encode("utf-8"))
    return md5_hash.hexdigest()


###############################################################################
# 3) read_repo_intro
###############################################################################

def read_repo_intro(directory):
    intro_path = Path(directory) / "repo.intro"
    if intro_path.exists() and intro_path.is_file():
        try:
            return intro_path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


###############################################################################
# 4) detect_tools
###############################################################################

def detect_tools(directory, ignore_patterns, ignore_ext):
    tools = set()
    for root, dirs, files in os.walk(directory):
        if should_ignore_path(root, ignore_patterns):
            continue
        for file_name in files:
            if any(file_name.endswith(ext) for ext in ignore_ext):
                continue
            if should_ignore_path(file_name, ignore_patterns):
                continue

            if file_name.endswith(".py"):
                tools.add("Python")
            elif file_name.endswith(".tf"):
                tools.add("Terraform")
            elif file_name.endswith(".sh"):
                tools.add("Bash/Shell")
            elif file_name.endswith(".js"):
                tools.add("Node.js / JavaScript")
            elif file_name.endswith(".ts"):
                tools.add("TypeScript")
            elif file_name.endswith("Dockerfile"):
                tools.add("Docker")
    return tools


###############################################################################
# 5) gather_files_by_directory
###############################################################################

def gather_files_by_directory(directory, ignore_patterns, ignore_ext):
    dir_map = defaultdict(list)
    for root, dirs, files in os.walk(directory):
        if should_ignore_path(root, ignore_patterns):
            continue

        for file_name in files:
            if any(file_name.endswith(ext) for ext in ignore_ext):
                continue
            if should_ignore_path(file_name, ignore_patterns):
                continue

            if file_name == "repo.intro":
                continue

            file_path = Path(root) / file_name
            try:
                _ = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            dir_map[Path(root)].append(file_path)
    return dict(dir_map)


###############################################################################
# Summarize files & collect !important
###############################################################################

def summarize_file_and_collect_annotations(client, file_path, temperature=0.3):
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return (f"Could not read {file_path}: {e}", [])

    annotated_lines = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if "!important" in line:
            annotated_lines.append((i, line.strip()))

    # Skip very large files or files that might cause issues
    if len(text) > 50000:  # Skip files larger than 50KB
        return (f"File {file_path.name}: Large file ({len(lines)} lines) - skipped for analysis", annotated_lines)

    text_chunks = chunk_text(text, max_chunk_size=16000)
    chunk_summaries = []

    # Process chunks with error handling
    for idx, chunk in enumerate(text_chunks):
        try:
            snippet_summary = call_gemini_chat(
                client,
                system_prompt="Summarize this code content.",
                user_prompt=f"Code:\n{chunk}\n\nSummary:",
                max_tokens=15000,
                temperature=temperature
            )
            chunk_summaries.append(f"Chunk {idx+1} summary: {snippet_summary}")
        except Exception as e:
            click.echo(f"Warning: Failed to summarize chunk {idx+1} of {file_path}: {str(e)}")
            chunk_summaries.append(f"Chunk {idx+1} summary: (Failed to summarize)")

    # If all chunks failed, return a basic summary
    if not chunk_summaries or all("Failed to summarize" in summary for summary in chunk_summaries):
        return (f"File {file_path.name}: Code file with {len(lines)} lines", annotated_lines)

    combined_text = "\n".join(chunk_summaries)

    try:
        final_file_summary = call_gemini_chat(
            client,
            system_prompt="Combine these summaries into one.",
            user_prompt=f"Summaries:\n{combined_text}\n\nCombined summary:",
            max_tokens=25000,
            temperature=temperature
        )
    except Exception as e:
        click.echo(f"Warning: Failed to combine summaries for {file_path}: {str(e)}")
        # Fallback to a simple summary
        final_file_summary = f"File {file_path.name}: Contains {len(lines)} lines of code"

    return (final_file_summary, annotated_lines)


###############################################################################
# Summarize directory
###############################################################################

def summarize_directory(client, dir_path, file_summaries, temperature=0.3):
    summary_list = []
    for fpath, summary in file_summaries.items():
        summary_list.append(f"File: {fpath.name}\nSummary: {summary}\n")

    combined_file_summaries = "\n".join(summary_list)

    try:
        dir_summary = call_gemini_chat(
            client,
            system_prompt="Summarize this directory.",
            user_prompt=(
                f"Directory: {dir_path}\n"
                f"Files:\n{combined_file_summaries}\n\n"
                f"Summary:"
            ),
            max_tokens=1000,
            temperature=temperature
        )
    except Exception as e:
        click.echo(f"Warning: Failed to summarize directory {dir_path}: {str(e)}")
        # Fallback to a simple summary
        file_count = len(file_summaries)
        dir_summary = f"Directory {dir_path.name}: Contains {file_count} files"

    return dir_summary


###############################################################################
# Summarize entire repo => final README
###############################################################################

def generate_final_readme(
    client,
    repo_intro,
    tools,
    directory_summaries,
    annotated_lines_map,
    file_summaries=None,
    max_tokens=30000,
    temperature=0.3,
    repo_digest=None,
    existing_readme="",
    template_content=""
):
    """
    Merge existing README content, new analysis, and a custom template file (if provided).
    """
    # Summarize directories
    dir_summary_list = []
    for dpath, summary in directory_summaries.items():
        dir_summary_list.append(f"Directory: {dpath}\n{summary}\n")
    combined_dir_summaries = "\n".join(dir_summary_list) if dir_summary_list else ""

    # Summarize file-level
    file_summary_list = []
    if file_summaries:
        for dpath, fsums in file_summaries.items():
            for fp, fsum in fsums.items():
                file_summary_list.append(f"- {fp.name}: {fsum}")
    all_file_summaries = "\n".join(file_summary_list)

    # Summarize custom-annotated lines
    annotated_summary = summarize_annotated_lines(client, annotated_lines_map, temperature=temperature)

    # Tools instructions
    tools_block = build_tools_install_instructions(client, sorted(tools), temperature=temperature)

    # Dynamically build the analysis block to avoid empty sections
    analysis_block_parts = []
    if repo_intro:
        analysis_block_parts.append(f"User Intro:\n{repo_intro}")

    if tools_block != "No tools detected.":
        analysis_block_parts.append(f"Tools found + install instructions:\n{tools_block}")

    if combined_dir_summaries:
        analysis_block_parts.append(f"Directory Summaries:\n{combined_dir_summaries}")

    if all_file_summaries:
        analysis_block_parts.append(f"File Summaries (if directory summaries disabled):\n{all_file_summaries}")

    if annotated_summary and annotated_summary != "No custom annotations found.":
        analysis_block_parts.append(f"Custom-Annotated Lines Summary:\n{annotated_summary}")

    if repo_digest:
        analysis_block_parts.append(f"Code Digest: {repo_digest}")

    analysis_block = "\n\n".join(analysis_block_parts)

    # The final prompt merges the existing README with the new analysis, plus a custom template
    user_prompt = f"""
    We have a user-provided template (or custom instructions):
    {template_content}

    We have an existing README with the following content:
    {existing_readme}

    Below is new analysis of the code base:
    {analysis_block}

    **Your Task**:
    - **Preserve** unique sections from the existing README.
    - **Incorporate** the user-provided template headings.
    - **Add** the new analysis (intro, tools, directory/file summaries, annotated code) into the final structure.

    Preserve any unique sections from the original README and blend them with the
    updated logic, tools, structure, and template. The final README should incorporate
    the template's headings and instructions, plus the new analysis.

    **Important**: Produce **valid Markdown** **without** enclosing the entire output in triple backticks.
    Keep it under {max_tokens} tokens if possible, and be concise yet informative.
    """

    final_readme = call_gemini_chat(
        client,
        system_prompt="You are a technical documentation assistant that creates comprehensive README files by merging existing content, templates, and code analysis.",
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature
    )

    # if final_readme.startswith("```"):
    #     # Strip off leading triple-backtick lines
    #     final_readme = re.sub(r"^```[a-zA-Z0-9]*\n?", "", final_readme)
    # if final_readme.endswith("```"):
    #     # Strip off trailing triple-backtick
    #     final_readme = re.sub(r"```$", "", final_readme)

    return final_readme


###############################################################################
# Summarize annotated lines
###############################################################################

def summarize_annotated_lines(client, annotated_lines_map, temperature=0.3):
    if not annotated_lines_map:
        return "No custom annotations found."

    lines_text = []
    for fp, lines in annotated_lines_map.items():
        if not lines:
            continue
        line_block = "\n".join(f"Line {line_num}: {line_content}" for (line_num, line_content) in lines)
        lines_text.append(f"File: {fp}\n{line_block}\n")

    combined_text = "\n".join(lines_text)
    annotated_summary = call_gemini_chat(
        client,
        system_prompt="You are a technical documentation assistant analyzing code annotations.",
        user_prompt=(
            "Below are lines containing '!important' with file paths and line numbers. "
            "Please provide a technical summary of what these annotations indicate:\n\n"
            f"{combined_text}"
        ),
        max_tokens=2500,
        temperature=temperature
    )
    return annotated_summary


###############################################################################
# Tools Installation
###############################################################################

def build_tools_install_instructions(client, tools_list, temperature=0.3):
    """
    Build installation instructions for each tool.
    If a tool is in TOOL_INSTALL_GUIDES, use that data.
    Otherwise, generate instructions by calling GPT.
    """
    if not tools_list:
        return "No tools detected."

    lines = []
    for tool in tools_list:
        lines.append(f"### {tool}")

        guide = TOOL_INSTALL_GUIDES.get(tool)
        if guide:
            # We have a predefined entry
            win = guide.get("Windows", "N/A")
            mac = guide.get("Mac", "N/A")
            ubuntu = guide.get("Ubuntu", "N/A")

            lines.append(f"**Windows**: {win}")
            lines.append(f"**Mac**: {mac}")
            lines.append(f"**Ubuntu**: {ubuntu}\n")
        else:
            # Unknown tool => generate instructions on the fly
            instructions = generate_install_guide_for(client, tool, temperature=temperature)
            lines.append(instructions)
            lines.append("")  # blank line

    return "\n".join(lines)


def generate_install_guide_for(client, tool_name, temperature=0.3):
    """
    Use GPT to produce short installation instructions for 'tool_name'
    on Windows, Mac, and Ubuntu. We'll do a single call.
    """
    system_prompt = (
        "You are a technical documentation assistant that provides installation instructions "
        "for development tools on different operating systems."
    )
    user_prompt = (
        f"Provide concise installation instructions for '{tool_name}' "
        "on Windows, Mac, and Ubuntu. Focus on technical steps and commands."
    )

    response = call_gemini_chat(
        client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=800,
        temperature=temperature
    )
    return response


###############################################################################
# Gemini call with usage logging and robust error handling
###############################################################################

def call_gemini_chat(client, system_prompt, user_prompt, max_tokens=10000, temperature=0.3):
    """
    Call Gemini API with robust error handling and token limit compliance.
    Uses the new client format from the Gemini API documentation.

    Gemini 2.5 Flash limits:
    - Input: 1,048,576 tokens
    - Output: 65,536 tokens
    """
    model_name = MODEL_NAME

    # Combine system and user prompts for Gemini
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    # Validate input length (rough estimation: 1 token ≈ 4 characters)
    input_length = len(full_prompt)
    estimated_tokens = input_length // 4

    if estimated_tokens > 1000000:  # Leave some buffer for safety
        click.echo(f"Warning: Input may exceed token limit. Estimated tokens: {estimated_tokens}")
        # Truncate if necessary
        max_chars = 4000000  # ~1M tokens * 4 chars
        if len(full_prompt) > max_chars:
            full_prompt = full_prompt[:max_chars] + "\n\n[Content truncated due to length]"
            click.echo(" - Input truncated to comply with token limits")

    # Ensure output token limit compliance
    if max_tokens > 60000:  # Leave buffer for Gemini 2.5 Flash (65,535 limit)
        max_tokens = 60000
        click.echo(f" - Output token limit adjusted to {max_tokens} to comply with Gemini limits")

    try:
        # Generate content using new client format
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            }
        )

        # Check for response blocks and finish reasons
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.finish_reason == "SAFETY" or candidate.finish_reason == 3:
                click.echo(f"Warning: Response blocked by safety filters (model: {model_name})")
                click.echo(f"Debug: Input length: {len(full_prompt)} chars, estimated tokens: {estimated_tokens}")
                click.echo(f"Debug: First 200 chars of input: {full_prompt[:200]}...")
                return "(Response blocked by safety filters)"
            elif candidate.finish_reason == "RECITATION" or candidate.finish_reason == 4:
                click.echo("Warning: Response was recitation (repeated content)")
                return "(Response was recitation)"
            elif candidate.finish_reason == "OTHER" or candidate.finish_reason == 5:
                click.echo("Warning: Response finished with unknown reason")
                return "(Response finished with unknown reason)"
            elif candidate.finish_reason == "MAX_TOKENS" or candidate.finish_reason == 2:
                click.echo("Warning: Response truncated due to token limit")
                # Check if we have any content despite truncation
                if (candidate.content and
                    candidate.content.parts and
                    len(candidate.content.parts) > 0 and
                    candidate.content.parts[0].text):
                    # We have some content, continue with it
                    pass
                else:
                    click.echo("Warning: Truncated response has no content")
                    return "(Truncated response with no content)"
            elif candidate.finish_reason == "STOP" or candidate.finish_reason == 1:
                # Normal completion
                pass
        else:
            click.echo("Warning: No candidates in response")
            return "(No response candidates)"

        # Safely get response text from new API format
        try:
            if (response.candidates and
                len(response.candidates) > 0 and
                response.candidates[0].content and
                response.candidates[0].content.parts and
                len(response.candidates[0].content.parts) > 0):
                result = response.candidates[0].content.parts[0].text.strip()
            else:
                click.echo("Warning: No content in response")
                click.echo(f"Debug: response.candidates={response.candidates}")
                if response.candidates and len(response.candidates) > 0:
                    click.echo(f"Debug: candidate.content={response.candidates[0].content}")
                return "(No content in response)"
        except (AttributeError, IndexError, TypeError) as e:
            click.echo(f"Warning: Could not extract response text: {str(e)}")
            return "(Error extracting response text)"

        # Log successful completion
        click.echo(f" - Gemini API call completed successfully (model: {model_name}, input: ~{estimated_tokens} tokens, output: {len(result)} chars)")

        if not result:
            click.echo("Warning: Empty response received from Gemini")
            return "(Empty response)"

        return result

    except Exception as e:
        click.echo(f"Error calling Gemini API with model {model_name}: {str(e)}")
        return "(Error calling Gemini API)"


###############################################################################
# Text Chunking optimized for Gemini 2.5 Flash
###############################################################################

def chunk_text(text, max_chunk_size=8000):
    """
    Chunk text efficiently for Gemini 2.5 Flash.

    Gemini 2.5 Flash can handle much larger chunks (1M input tokens),
    so we use larger chunk sizes for better context preservation.
    """
    if not text or not text.strip():
        return []

    if not tiktoken:
        # Fallback: use character-based chunking with larger chunks
        chunk_len = max_chunk_size * 4  # ~4 chars per token
        return [text[i : i+chunk_len] for i in range(0, len(text), chunk_len)]

    try:
        # Use cl100k_base encoding (same as GPT-4, good for Gemini)
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)

        # For Gemini 2.5 Flash, we can use much larger chunks
        # Leave buffer for system prompts and other content
        safe_chunk_size = min(max_chunk_size, 800000)  # ~800k tokens max per chunk

        chunks = []
        start = 0
        while start < len(tokens):
            end = start + safe_chunk_size
            token_chunk = tokens[start:end]
            chunk_text_ = enc.decode(token_chunk)
            chunks.append(chunk_text_)
            start = end

        return chunks
    except Exception as e:
        click.echo(f"Warning: Tokenization failed, using character-based chunking: {str(e)}")
        # Fallback to character-based chunking
        chunk_len = max_chunk_size * 4
        return [text[i : i+chunk_len] for i in range(0, len(text), chunk_len)]
