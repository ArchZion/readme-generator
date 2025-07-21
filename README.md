# Python Gemini - Readme Generator

**Readme Generator** is a Python command-line tool that automatically analyzes your codebase, merges existing documentation, and updates a `README.md` by combining:

1. An existing README (if present)
2. A user-provided template file (optional)
3. A Gemini-based analysis of your code (chunking & summarizing)

It detects tools, merges code summaries, and preserves unique sections from the old README.

## Key Features

- **Incremental Updates**: Stores an MD5 digest of your code in a JSON file so it only regenerates if something actually changed (unless `--force` is used).
- **Merges Old README**: If a README already exists, the new content is merged in, preserving unique sections.
- **Custom Template**: Provide a file (`readme-generator.template`) with headings or instructions you want integrated.
- **Tool Detection**: Scans `.py`, `.tf`, `.sh`, `.js`, `.ts`, `Dockerfile`, etc. to generate installation steps. If a tool is unknown, it queries Gemini for short instructions.
- **Annotated Lines**: Any line containing `!important` will be specially summarized in a "Custom-Annotated Code" section.
- **Gemini 2.5 Flash Optimized**: Uses Google's Gemini 2.5 Flash model with robust token limit handling (1M input, 65K output tokens).
- **Reliability**: Includes comprehensive error handling and fallback mechanisms.

## Installation

1. **Clone the repo** or place the script in your project.
2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```
3. **Set up Gemini API key**:

   ```bash
   export GEMINI_API_KEY="your-api-key"
   ```

   or on Windows:

   ```powershell
   $env:GEMINI_API_KEY="your-api-key"
   ```

   Get your API key from: https://makersuite.google.com/app/apikey

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

## Set Your Gemini API Key

```bash
export GEMINI_API_KEY="your-api-key"
# or on Windows:
$env:GEMINI_API_KEY="your-api-key"
```

Get your API key from: https://makersuite.google.com/app/apikey

## Run the CLI from Anywhere

```bash
readme-generator --help
```

This should display the full list of CLI options. You can now run commands like:

```bash
# Simple usage with default template
readme-generator --directory . --output-file README.md

# Advanced usage with custom parameters
readme-generator \
  --directory . \
  --output-file README.md \
  --max-tokens 12000 \
  --temperature 0.2 \
  --force
```

The tool now automatically uses the template from `docs/readme-generator/readme-generator.template` and stores all supporting files in the `docs/readme-generator/` directory.

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

### `--template-file` (default: `docs/readme-generator/readme-generator.template`)

The path to a custom template containing headers, instructions, or special sections to integrate.

### `--append/--overwrite` (default: `False` => overwrite)

Determines whether the final README content is appended or overwrites the existing file.

- `--append`: Adds new content at the end.
- `--overwrite`: Replaces the file’s contents.

### `--max-tokens` (default: `8000`)

Token budget for the final Gemini-based summary.

- Higher values produce more verbose READMEs.
- Lower values keep responses concise.
- Gemini 2.5 Flash supports up to 65,536 output tokens.

### `--directory-summary/--no-directory-summary` (default: `directory-summary=True`)

Controls whether per-directory summaries are generated.

- `--no-directory-summary`: Skips directory-level analysis.

### `--temperature` (default: `0.3`)

Controls the randomness of the Gemini output.

- `0.0`: Deterministic and concise.
- `1.0`: More creative text.
- Recommended range: `0.2–0.5`.

### `--force` (flag, default: `False`)

Forces a README re-generation even if no code changes are detected.

### `--ignore` (repeatable)

Excludes specific paths or substrings from analysis. The tool comes with comprehensive default exclusions for common files and folders.
Example:

```bash
--ignore .git --ignore .vscode
```

**Default exclusions include:**
- Version control: `.git`, `.svn`, `.hg`
- Virtual environments: `.venv`, `venv`, `node_modules`
- Build directories: `build`, `dist`, `target`
- IDE files: `.vscode`, `.idea`, `.vs`
- Package locks: `package-lock.json`, `yarn.lock`
- Infrastructure: `.terraform`, `Dockerfile`
- Configuration: `.env`, `.gitignore`, `.dockerignore`
- And many more...

**Note:** You can also add custom ignore patterns to `docs/readme-generator/.readme-generator.ignore` for project-specific exclusions.

### `--ignore-ext` (repeatable)

Excludes files with specific extensions. The tool comes with comprehensive default extensions.
Example:

```bash
--ignore-ext .png --ignore-ext .exe
```

**Default extensions include:**
- Binary files: `.exe`, `.dll`, `.so`, `.bin`
- Images: `.png`, `.jpg`, `.gif`, `.svg`
- Archives: `.zip`, `.tar`, `.gz`
- Documents: `.pdf`, `.doc`, `.xlsx`
- Compiled: `.pyc`, `.class`, `.jar`
- And many more...

### `--digest-file` (default: `docs/readme-generator/readme.md5s`)

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

### Use the Default Template

```bash
python readme_generator/cli.py \
    --directory-summary \
    --output-file README_NEW.md
