# Python OpenAI - Readme Generator

**Readme Generator** is a Python command-line tool that automatically analyzes your codebase, merges existing documentation, and updates a `README.md` by combining:

1. An existing README (if present)
2. A user-provided template file (optional)
3. A GPT-based analysis of your code (chunking & summarizing)

It detects tools, merges code summaries, and preserves unique sections from the old README.

## Key Features

- **Incremental Updates**: Stores an MD5 digest of your code in a JSON file so it only regenerates if something actually changed (unless `--force` is used).
- **Merges Old README**: If a README already exists, the new content is merged in, preserving unique sections.
- **Custom Template**: Provide a file (`readme-generator.template`) with headings or instructions you want integrated.
- **Tool Detection**: Scans `.py`, `.tf`, `.sh`, `.js`, `.ts`, `Dockerfile`, etc. to generate installation steps. If a tool is unknown, it queries GPT for short instructions.
- **Annotated Lines**: Any line containing `!important` will be specially summarized in a “Custom-Annotated Code” section.

## Installation

1. **Clone the repo** or place the script in your project.
2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```
3. **Set up OpenAI API key**:

   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

   or on Windows:

   ```powershell
   $env:OPENAI_API_KEY="sk-..."
   ```

## Installation via setup.py

If you want to use **Readme Generator** as a pip-installable module—for instance, to run it using a `readme-generator` command on your system—follow these steps:

## Clone or Download the Repository

```bash
git clone https://github.com/ArchZion/readme-generator.git
cd readme-generator
```

### Create and Activate a Virtual Environment (Optional but Recommended)

```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or on Windows: .\venv\Scripts\activate
```

### Install the Package

#### Editable (Development) Install:
```bash
pip install -e .
```

#### Regular Local Install:
```bash
pip install .
```

## Set Your OpenAI API Key

```bash
export OPENAI_API_KEY="sk-..."
# or on Windows:
$env:OPENAI_API_KEY="sk-..."
```

## Run the CLI from Anywhere

```bash
readme-generator --help
```

This should display the full list of CLI options. You can now run commands like:

```bash
readme-generator \
  --directory . \
  --output-file README.md \
  --template-file readme-generator.template
```

## Usage

```bash
python readme_generator/cli.py [OPTIONS]
```

# CLI Arguments and Their Usage

## Arguments & Options

### `--directory, -d` (default: `.`)

The directory of the repository to analyze. If not specified, the current working directory (`.`) is used.
Example:

```bash
--directory ../my_project
```

Analyzes the `my_project` folder above the current location.

### `--output-file, -o` (default: `README.md`)

The path or filename where the newly generated README should be written.
Example:

```bash
--output-file NEW_README.md
```

The final content will be saved in `NEW_README.md` instead of the default `README.md`.

### `--existing-readme-file` (default: `None`)

The path to an existing README to merge. If not provided, it defaults to `--output-file`.

### `--template-file` (default: `readme-generator.template`)

The path to a custom template containing headers, instructions, or special sections to integrate.

### `--append/--overwrite` (default: `False` => overwrite)

Determines whether the final README content is appended or overwrites the existing file.

- `--append`: Adds new content at the end.
- `--overwrite`: Replaces the file’s contents.

### `--max-tokens` (default: `1500`)

Token budget for the final GPT-based summary.

- Higher values produce more verbose READMEs.
- Lower values keep responses concise.

### `--directory-summary/--no-directory-summary` (default: `directory-summary=True`)

Controls whether per-directory summaries are generated.

- `--no-directory-summary`: Skips directory-level analysis.

### `--temperature` (default: `0.3`)

Controls the randomness of the GPT output.

- `0.0`: Deterministic and concise.
- `1.0`: More creative text.
- Recommended range: `0.2–0.5`.

### `--force` (flag, default: `False`)

Forces a README re-generation even if no code changes are detected.

### `--ignore` (repeatable)

Excludes specific paths or substrings from analysis.
Example:

```bash
--ignore .git --ignore .vscode
```

### `--ignore-ext` (repeatable)

Excludes files with specific extensions.
Example:

```bash
--ignore-ext .png --ignore-ext .exe
```

### `--digest-file` (default: `readme.md5s`)

Specifies the JSON file for storing MD5 checksums.
Example:

```bash
--digest-file custom_digests.json
```

## Example Usage Scenarios

### Basic Run

```bash
python readme_generator/cli.py --directory . --output-file README.md
```

Analyzes the current directory and writes or overwrites `README.md`.

### Merge an Older README

```bash
python readme_generator/cli.py \
    --directory ./src \
    --output-file README.md \
    --existing-readme-file OLDER_README.md
```

Merges content from `OLDER_README.md` into the new `README.md`.

### Use a Custom Template

```bash
python readme_generator/cli.py \
    --template-file my_custom_template.txt \
    --directory-summary \
    --output-file README_NEW.md
```

Loads headings from `my_custom_template.txt` and includes directory-level summaries.

### Append Instead of Overwriting

```bash
python readme_generator/cli.py \
    --append \
    --directory . \
    --output-file README_APPEND.md
```

Appends new sections to `README_APPEND.md` instead of replacing it.

### Ignore Certain Paths

```bash
python readme_generator/cli.py \
    --ignore .git \
    --ignore .vscode \
    --ignore-ext .png \
    --ignore-ext .log
```

Skips analyzing `.git/`, `.vscode/`, `.png`, and `.log` files.

### Increasing Detail

```bash
python readme_generator/cli.py --max-tokens 2500 --temperature 0.5
```

Allows GPT to use up to 2,500 tokens with a slightly more creative approach.

### Forcing a Regeneration

```bash
python readme_generator/cli.py --force
```

Forces a README update even if no changes are detected.

### Using a Different Digest File

```bash
python readme_generator/cli.py \
    --digest-file custom_digest.json \
    --directory . \
    --output-file README.md
```

Tracks MD5 checksums in `custom_digest.json` instead of `readme.md5s`.

## Workflow

1. **Digest Check**: We store a `readme.md5s` file that holds MD5 checksums of your files/directories. If nothing changed, we skip generation.
2. **File Summaries**: Each file is read in chunks and summarized by GPT.
3. **Directory Summaries**: The file summaries are merged into a directory-level summary.
4. **Old README Merge**: If an old README is found, or if you specify one, GPT merges it with the new content.
5. **Template Integration**: If you provide a template, it’s included in the final prompt.
6. **Result**: A final README is written or appended to your chosen output path.

## Requirements

See `requirements.txt` for details. Typical dependencies include:

- `openai`
- `click`
- `tiktoken`

## Development & Contributing

Feel free to open PRs or issues.
For large repos, you may need to chunk or reduce the code. If you encounter token limit errors, consider GPT-3.5-16k or GPT-4.

