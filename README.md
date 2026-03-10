# CourseLink CSV Grading Helper

This project is a Typer CLI for CourseLink CSV exports.
The source now lives under `src/`, and `uv` exposes it as the `CourseLink_Helper` command.
It uses color-coded terminal output via `rich` to make statuses and workflow steps easier to follow.

## What it does

### Option 1 (`option1`)
- Loads a CourseLink export CSV.
- If `fzf` is installed, prompts whether to use `fzf` for CSV selection.
- Detects the assignment grade column by matching `"Points Grade"` in the header.
- Creates a new CSV that is ready to import by removing rows where the grade cell is empty.
- Keeps all columns and headers unchanged for remaining rows, including `End-of-Line Indicator`.
- Keeps valid `0` grades.

### Option 2 (`option2`)
- Opens a CSV and runs an interactive grading harness.
- If `fzf` is installed, prompts whether to use `fzf` for CSV and student selection.
- Without `fzf`, the built-in CSV picker starts at the project root and behaves like a simple directory tree:
  - arrow keys move the selection
  - `Enter` opens a directory or selects a CSV
  - `Backspace` moves to the parent directory
- In `fzf` mode, student matching uses case-insensitive fuzzy matching against a hidden search key
  (name, username, IDs) while showing a clean display column for stable selection.
- Uses ranked fuzzy search (live filter, arrow keys, Enter) to find students by:
  - `Last Name`
  - `First Name`
  - `Username`
  - `OrgDefinedId`
- Prioritizes stronger matches (for example, `Cole` should rank above weaker partial matches).
- If you press Enter after typing a close match (even without explicitly accepting completion text),
  it resolves to the best student match.
- Displays `Username` and `OrgDefinedId` without the leading `#` for readability
  (the saved CSV still keeps original values).
- If `fzf` selection is cancelled or fails, it falls back to the built-in picker.
- Lets you enter decimal grades and validates:
  - grade is not empty
  - grade is numeric
  - grade is not negative
  - grade is `<= MaxPoints` parsed from header text like:
    - `Homework 6 Points Grade <Numeric MaxPoints:12 Weight:1>`
- Autosaves after every entered grade into a progress CSV in the current directory.
- Supports resume by reopening that progress CSV.
- Keyboard controls:
  - `Ctrl-Q`: quit
  - `Ctrl-B`: jump to previously graded student

## Install

```bash
uv sync
```

## Usage

Run commands from the project root.
CSV files can live directly in the root or in nested folders such as `./grading/assignments/assignment1.csv`.

Run menu mode (choose option 1 or 2):

```bash
uv run CourseLink_Helper
```

Direct command usage:

```bash
# Option 1: ready-to-import CSV
uv run CourseLink_Helper option1
uv run CourseLink_Helper option1 --csv "grading/assignments/assignment1.csv" --out "ready_import.csv"

# Option 2: grading harness
uv run CourseLink_Helper option2
uv run CourseLink_Helper option2 --csv "grading/assignments/assignment1.csv"
uv run CourseLink_Helper option2 --csv "grading/assignments/assignment1.csv" --progress-out "my_progress.csv"
```

## Notes

- When `--csv` is not provided, CSV selection starts at the project root.
- The built-in picker shows only directories that contain at least one CSV somewhere below them, plus CSV files in the current directory.
- `fzf` mode searches recursively across CSV paths under the project root.
- `fzf` is optional and not a Python dependency; install separately if desired.
- Progress files use `__progress.csv` suffix by default.
- Output from option 1 uses `__ready_to_import.csv` suffix by default.
