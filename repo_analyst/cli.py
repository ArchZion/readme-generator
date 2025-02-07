import os
import re
import json
import click
import openai
import hashlib
from pathlib import Path
from collections import defaultdict

try:
    import tiktoken
except ImportError:
    tiktoken = None

MODEL_NAME = "gpt-4o"

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
    ".git", ".venv", "node_modules", "__pycache__", ".terraform", ".vscode",
    "package-lock.json"
]


@click.command()
@click.option("--directory", "-d", default=".",
              help="Directory of the repository to analyze (default: current directory).")
@click.option("--output-file", "-o", default="README.md",
              help="Output filename for the generated README (default: README.md).")
@click.option("--existing-readme-file", default=None,
              help="Path to an existing README to merge. If not provided, defaults to the output-file path.")
@click.option("--template-file", default="readme-Readme Generator.template",
              help="Path to a custom template file with headers or instructions.")
@click.option("--append/--overwrite", default=False,
              help="Append to existing README instead of overwriting (default: overwrite).")
@click.option("--max-tokens", default=1500,
              help="Max tokens for the final combined summary (default: 1500).")
@click.option("--directory-summary/--no-directory-summary", "dir_summary",
              default=True,
              help="Enable or disable directory-level summaries (default: enabled).")
@click.option("--temperature", default=0.3,
              help="Temperature for OpenAI calls (0.0 => deterministic, 1.0 => creative).")
@click.option("--force", is_flag=True,
              help="Force re-generation even if the code digest hasn't changed.")
@click.option("--ignore", multiple=True,
              help="Ignore paths or substrings (e.g. '.git', '.vscode'). Can be repeated.")
@click.option("--ignore-ext", multiple=True,
              help="Ignore file extensions (e.g. '.png', '.exe'). Can be repeated.")
@click.option("--digest-file", default="readme.md5s",
              help="Where to store/load MD5 digests. Default: readme.md5s")
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
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        click.echo("Error: The environment variable OPENAI_API_KEY is not set.")
        return

    # Combine default patterns + user-specified ignores
    ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
    if ignore:
        ignore_patterns.extend(ignore)

    # 1) Load old digests from separate file
    old_repo_digest, old_dir_digests, old_file_digests = load_digests(digest_file)

    # 2) Compute new digests
    new_file_digests = compute_file_digests(directory, ignore_patterns, ignore_ext)
    new_dir_digests = compute_directory_digests(new_file_digests)
    new_repo_digest = compute_repo_digest_from_file_digests(new_file_digests)

    # If no changes in entire repo => skip
    if (not force) and (old_repo_digest == new_repo_digest) and (old_repo_digest is not None):
        click.echo("No code changes detected (repo digest matches). Skipping README generation.")
        return

    # read optional repo.intro
    repo_intro = read_repo_intro(directory)

    # detect Tools from file extensions (ignoring certain dirs if needed)
    detected_tools = detect_tools(directory, ignore_patterns, ignore_ext)

    # gather directories -> file paths
    dir_to_files = gather_files_by_directory(directory, ignore_patterns, ignore_ext)
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
                ds = summarize_directory(dir_path, file_summaries, temperature=temperature)
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
    Path(digest_file).write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(f"Saved new digests to {digest_file}")


###############################################################################
# 2) Compute new digests
###############################################################################

def compute_file_digests(directory, ignore_patterns, ignore_ext):
    file_digests = {}
    for root, dirs, files in os.walk(directory):
        # skip if pattern is in 'root'
        if any(ignored in root for ignored in ignore_patterns):
            continue

        for file_name in files:
            if any(file_name.endswith(ext) for ext in ignore_ext):
                continue
            if any(ignored in file_name for ignored in ignore_patterns):
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
        if any(ignored in root for ignored in ignore_patterns):
            continue
        for file_name in files:
            if any(file_name.endswith(ext) for ext in ignore_ext):
                continue
            if any(ignored in file_name for ignored in ignore_patterns):
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
        if any(ignored in root for ignored in ignore_patterns):
            continue

        for file_name in files:
            if any(file_name.endswith(ext) for ext in ignore_ext):
                continue
            if any(ignored in file_name for ignored in ignore_patterns):
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

def summarize_file_and_collect_annotations(file_path, temperature=0.3):
    try:
        text = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return (f"Could not read {file_path}: {e}", [])

    annotated_lines = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if "!important" in line:
            annotated_lines.append((i, line.strip()))

    text_chunks = chunk_text(text, max_chunk_size=1200)
    chunk_summaries = []
    for idx, chunk in enumerate(text_chunks):
        snippet_summary = call_openai_chat(
            system_prompt="You are a code summarizer. Summarize the given file content briefly.",
            user_prompt=f"File chunk {idx+1}:\n\n{chunk}\n\nSummarize it concisely.",
            max_tokens=300,
            temperature=temperature
        )
        chunk_summaries.append(f"Chunk {idx+1} summary: {snippet_summary}")

    combined_text = "\n".join(chunk_summaries)
    final_file_summary = call_openai_chat(
        system_prompt="You are a code summarizer. Combine partial summaries into one final summary.",
        user_prompt=f"Combine these partial summaries into a single, concise summary:\n\n{combined_text}",
        max_tokens=300,
        temperature=temperature
    )
    return (final_file_summary, annotated_lines)


