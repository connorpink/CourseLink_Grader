# CourseLink CSV Grading Helper

[![PyPI version](https://img.shields.io/pypi/v/courselink-grader)](https://pypi.org/project/courselink-grader/) [![Python versions](https://img.shields.io/pypi/pyversions/courselink-grader)](https://pypi.org/project/courselink-grader/)

If your use-case includes grading on CourseLink this tool may save you time entering grades into CourseLink. It supports entering a numeric grade for 1 deliverable at a time. It would mainly be useful for grading physical assignments.

First export a csv for the particular Assignment being graded, for the class section you intend to grade. Then run the program in the dir where the csv lives... Thats it! The program will act as a harness to speed up entering the grades, and it can format the csv for you so that it is ready to be imported back into CourseLink once your done entering grades.

This project is a Typer CLI for CourseLink CSV exports. It can easily be installed as a PyPi package or built from source. The program will prefer FZF if installed, but has fallback functionality in pure-python as well.
The source lives under `src/`, and the packaged CLI command is `courselink-grader`.

> Note that this tool is in early development. Usage of this tool is at your own risk.

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

Run menu mode (choose a workflow from the prompt):

```bash
courselink-grader
```

Direct command usage:

```bash
# Import helper: ready-to-import CSV
courselink-grader import-helper
courselink-grader import-helper --csv "grading/assignments/assignment1.csv" --out "ready_import.csv"
courselink-grader import-helper --csv "grading/assignments/assignment1__progress.csv"
courselink-grader import-helper --csv "grading/assignments/assignment1__progress.csv" --fresh-csv "grading/assignments/assignment1_fresh_export.csv"
courselink-grader import-helper --root "~/Courses/CS101"

# Grading harness: interactive grading
courselink-grader grading-harness
courselink-grader grading-harness --csv "grading/assignments/assignment1.csv"
courselink-grader grading-harness --csv "grading/assignments/assignment1.csv" --progress-out "my_progress.csv"
courselink-grader grading-harness --root "~/Courses/CS101"
```

## What it does

### Import helper (`import-helper`)

- Loads a CourseLink export CSV.
- If `fzf` is installed, prompts whether to use `fzf` for CSV selection.
- Detects the assignment grade column by matching `"Points Grade"` in the header.
- For a plain CourseLink export, creates a new CSV that is ready to import by removing rows where the grade cell is empty.
- For a `__progress.csv`, compares it against the original export by `OrgDefinedId` and only keeps rows whose normalized grade changed.
- Optional `--fresh-csv` lets you merge those changed grades onto a fresh CourseLink export before writing the import-ready CSV.
- Keeps all columns and headers unchanged for remaining rows, including `End-of-Line Indicator`.
- Keeps valid `0` grades.
- Refuses to merge when the original export and fresh export cannot be proven compatible.

### Grading harness (`grading-harness`)

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
- Writes a sidecar metadata file next to the progress CSV so import prep can find the original export safely later.
- Supports resume by reopening that progress CSV.
- Keyboard controls:
  - `Ctrl-Q`: open the post-grading menu
  - `Ctrl-B`: jump to previously graded student
  - `F2`: open the same post-grading menu without leaving the session
- Post-grading menu options:
  - resume grading
  - prep import immediately from changed rows only
  - prep import using a fresh CourseLink export
  - exit

## Notes

- When `--csv` is not provided, CSV selection starts at the current working directory by default.
- The built-in picker shows only directories that contain at least one CSV somewhere below them, plus CSV files in the current directory.
- `fzf` mode searches recursively across CSV paths under the active browse root.
- `fzf` is optional and not a Python dependency; install separately if desired.
- Progress files use `__progress.csv` suffix by default.
- Progress metadata uses `__progress.meta.json` suffix by default.
- Output from `import-helper` uses `__ready_to_import.csv` suffix by default.
- When exporting the CSV from CourseLink, I use these options. Results may vary with other export settings:
  - Key Field: `Both`
  - Grade Values: `Points grade`
    - no weighted grade or grade scheme
  - User Details:
    - Last Name
    - First Name
    - Email
    - Section Membership