```

Uses the default template from `docs/readme-generator/readme-generator.template` and includes directory-level summaries.

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

Allows Gemini to use up to 8,000 tokens with a slightly more creative approach.

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

Tracks MD5 checksums in `custom_digest.json` instead of `docs/readme-generator/readme.md5s`.

## Workflow

1. **Digest Check**: We store a `docs/readme-generator/readme.md5s` file that holds MD5 checksums of your files/directories. If nothing changed, we skip generation.
2. **File Summaries**: Each file is read in chunks and summarized by Gemini.
3. **Directory Summaries**: The file summaries are merged into a directory-level summary.
4. **Old README Merge**: If an old README is found, or if you specify one, Gemini merges it with the new content.
5. **Template Integration**: If you provide a template, it’s included in the final prompt.
6. **Result**: A final README is written or appended to your chosen output path.

## Requirements

See `requirements.txt` for details. Typical dependencies include:

- `google-generativeai`
- `click`
- `tiktoken`

## Directory Structure

The tool now organizes its files in a clean directory structure:

```
project-root/
├── README.md                    # Generated README (stays in root)
├── docs/
│   └── readme-generator/
│       ├── readme-generator.template  # Template file
│       ├── .readme-generator.ignore   # Custom ignore patterns
│       └── readme.md5s               # MD5 checksums
└── ... (other project files)
```

This keeps your project root clean while organizing all readme-generator related files in one place.

### Custom Ignore File

You can create a `.readme-generator.ignore` file in the `docs/readme-generator/` directory to add your own custom ignore patterns. This file works similarly to `.gitignore`:

```bash
# Example .readme-generator.ignore file
tests/
docs/api/
*.test.js
*.spec.py
config.local.json
secrets.env
```

The tool will automatically load these patterns and combine them with the default exclusions.

## Technical Details

### Gemini 2.5 Flash Integration

This tool is specifically optimized for Google's Gemini 2.5 Flash model with the following capabilities:

- **Input Token Limit**: 1,048,576 tokens (~4MB of text)
- **Output Token Limit**: 65,536 tokens (~256KB of response)
- **Large Context Windows**: Can process entire codebases in fewer chunks
- **Safety Filters**: Built-in content filtering and safety mechanisms
- **Robust Error Handling**: Comprehensive fallback mechanisms and error recovery

### Reliability Features

- **Token Limit Compliance**: Automatic truncation and adjustment to stay within limits
- **Fallback Mechanisms**: Graceful degradation when tokenization fails
- **Detailed Logging**: Comprehensive logging of API calls and token usage
- **Error Recovery**: Continues processing even if individual API calls fail

## Development & Contributing

Feel free to open PRs or issues.
For large repos, you may need to chunk or reduce the code. If you encounter token limit errors, consider using a different Gemini model or reducing the input size. The tool is optimized for Gemini 2.5 Flash which can handle up to 1M input tokens and 65K output tokens.

