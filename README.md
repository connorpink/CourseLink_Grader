# CourseLink CSV Grading Helper

`process.py` is a Typer CLI for CourseLink CSV exports.
It uses color-coded terminal output via `rich` to make statuses and workflow steps easier to follow.

## What it does

### Option 1 (`option1`)
- Loads a CourseLink export CSV.
- Detects the assignment grade column by matching `"Points Grade"` in the header.
- Creates a new CSV that is ready to import by removing rows where the grade cell is empty.
- Keeps all columns and headers unchanged for remaining rows, including `End-of-Line Indicator`.
- Keeps valid `0` grades.

### Option 2 (`option2`)
- Opens a CSV and runs an interactive grading harness.
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
python3 -m pip install typer prompt_toolkit rich
```

## Usage

Run menu mode (choose option 1 or 2):

```bash
python3 process.py
```

Direct command usage:

```bash
# Option 1: ready-to-import CSV
python3 process.py option1
python3 process.py option1 --csv "your_export.csv" --out "ready_import.csv"

# Option 2: grading harness
python3 process.py option2
python3 process.py option2 --csv "your_export.csv"
python3 process.py option2 --csv "your_export.csv" --progress-out "my_progress.csv"
```

## Notes

- CSV file selection supports fuzzy filtering when `--csv` is not provided.
- Progress files use `__progress.csv` suffix by default.
- Output from option 1 uses `__ready_to_import.csv` suffix by default.
