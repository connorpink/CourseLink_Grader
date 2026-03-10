# CourseLink CSV Grading Helper

This project is a Typer CLI for CourseLink CSV exports.
The source lives under `src/`, and the packaged CLI command is `courselink-grader`.
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
- Without `fzf`, the built-in CSV picker starts at the current working directory by default and behaves like a simple directory tree:
  - arrow keys move the selection
  - `Enter` or `Right` opens a directory or selects a CSV
  - `Left` or `Backspace` moves to the parent directory
- `--root PATH` lets you override where CSV browsing starts.
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

### Install from PyPI

After publishing, the simplest global installs are:

```bash
uv tool install courselink-grader
# or
pipx install courselink-grader
```

That puts `courselink-grader` on your `PATH`, so you can run it from any directory.

### Install from this repo during development

```bash
uv tool install .
# or, for a project-local environment:
uv sync
```

## Usage

Run `courselink-grader` from the directory that contains your grading files, or pass `--root` to browse somewhere else.
CSV files can live directly in the current directory or in nested folders such as `./grading/assignments/assignment1.csv`.

Run menu mode (choose option 1 or 2):

```bash
courselink-grader
```

Direct command usage:

```bash
# Option 1: ready-to-import CSV
courselink-grader option1
courselink-grader option1 --csv "grading/assignments/assignment1.csv" --out "ready_import.csv"
courselink-grader option1 --root "~/Courses/CS101"

# Option 2: grading harness
courselink-grader option2
courselink-grader option2 --csv "grading/assignments/assignment1.csv"
courselink-grader option2 --csv "grading/assignments/assignment1.csv" --progress-out "my_progress.csv"
courselink-grader option2 --root "~/Courses/CS101"
```

## Notes

- When `--csv` is not provided, CSV selection starts at the current working directory by default.
- The built-in picker shows only directories that contain at least one CSV somewhere below them, plus CSV files in the current directory.
- `fzf` mode searches recursively across CSV paths under the active browse root.
- `fzf` is optional and not a Python dependency; install separately if desired.
- Progress files use `__progress.csv` suffix by default.
- Output from option 1 uses `__ready_to_import.csv` suffix by default.

## Release Workflow

- For local publishing, use a PyPI token with `UV_PUBLISH_TOKEN` instead of entering credentials interactively.
- For CI/CD publishing, this repo includes GitHub Actions workflows for pull-request CI and tagged PyPI releases.
- The recommended flow is feature branch -> pull request -> merge to `main` -> version bump -> `vX.Y.Z` tag -> publish workflow.
- Detailed setup and release steps are in [`RELEASING.md`](RELEASING.md).