###############################################################################
# Summarize directory
###############################################################################

def summarize_directory(dir_path, file_summaries, temperature=0.3):
    summary_list = []
    for fpath, summary in file_summaries.items():
        summary_list.append(f"File: {fpath.name}\nSummary: {summary}\n")

    combined_file_summaries = "\n".join(summary_list)
    dir_summary = call_openai_chat(
        system_prompt="You are a code summarizer. Summarize a directory based on file summaries.",
        user_prompt=(
            f"Directory: {dir_path}\n\n"
            f"Here are the file summaries:\n\n{combined_file_summaries}\n\n"
            "Please provide a concise overview of this directory's purpose and logic."
        ),
        max_tokens=500,
        temperature=temperature
    )
    return dir_summary


###############################################################################
# Summarize entire repo => final README
###############################################################################

def generate_final_readme(
    repo_intro,
    tools,
    directory_summaries,
    annotated_lines_map,
    file_summaries=None,
    max_tokens=1500,
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
    annotated_summary = summarize_annotated_lines(annotated_lines_map, temperature=temperature)

    # Tools instructions
    tools_block = build_tools_install_instructions(sorted(tools), temperature=temperature)

    # The final prompt merges the existing README with the new analysis, plus a custom template
    user_prompt = f"""
    We have a user-provided template (or custom instructions):
    {template_content}

    We have an existing README with the following content:
    {existing_readme}

    Below is new analysis of the code base:

    User Intro:
    {repo_intro}

    Tools found + install instructions:
    {tools_block}

    Directory Summaries:
    {combined_dir_summaries}

    File Summaries (if directory summaries disabled):
    {all_file_summaries}

    Custom-Annotated Lines Summary:
    {annotated_summary}

    Code Digest: {repo_digest or ''}

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

    final_readme = call_openai_chat(
        system_prompt="You are a helpful assistant that merges existing content, a template, and new analysis.",
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

def summarize_annotated_lines(annotated_lines_map, temperature=0.3):
    if not annotated_lines_map:
        return "No custom annotations found."

    lines_text = []
    for fp, lines in annotated_lines_map.items():
        if not lines:
            continue
        line_block = "\n".join(f"Line {line_num}: {line_content}" for (line_num, line_content) in lines)
        lines_text.append(f"File: {fp}\n{line_block}\n")

    combined_text = "\n".join(lines_text)
    annotated_summary = call_openai_chat(
        system_prompt="You are analyzing custom annotated lines in the code.",
        user_prompt=(
            "Below are lines containing '!important' with file paths and line numbers. "
            "Please summarize what they indicate about the code:\n\n"
            f"{combined_text}"
        ),
        max_tokens=500,
        temperature=temperature
    )
    return annotated_summary


###############################################################################
# Tools Installation
###############################################################################

def build_tools_install_instructions(tools_list, temperature=0.3):
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
            instructions = generate_install_guide_for(tool, temperature=temperature)
            lines.append(instructions)
            lines.append("")  # blank line

    return "\n".join(lines)


def generate_install_guide_for(tool_name, temperature=0.3):
    """
    Use GPT to produce short installation instructions for 'tool_name'
    on Windows, Mac, and Ubuntu. We'll do a single call.
    """
    system_prompt = (
        "You are a helpful assistant that provides brief, step-by-step installation instructions "
        "for different tools on Windows, Mac, and Ubuntu."
    )
    user_prompt = (
        f"Give me concise instructions on how to install '{tool_name}' "
        "on Windows, Mac, and Ubuntu. Keep it short and clear."
    )

    response = call_openai_chat(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=300,
        temperature=temperature
    )
    return response


###############################################################################
# OpenAI call with usage logging
###############################################################################

def call_openai_chat(system_prompt, user_prompt, max_tokens=500, temperature=0.3):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = openai.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        usage = response.usage
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_tokens = prompt_tokens + completion_tokens

        click.echo(f" - API call used {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total tokens.")
        return response.choices[0].message.content.strip()
    except Exception as e:
        click.echo("Error calling OpenAI API:")
        click.echo(str(e))
        return "(Error or empty response)"


###############################################################################
# Text Chunking
###############################################################################

def chunk_text(text, max_chunk_size=1200):
    if not tiktoken:
        chunk_len = max_chunk_size * 2
        return [text[i : i+chunk_len] for i in range(0, len(text), chunk_len)]

    # We just pick a known encoding, ignoring MODEL_NAME
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)

    chunks = []
    start = 0
    while start < len(tokens):
        end = start + max_chunk_size
        token_chunk = tokens[start:end]
        chunk_text_ = enc.decode(token_chunk)
        chunks.append(chunk_text_)
        start = end
    return chunks
