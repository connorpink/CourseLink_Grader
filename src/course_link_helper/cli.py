"""CourseLink CSV grading helper.

This CLI has two workflows:
1) `import-helper`: create a ready-to-import CSV from an export or progress file.
2) `grading-harness`: run interactive grading with autosave and direct import prep.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Optional

import typer

try:
    from prompt_toolkit import prompt
    from prompt_toolkit.application import Application
    from prompt_toolkit.completion import Completion, Completer
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit
    from prompt_toolkit.widgets import Frame, Label, RadioList
except ImportError as exc:  # pragma: no cover - runtime dependency message
    raise SystemExit(
        "Missing dependency: prompt_toolkit. Install with: pip install prompt_toolkit"
    ) from exc

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError as exc:  # pragma: no cover - runtime dependency message
    raise SystemExit("Missing dependency: rich. Install with: pip install rich") from exc


app = typer.Typer(
    no_args_is_help=False,
    add_completion=False,
    help=(
        "Prepare CourseLink CSV files for import and run an interactive grading harness."
    ),
)

POINTS_GRADE_TOKEN = "Points Grade"
ORG_DEFINED_ID_COLUMN = "OrgDefinedId"
PROGRESS_SUFFIX = "__progress.csv"
PROGRESS_META_SUFFIX = "__progress.meta.json"
PREP_SENTINEL = "__PREP__"
CRLF = "\r\n"
QUIT_SENTINEL = "__QUIT__"
BACK_SENTINEL = "__BACK__"
console = Console()


def clean_hash_prefix(value: str) -> str:
    """Hide leading hash prefixes for display only."""
    return value[1:] if value.startswith("#") else value


def normalize_text(value: str) -> str:
    """Normalize search text for matching."""
    return " ".join(value.strip().lower().split())


def ui_info(message: str) -> None:
    """Print informational output with distinct styling."""
    console.print(f"[bold cyan]INFO[/] {message}")


def ui_warn(message: str) -> None:
    """Print warning output with distinct styling."""
    console.print(f"[bold yellow]WARN[/] {message}")


def ui_error(message: str) -> None:
    """Print error output with distinct styling."""
    console.print(f"[bold red]ERROR[/] {message}")


def ui_success(message: str) -> None:
    """Print success output with distinct styling."""
    console.print(f"[bold green]OK[/] {message}")


def is_fzf_available() -> bool:
    """Check whether fzf is available on PATH."""
    return shutil.which("fzf") is not None


def ask_use_fzf(purpose: str) -> bool:
    """Ask user whether to use fzf when available."""
    if not is_fzf_available():
        ui_info("fzf not found on PATH. Using built-in picker.")
        return False

    return typer.confirm(f"fzf is available. Use fzf for {purpose}?", default=True)


def run_fzf(
    lines: list[str],
    prompt_text: str,
    header_text: str,
    extra_args: Optional[list[str]] = None,
) -> Optional[str]:
    """Run fzf and return selected line, or None if cancelled/failed."""
    if not lines:
        return None

    cmd = [
        "fzf",
        "--height=80%",
        "--layout=reverse",
        "--border",
        "--prompt",
        prompt_text,
        "--header",
        header_text,
    ]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            input="\n".join(lines) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=None,
            check=False,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    selected = result.stdout.strip()
    return selected if selected else None


@dataclass
class CourseLinkSheet:
    """Represents a CourseLink export CSV file in memory."""

    source_path: Path
    encoding: str
    headers: list[str]
    rows: list[list[str]]
    grade_col_idx: int
    org_id_col_idx: int
    max_points: Optional[Decimal]


@dataclass(frozen=True)
class ProgressContext:
    """Original/export context associated with a progress CSV."""

    original_path: Path
    progress_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class ChangedGradeRow:
    """A single student row whose grade changed relative to the original export."""

    org_defined_id: str
    original_grade: str
    updated_grade: str
    progress_row: list[str]


@dataclass
class StudentRecord:
    """Represents a single student row and fields used for fuzzy search."""

    row_index: int
    org_defined_id: str
    username: str
    last_name: str
    first_name: str

    @property
    def display_username(self) -> str:
        """Username without hash prefix for display."""
        return clean_hash_prefix(self.username)

    @property
    def display_org_defined_id(self) -> str:
        """Org ID without hash prefix for display."""
        return clean_hash_prefix(self.org_defined_id)

    @property
    def display_name(self) -> str:
        """A consistent label shown in the student selector."""
        return (
            f"{self.last_name}, {self.first_name} | {self.display_username} | {self.display_org_defined_id}"
        )

    def search_terms(self) -> list[str]:
        """Searchable fields, both raw and display-form values."""
        first = self.first_name.lower()
        last = self.last_name.lower()
        username_raw = self.username.lower()
        org_raw = self.org_defined_id.lower()
        username_display = self.display_username.lower()
        org_display = self.display_org_defined_id.lower()
        return [
            first,
            last,
            f"{first} {last}",
            f"{last} {first}",
            username_raw,
            org_raw,
            username_display,
            org_display,
            self.display_name.lower(),
        ]


@dataclass(frozen=True)
class CsvBrowserEntry:
    """An entry in the interactive CSV browser."""

    path: Path
    kind: str

    @property
    def label(self) -> str:
        prefix = "dir" if self.kind == "dir" else "csv"
        suffix = "/" if self.kind == "dir" else ""
        return f"{prefix}: {self.path.name}{suffix}"


class CsvBrowser:
    """A simple tree-style CSV browser rooted at the project directory."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.current_dir = self.root_dir
        self.selection: Optional[Path] = None
        self._empty_value = object()
        self._selector = RadioList(values=[(self._empty_value, "Loading...")])
        self._path_label = Label("")
        self._help_label = Label(
            "Up/Down move  Enter/Right opens directory or selects CSV  Left/Backspace goes up  Ctrl-Q or Esc cancels"
        )
        self._application = Application(
            layout=Layout(
                HSplit(
                    [
                        Frame(
                            HSplit(
                                [
                                    self._path_label,
                                    self._selector,
                                    self._help_label,
                                ]
                            ),
                            title="CSV Browser",
                        )
                    ]
                ),
                focused_element=self._selector,
            ),
            key_bindings=self._build_keybindings(),
            full_screen=True,
        )
        self._refresh_entries()

    def run(self) -> Optional[Path]:
        """Launch the browser and return the selected CSV, if any."""
        return self._application.run()

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("enter", eager=True)
        @kb.add("right", eager=True)
        def _enter(event) -> None:  # type: ignore[no-untyped-def]
            current = self._selector.current_value
            if current is self._empty_value:
                return

            entry = current
            if entry.kind == "dir":
                self.current_dir = entry.path
                self._refresh_entries()
                event.app.invalidate()
                return

            self.selection = entry.path
            event.app.exit(result=entry.path)

        @kb.add("backspace", eager=True)
        @kb.add("left", eager=True)
        def _go_up(event) -> None:  # type: ignore[no-untyped-def]
            if self.current_dir == self.root_dir:
                return

            self.current_dir = self.current_dir.parent
            self._refresh_entries()
            event.app.invalidate()

        @kb.add("c-q")
        @kb.add("escape")
        def _quit(event) -> None:  # type: ignore[no-untyped-def]
            event.app.exit(result=None)

        return kb

    def _refresh_entries(self) -> None:
        entries = list_browsable_entries(self.current_dir)
        if entries:
            values = [(entry, entry.label) for entry in entries]
            self._selector.values = values
            self._selector.current_value = values[0][0]
            self._selector._selected_index = 0
        else:
            self._selector.values = [
                (
                    self._empty_value,
                    "No CSV files or matching subdirectories here. Press Backspace to go up.",
                )
            ]
            self._selector.current_value = self._empty_value
            self._selector._selected_index = 0

        self._path_label.text = f"Project root: {self.root_dir}\nCurrent: {format_browser_path(self.root_dir, self.current_dir)}"


def detect_encoding(path: Path) -> str:
    """Detect whether the file uses UTF-8 BOM, otherwise plain UTF-8."""
    raw = path.read_bytes()
    return "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"


def parse_max_points(header: str) -> Optional[Decimal]:
    """Extract max points from a CourseLink grade header."""
    match = re.search(r"MaxPoints:(\d+(?:\.\d+)?)", header)
    if not match:
        return None
    return Decimal(match.group(1))


def ensure_row_width(row: list[str], width: int) -> list[str]:
    """Pad or trim a row to match expected header width."""
    if len(row) < width:
        return row + [""] * (width - len(row))
    if len(row) > width:
        return row[:width]
    return row


def find_grade_column(headers: list[str]) -> int:
    """Find the first column containing the standard 'Points Grade' token."""
    for idx, header in enumerate(headers):
        if POINTS_GRADE_TOKEN in header:
            return idx
    raise typer.BadParameter(
        f"Could not find a grade column containing '{POINTS_GRADE_TOKEN}'."
    )


def read_sheet(path: Path) -> CourseLinkSheet:
    """Read a CSV file and locate key CourseLink columns."""
    if not path.exists():
        raise typer.BadParameter(f"CSV file not found: {path}")

    encoding = detect_encoding(path)
    with path.open("r", newline="", encoding=encoding) as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise typer.BadParameter(f"CSV file is empty: {path}") from exc
        rows = [ensure_row_width(row, len(headers)) for row in reader]

    grade_col_idx = find_grade_column(headers)
    try:
        org_id_col_idx = headers.index(ORG_DEFINED_ID_COLUMN)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Missing required column '{ORG_DEFINED_ID_COLUMN}'."
        ) from exc

    max_points = parse_max_points(headers[grade_col_idx])

    return CourseLinkSheet(
        source_path=path,
        encoding=encoding,
        headers=headers,
        rows=rows,
        grade_col_idx=grade_col_idx,
        org_id_col_idx=org_id_col_idx,
        max_points=max_points,
    )


def write_sheet(path: Path, headers: list[str], rows: list[list[str]], encoding: str) -> None:
    """Write CSV with CRLF endings for CourseLink compatibility."""
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.writer(handle, lineterminator=CRLF)
        writer.writerow(headers)
        writer.writerows(rows)


def iter_visible_children(directory: Path) -> list[Path]:
    """Return non-hidden child paths sorted by name."""
    try:
        children = [child for child in directory.iterdir() if not child.name.startswith(".")]
    except PermissionError:
        return []
    return sorted(children, key=lambda item: item.name.lower())


@lru_cache(maxsize=None)
def directory_contains_csv(directory: Path) -> bool:
    """Return whether a directory contains a visible CSV anywhere below it."""
    if not directory.is_dir():
        return False

    for child in iter_visible_children(directory):
        if child.is_file() and child.suffix.lower() == ".csv":
            return True
        if child.is_dir() and directory_contains_csv(child):
            return True
    return False


def list_browsable_entries(current_dir: Path) -> list[CsvBrowserEntry]:
    """List subdirectories leading to CSVs and CSV files in the current directory."""
    directories = [
        CsvBrowserEntry(path=child, kind="dir")
        for child in iter_visible_children(current_dir)
        if child.is_dir() and directory_contains_csv(child)
    ]
    files = [
        CsvBrowserEntry(path=child, kind="csv")
        for child in iter_visible_children(current_dir)
        if child.is_file() and child.suffix.lower() == ".csv"
    ]
    return directories + files


def list_all_csv_files(root_dir: Path) -> list[Path]:
    """Recursively list all visible CSV files under the project root."""
    csv_files: list[Path] = []
    if not root_dir.exists():
        return csv_files

    stack = [root_dir]
    while stack:
        current = stack.pop()
        for child in reversed(iter_visible_children(current)):
            if child.is_dir():
                stack.append(child)
            elif child.is_file() and child.suffix.lower() == ".csv":
                csv_files.append(child)

    return sorted(csv_files, key=lambda item: item.relative_to(root_dir).as_posix().lower())


def format_browser_path(root_dir: Path, current_dir: Path) -> str:
    """Format a directory path relative to the browser root."""
    if current_dir == root_dir:
        return "."
    return f"./{current_dir.relative_to(root_dir).as_posix()}"


def resolve_root(root_path: Optional[Path]) -> Path:
    """Resolve the CSV browser root, defaulting to the caller's working directory."""
    if root_path is None:
        return Path.cwd().resolve()
    return root_path.expanduser().resolve()


def display_path(path: Path, root_dir: Path) -> str:
    """Render paths relative to the active browser root when possible."""
    absolute_path = path if path.is_absolute() else (Path.cwd() / path).resolve()
    if absolute_path.is_relative_to(root_dir):
        return str(absolute_path.relative_to(root_dir))
    return str(path)


def _build_keybindings() -> KeyBindings:
    """Create keybindings used by interactive prompts."""
    kb = KeyBindings()

    @kb.add("c-q")
    def _quit(event) -> None:  # type: ignore[no-untyped-def]
        event.app.exit(result=QUIT_SENTINEL)

    @kb.add("c-b")
    def _back(event) -> None:  # type: ignore[no-untyped-def]
        event.app.exit(result=BACK_SENTINEL)

    @kb.add("f2")
    def _prep(event) -> None:  # type: ignore[no-untyped-def]
        event.app.exit(result=PREP_SENTINEL)

    return kb


def normalize_grade_cell(raw_grade: str) -> str:
    """Normalize grade text for comparisons while preserving non-numeric text as-is."""
    stripped = raw_grade.strip()
    if stripped == "":
        return ""
    try:
        return normalize_decimal_input(stripped)
    except typer.BadParameter:
        return stripped


def progress_metadata_path(progress_path: Path) -> Path:
    """Return the sidecar metadata path for a progress CSV."""
    progress_path = progress_path.resolve()
    if progress_path.name.endswith(PROGRESS_SUFFIX):
        base_name = progress_path.name[: -len(PROGRESS_SUFFIX)]
        return progress_path.with_name(f"{base_name}{PROGRESS_META_SUFFIX}")
    return progress_path.with_name(f"{progress_path.name}.meta.json")


def is_progress_csv(path: Path) -> bool:
    """Return whether a path appears to be a grading progress CSV."""
    return path.name.endswith(PROGRESS_SUFFIX)


def derive_original_from_progress(progress_path: Path) -> Optional[Path]:
    """Best-effort fallback for legacy progress files without metadata."""
    progress_path = progress_path.resolve()
    if not progress_path.name.endswith(PROGRESS_SUFFIX):
        return None
    original_name = progress_path.name[: -len(PROGRESS_SUFFIX)] + ".csv"
    return progress_path.with_name(original_name)


def write_progress_metadata(progress_path: Path, original_path: Path) -> Path:
    """Persist the original export path used to create or resume a progress CSV."""
    metadata_path = progress_metadata_path(progress_path)
    payload = {
        "original_path": str(original_path.resolve()),
        "progress_path": str(progress_path.resolve()),
    }
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return metadata_path


def load_progress_context(progress_path: Path) -> ProgressContext:
    """Resolve the original export path for a progress CSV."""
    progress_path = progress_path.resolve()
    metadata_path = progress_metadata_path(progress_path)
    if metadata_path.exists():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(
                f"Progress metadata is invalid JSON: {metadata_path}"
            ) from exc
        original_value = str(payload.get("original_path", "")).strip()
        if not original_value:
            raise typer.BadParameter(
                f"Progress metadata is missing 'original_path': {metadata_path}"
            )
        original_path = Path(original_value).expanduser().resolve()
    else:
        original_path = derive_original_from_progress(progress_path)
        if original_path is None:
            raise typer.BadParameter(
                "This progress CSV does not have source metadata and its original export "
                "cannot be derived from the filename."
            )

    if not original_path.exists():
        raise typer.BadParameter(
            "Could not find the original export for this progress CSV. "
            f"Expected: {original_path}"
        )

    return ProgressContext(
        original_path=original_path,
        progress_path=progress_path,
        metadata_path=metadata_path,
    )


def build_row_index(sheet: CourseLinkSheet) -> dict[str, list[str]]:
    """Index sheet rows by OrgDefinedId."""
    indexed: dict[str, list[str]] = {}
    for row in sheet.rows:
        org_id = row[sheet.org_id_col_idx].strip()
        if org_id:
            indexed[org_id] = row
    return indexed


def ensure_compatible_sheets(
    base_sheet: CourseLinkSheet, candidate_sheet: CourseLinkSheet, label: str
) -> None:
    """Validate that two sheets can be diffed or merged safely."""
    if base_sheet.headers != candidate_sheet.headers:
        raise typer.BadParameter(
            f"{label} does not match the original export headers."
        )
    if (
        base_sheet.grade_col_idx != candidate_sheet.grade_col_idx
        or base_sheet.headers[base_sheet.grade_col_idx]
        != candidate_sheet.headers[candidate_sheet.grade_col_idx]
    ):
        raise typer.BadParameter(
            f"{label} does not match the original export grade column."
        )


def detect_changed_grade_rows(
    original_sheet: CourseLinkSheet, progress_sheet: CourseLinkSheet
) -> list[ChangedGradeRow]:
    """Return rows whose grade changed relative to the original export."""
    ensure_compatible_sheets(original_sheet, progress_sheet, "Progress CSV")
    original_rows = build_row_index(original_sheet)
    changed_rows: list[ChangedGradeRow] = []

    for progress_row in progress_sheet.rows:
        org_id = progress_row[progress_sheet.org_id_col_idx].strip()
        if not org_id:
            continue
        original_row = original_rows.get(org_id)
        if original_row is None:
            raise typer.BadParameter(
                f"Progress CSV contains student not present in original export: {org_id}"
            )
        original_grade = normalize_grade_cell(original_row[original_sheet.grade_col_idx])
        updated_grade = normalize_grade_cell(progress_row[progress_sheet.grade_col_idx])
        if original_grade != updated_grade:
            changed_rows.append(
                ChangedGradeRow(
                    org_defined_id=org_id,
                    original_grade=original_grade,
                    updated_grade=updated_grade,
                    progress_row=progress_row.copy(),
                )
            )

    return changed_rows


def build_import_rows_from_changes(
    source_sheet: CourseLinkSheet, changed_rows: list[ChangedGradeRow]
) -> list[list[str]]:
    """Build import-ready rows from a change set against a chosen source sheet."""
    source_rows = build_row_index(source_sheet)
    import_rows: list[list[str]] = []
    for changed_row in changed_rows:
        source_row = source_rows.get(changed_row.org_defined_id)
        if source_row is None:
            raise typer.BadParameter(
                f"Student {changed_row.org_defined_id} is missing from the selected source CSV."
            )
        row = source_row.copy()
        row[source_sheet.grade_col_idx] = changed_row.updated_grade
        import_rows.append(row)
    return import_rows


def default_ready_import_path(source: Path) -> Path:
    """Default output path for import-ready CSVs."""
    return source.with_name(f"{source.stem}__ready_to_import.csv")


def prompt_post_grading_action() -> str:
    """Ask what to do after pausing or stopping grading."""
    menu = Table(show_header=False, box=box.SIMPLE_HEAVY)
    menu.add_row("[bold cyan]1[/]", "Resume grading")
    menu.add_row("[bold cyan]2[/]", "Prep import now from changed rows only")
    menu.add_row("[bold cyan]3[/]", "Prep import now using a fresh CourseLink export")
    menu.add_row("[bold cyan]4[/]", "Exit")
    console.print(Panel(menu, title="After Grading", border_style="cyan"))
    choice = typer.prompt("Choose next action", type=int)
    if choice == 1:
        return "resume"
    if choice == 2:
        return "prep_changed_only"
    if choice == 3:
        return "prep_fresh_merge"
    if choice == 4:
        return "exit"
    raise typer.BadParameter("Invalid choice. Enter 1, 2, 3, or 4.")


def handle_post_grading_action(
    active_root: Path, progress_path: Path, use_fzf: bool
) -> str:
    """Run the post-grading menu and perform the selected action."""
    action = prompt_post_grading_action()
    if action == "resume":
        return "resume"
    if action == "prep_changed_only":
        output_path = default_ready_import_path(progress_path)
        rows_kept, _ = prepare_import_output(
            active_root=active_root,
            source=progress_path,
            output_path=output_path,
        )
        ui_success(
            f"Prepared import CSV with {rows_kept} changed rows at {display_path(output_path, active_root)}"
        )
        return "resume"
    if action == "prep_fresh_merge":
        if use_fzf:
            fresh_source = pick_csv_file(active_root, use_fzf=True)
        else:
            ui_info("Select the fresh CourseLink export to merge against.")
            fresh_source = pick_csv_file(active_root, use_fzf=False)
        output_path = default_ready_import_path(progress_path)
        rows_kept, _ = prepare_import_output(
            active_root=active_root,
            source=progress_path,
            output_path=output_path,
            fresh_csv=fresh_source,
        )
        ui_success(
            f"Prepared import CSV with {rows_kept} changed rows at {display_path(output_path, active_root)}"
        )
        return "resume"
    return "exit"


def prepare_import_output(
    active_root: Path,
    source: Path,
    output_path: Path,
    fresh_csv: Optional[Path] = None,
) -> tuple[int, int]:
    """Create an import-ready CSV from either a plain export or a progress CSV."""
    sheet = read_sheet(source)
    if not is_progress_csv(source):
        if fresh_csv is not None:
            raise typer.BadParameter(
                "--fresh-csv can only be used when the source CSV is a __progress.csv file."
            )
        filtered_rows = [
            row for row in sheet.rows if row[sheet.grade_col_idx].strip() != ""
        ]
        write_sheet(output_path, sheet.headers, filtered_rows, sheet.encoding)
        return len(filtered_rows), len(sheet.rows) - len(filtered_rows)

    context = load_progress_context(source)
    original_sheet = read_sheet(context.original_path)
    changed_rows = detect_changed_grade_rows(original_sheet, sheet)
    if fresh_csv is not None:
        merge_sheet = read_sheet(fresh_csv)
        ensure_compatible_sheets(original_sheet, merge_sheet, "Fresh CourseLink export")
        output_rows = build_import_rows_from_changes(merge_sheet, changed_rows)
    else:
        output_rows = build_import_rows_from_changes(original_sheet, changed_rows)

    write_sheet(output_path, sheet.headers, output_rows, sheet.encoding)
    return len(output_rows), len(sheet.rows) - len(output_rows)


def rank_file_candidates(query: str, names: list[str]) -> list[tuple[int, str]]:
    """Rank file-name candidates for fuzzy selection fallback."""
    normalized_query = normalize_text(query)
    ranked: list[tuple[int, str]] = []
    for name in names:
        lowered = name.lower()
        score = 0
        if lowered == normalized_query:
            score += 300
        if lowered.startswith(normalized_query):
            score += 140
        if normalized_query in lowered:
            score += 80
        score += int(SequenceMatcher(None, normalized_query, lowered).ratio() * 40)
        ranked.append((score, name))
    ranked.sort(key=lambda item: (-item[0], item[1].lower()))
    return ranked


def fzf_pick_file(root_dir: Path, csv_files: list[Path]) -> Optional[Path]:
    """Pick a CSV file using fzf."""
    relative_names = [path.relative_to(root_dir).as_posix() for path in csv_files]
    selected = run_fzf(
        relative_names,
        prompt_text="csv> ",
        header_text=(
            "Browsing CSV files under project root. Type to filter nested paths, Enter to select, Esc/Ctrl-C to cancel"
        ),
    )
    if selected is None:
        return None
    if selected in relative_names:
        return root_dir / selected

    ranked = rank_file_candidates(selected, relative_names)
    if ranked and ranked[0][0] > 0:
        return root_dir / ranked[0][1]
    return None


def pick_csv_file(root_dir: Path, use_fzf: bool = False) -> Path:
    """Pick a CSV file using fzf or a built-in directory browser."""
    csv_files = list_all_csv_files(root_dir)
    if not csv_files:
        raise typer.BadParameter(f"No CSV files found under project root: {root_dir}")
    if len(csv_files) == 1:
        return csv_files[0]

    if use_fzf:
        selected = fzf_pick_file(root_dir, csv_files)
        if selected is not None:
            return selected
        ui_warn("fzf selection cancelled or failed. Falling back to built-in picker.")

    selected = CsvBrowser(root_dir).run()
    if selected is None:
        raise typer.Exit(code=0)
    return selected


def normalize_decimal_input(raw_grade: str) -> str:
    """Validate and normalize decimal text so CSV stores plain numeric strings."""
    try:
        value = Decimal(raw_grade.strip())
    except InvalidOperation as exc:
        raise typer.BadParameter("Grade must be a valid decimal number.") from exc
    if value < 0:
        raise typer.BadParameter("Grade cannot be negative.")

    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def build_students(sheet: CourseLinkSheet) -> list[StudentRecord]:
    """Build searchable student records from sheet rows."""
    headers = sheet.headers

    def col_index(name: str) -> int:
        try:
            return headers.index(name)
        except ValueError as exc:
            raise typer.BadParameter(f"Missing required column '{name}'.") from exc

    username_col = col_index("Username")
    last_name_col = col_index("Last Name")
    first_name_col = col_index("First Name")

    students: list[StudentRecord] = []
    for idx, row in enumerate(sheet.rows):
        org_id = row[sheet.org_id_col_idx].strip()
        if not org_id:
            continue
        students.append(
            StudentRecord(
                row_index=idx,
                org_defined_id=org_id,
                username=row[username_col].strip(),
                last_name=row[last_name_col].strip(),
                first_name=row[first_name_col].strip(),
            )
        )
    return students


def student_match_score(query: str, student: StudentRecord) -> int:
    """Return weighted score; higher means better match."""
    normalized_query = normalize_text(query)
    if not normalized_query:
        return 0

    tokens = normalized_query.split()
    first = student.first_name.lower()
    last = student.last_name.lower()
    full_forward = f"{first} {last}"
    full_reverse = f"{last} {first}"
    username_raw = student.username.lower()
    org_raw = student.org_defined_id.lower()
    username_display = student.display_username.lower()
    org_display = student.display_org_defined_id.lower()
    fields = [first, last, full_forward, full_reverse, username_raw, org_raw, username_display, org_display]

    score = 0
    if normalized_query == full_forward or normalized_query == full_reverse:
        score += 300
    if normalized_query == first or normalized_query == last:
        score += 240
    if normalized_query in (username_raw, username_display, org_raw, org_display):
        score += 220

    for token in tokens:
        if token == first or token == last:
            score += 120
        if token == username_display or token == org_display:
            score += 110
        if token == username_raw or token == org_raw:
            score += 110
        if first.startswith(token) or last.startswith(token):
            score += 80
        if username_display.startswith(token) or org_display.startswith(token):
            score += 70
        for field in fields:
            if token in field:
                score += 25
                break

    for field in [full_forward, full_reverse, username_display, org_display]:
        similarity = SequenceMatcher(None, normalized_query, field).ratio()
        score += int(similarity * 30)

    return score


def rank_students(query: str, students: list[StudentRecord]) -> list[tuple[int, StudentRecord]]:
    """Rank students by match score for a user query."""
    normalized_query = normalize_text(query)
    if not normalized_query:
        ordered = sorted(students, key=lambda item: (item.last_name.lower(), item.first_name.lower()))
        return [(0, student) for student in ordered]

    ranked: list[tuple[int, StudentRecord]] = []
    for student in students:
        score = student_match_score(normalized_query, student)
        if score > 0:
            ranked.append((score, student))

    ranked.sort(key=lambda item: (-item[0], item[1].last_name.lower(), item[1].first_name.lower()))
    return ranked


class StudentCompleter(Completer):
    """Prompt-toolkit completer with weighted student ranking."""

    def __init__(self, students: list[StudentRecord], sheet: CourseLinkSheet) -> None:
        self.students = students
        self.sheet = sheet

    def get_completions(self, document, complete_event):  # type: ignore[no-untyped-def]
        query = document.text_before_cursor
        ranked = rank_students(query, self.students)
        if not ranked:
            return

        prefix_len = len(query)
        for score, student in ranked[:25]:
            grade = self.sheet.rows[student.row_index][self.sheet.grade_col_idx].strip() or "-"
            label = f"{student.display_name} | grade:{grade}"
            yield Completion(
                text=student.org_defined_id,
                start_position=-prefix_len,
                display=label,
                display_meta=f"score:{score}",
            )


def fzf_pick_student(students: list[StudentRecord], sheet: CourseLinkSheet) -> Optional[str]:
    """Pick a student using fzf and return OrgDefinedId."""
    lines: list[str] = []
    for student in students:
        grade = sheet.rows[student.row_index][sheet.grade_col_idx].strip() or "-"
        search_key = " ".join(
            [
                student.last_name.lower(),
                student.first_name.lower(),
                f"{student.first_name.lower()} {student.last_name.lower()}",
                f"{student.last_name.lower()} {student.first_name.lower()}",
                student.display_username.lower(),
                student.username.lower(),
                student.display_org_defined_id.lower(),
                student.org_defined_id.lower(),
            ]
        )
        display = (
            f"{student.last_name}, {student.first_name} | "
            f"{student.display_username} | {student.display_org_defined_id} | grade:{grade}"
        )
        line = (
            f"{search_key}\t"
            f"{display}\t"
            f"{student.org_defined_id}"
        )
        lines.append(line)

    selected = run_fzf(
        lines,
        prompt_text="student> ",
        header_text="Type to filter, Enter to select, Esc/Ctrl-C to stop",
        extra_args=[
            "--delimiter",
            "\t",
            "--with-nth",
            "2",
            "--nth",
            "1",
            "--ignore-case",
        ],
    )
    if selected is None:
        return None

    parts = selected.split("\t")
    org_id = parts[2].strip() if len(parts) > 2 else ""
    return org_id or None


def resolve_student_query(query: str, students: list[StudentRecord]) -> Optional[StudentRecord]:
    """Resolve user input to a single student record robustly."""
    normalized_query = normalize_text(query)
    if not normalized_query:
        return None

    for student in students:
        if normalized_query in {
            normalize_text(student.org_defined_id),
            normalize_text(student.display_org_defined_id),
            normalize_text(student.username),
            normalize_text(student.display_username),
            normalize_text(student.display_name),
            normalize_text(f"{student.first_name} {student.last_name}"),
            normalize_text(f"{student.last_name} {student.first_name}"),
        }:
            return student

    ranked = rank_students(normalized_query, students)
    if not ranked:
        return None
    best_score, best_student = ranked[0]
    return best_student if best_score >= 60 else None


def prompt_student(students: list[StudentRecord], sheet: CourseLinkSheet, use_fzf: bool = False) -> str:
    """Prompt for a student selection using fzf or ranked fuzzy completion."""
    if use_fzf:
        selected = fzf_pick_student(students, sheet)
        if selected is not None:
            return selected
        ui_warn("fzf selection cancelled or failed. Falling back to built-in picker.")

    result = prompt(
        "Find student (Ctrl-B previous, Ctrl-Q menu, F2 menu): ",
        completer=StudentCompleter(students, sheet),
        complete_while_typing=True,
        key_bindings=_build_keybindings(),
    ).strip()

    if result in (QUIT_SENTINEL, BACK_SENTINEL):
        return result
    return result


def save_progress(sheet: CourseLinkSheet, progress_path: Path) -> None:
    """Persist current grading progress so the harness can resume later."""
    write_sheet(progress_path, sheet.headers, sheet.rows, sheet.encoding)


@app.command("import-helper")
def import_helper(
    csv_file: Optional[Path] = typer.Option(
        None, "--csv", "-c", help="Source CourseLink CSV. If omitted, browse from the active root."
    ),
    fresh_csv: Optional[Path] = typer.Option(
        None,
        "--fresh-csv",
        help=(
            "Fresh CourseLink export to merge changed grades onto. "
            "Only used when the source CSV is a __progress.csv file."
        ),
    ),
    out_file: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output CSV path. Default: <source_stem>__ready_to_import.csv",
    ),
    root_dir: Optional[Path] = typer.Option(
        None,
        "--root",
        help="Directory to browse for CSV files. Default: current working directory.",
    ),
) -> None:
    """Create a ready-to-import CSV from an export or grading progress file."""
    active_root = resolve_root(root_dir)
    use_fzf = ask_use_fzf("CSV selection") if csv_file is None else False
    source = csv_file if csv_file else pick_csv_file(active_root, use_fzf=use_fzf)

    if out_file:
        output_path = out_file
    else:
        output_path = default_ready_import_path(source)

    rows_kept, rows_removed = prepare_import_output(
        active_root=active_root,
        source=source,
        output_path=output_path,
        fresh_csv=fresh_csv,
    )

    summary = Table(show_header=False, box=box.SIMPLE_HEAVY)
    summary.add_row("Browse root", str(active_root))
    summary.add_row("Source", display_path(source, active_root))
    if fresh_csv is not None:
        summary.add_row("Fresh export", display_path(fresh_csv, active_root))
    summary.add_row("Output", display_path(output_path, active_root))
    if is_progress_csv(source):
        mode = "fresh export merge" if fresh_csv is not None else "changed rows only"
        summary.add_row("Mode", mode)
        summary.add_row("Changed rows kept", str(rows_kept))
        summary.add_row("Unchanged rows excluded", str(rows_removed))
    else:
        summary.add_row("Removed empty-grade rows", str(rows_removed))
        summary.add_row("Rows kept", str(rows_kept))
    console.print(Panel(summary, title="Import Helper Complete", border_style="green"))


@app.command("grading-harness")
def grading_harness(
    csv_file: Optional[Path] = typer.Option(
        None, "--csv", "-c", help="Source CSV to grade. If omitted, browse from the active root."
    ),
    progress_file: Optional[Path] = typer.Option(
        None,
        "--progress-out",
        "-p",
        help="Autosave path for in-progress CSV. Default: <source_stem>__progress.csv",
    ),
    root_dir: Optional[Path] = typer.Option(
        None,
        "--root",
        help="Directory to browse for CSV files. Default: current working directory.",
    ),
) -> None:
    """Run interactive grading with fuzzy student search and autosave/resume."""
    active_root = resolve_root(root_dir)
    use_fzf = ask_use_fzf("CSV and student selection")
    source = csv_file if csv_file else pick_csv_file(active_root, use_fzf=use_fzf)
    source_is_progress = is_progress_csv(source)
    progress_context = load_progress_context(source) if source_is_progress else None
    original_source = progress_context.original_path if progress_context else source.resolve()
    sheet = read_sheet(source)
    students = build_students(sheet)
    if not students:
        raise typer.BadParameter("No student rows found in the selected CSV.")

    if progress_file:
        progress_path = progress_file
    elif source_is_progress:
        progress_path = source
    else:
        progress_path = source.with_name(f"{source.stem}{PROGRESS_SUFFIX}")

    metadata_path = write_progress_metadata(progress_path, original_source)
    save_progress(sheet, progress_path)
    last_graded_org_id: Optional[str] = None

    details = Table(show_header=False, box=box.SIMPLE_HEAVY)
    details.add_row("Browse root", str(active_root))
    details.add_row("Loaded CSV", display_path(source, active_root))
    details.add_row("Original export", display_path(original_source, active_root))
    details.add_row(
        "Detected max points", str(sheet.max_points) if sheet.max_points is not None else "not found"
    )
    details.add_row("Autosave", display_path(progress_path, active_root))
    details.add_row("Progress metadata", display_path(metadata_path, active_root))
    if use_fzf:
        details.add_row("Picker mode", "fzf")
        details.add_row("Controls", "fzf for student pick, Esc/Ctrl-C stops, Ctrl-B previous, F2 import prep menu")
    else:
        details.add_row("Picker mode", "built-in browser + fuzzy student search")
        details.add_row("Controls", "CSV browser: Enter dir/file, Backspace up, Ctrl-Q quit; prompts: Ctrl-B previous, F2 import prep menu")
    console.print(Panel(details, title="Grading Harness", border_style="cyan"))

    by_org = {student.org_defined_id: student for student in students}
    while True:
        selection = prompt_student(students, sheet, use_fzf=use_fzf)
        if selection == QUIT_SENTINEL:
            if handle_post_grading_action(active_root, progress_path, use_fzf) == "resume":
                continue
            ui_info("Stopping harness.")
            break
        if selection == PREP_SENTINEL:
            if handle_post_grading_action(active_root, progress_path, use_fzf) == "resume":
                continue
            ui_info("Stopping harness.")
            break
        if selection == BACK_SENTINEL:
            if last_graded_org_id is None:
                ui_warn("No previous graded student in this session.")
                continue
            student = by_org[last_graded_org_id]
        else:
            if not selection:
                ui_warn("Please select or type a student.")
                continue
            student = by_org.get(selection)
            if student is None:
                resolved = resolve_student_query(selection, students)
                if resolved is None:
                    ui_error("No matching student found.")
                    continue
                student = resolved

        student_row = sheet.rows[student.row_index]
        current_grade = student_row[sheet.grade_col_idx].strip()
        selected = Table(show_header=False, box=box.SIMPLE)
        selected.add_row("Student", f"{student.last_name}, {student.first_name}")
        selected.add_row("Username", student.display_username)
        selected.add_row("OrgDefinedId", student.display_org_defined_id)
        selected.add_row("Current grade", current_grade if current_grade else "<empty>")
        console.print(Panel(selected, title="Selected Student", border_style="blue"))

        while True:
            raw_grade = prompt(
                "Enter grade (Ctrl-B previous, Ctrl-Q menu, F2 menu): ",
                key_bindings=_build_keybindings(),
            ).strip()
            if raw_grade == QUIT_SENTINEL:
                if handle_post_grading_action(active_root, progress_path, use_fzf) == "resume":
                    continue
                ui_info("Stopping harness.")
                return
            if raw_grade == BACK_SENTINEL:
                if last_graded_org_id is None:
                    ui_warn("No previous graded student in this session.")
                    continue
                student = by_org[last_graded_org_id]
                student_row = sheet.rows[student.row_index]
                ui_info(
                    "Switched to previous: "
                    f"{student.last_name}, {student.first_name} "
                    f"({student.display_username}, {student.display_org_defined_id})"
                )
                ui_info(f"Current grade: {student_row[sheet.grade_col_idx].strip() or '<empty>'}")
                continue
            if raw_grade == PREP_SENTINEL:
                if handle_post_grading_action(active_root, progress_path, use_fzf) == "resume":
                    continue
                ui_info("Stopping harness.")
                return
            if raw_grade == "":
                ui_warn("Grade is required. Empty grade is not allowed.")
                continue

            try:
                normalized = normalize_decimal_input(raw_grade)
                numeric_value = Decimal(normalized)
            except typer.BadParameter as exc:
                ui_error(str(exc))
                continue

            if sheet.max_points is not None and numeric_value > sheet.max_points:
                ui_error(f"Grade must be <= {sheet.max_points}. Received: {numeric_value}")
                continue

            student_row[sheet.grade_col_idx] = normalized
            save_progress(sheet, progress_path)
            last_graded_org_id = student.org_defined_id
            ui_success(
                f"Saved {normalized} for {student.last_name}, {student.first_name}. "
                f"Progress written to {progress_path.name}"
            )
            break


@app.command("option1", hidden=True)
def option1_alias(
    ctx: typer.Context,
    csv_file: Optional[Path] = typer.Option(
        None, "--csv", "-c", help="Source CourseLink CSV. If omitted, browse from the active root."
    ),
    fresh_csv: Optional[Path] = typer.Option(
        None,
        "--fresh-csv",
        help="Fresh CourseLink export to merge changed grades onto for progress CSVs.",
    ),
    out_file: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output CSV path. Default: <source_stem>__ready_to_import.csv",
    ),
    root_dir: Optional[Path] = typer.Option(
        None,
        "--root",
        help="Directory to browse for CSV files. Default: current working directory.",
    ),
) -> None:
    """Backward-compatible alias for import-helper."""
    ui_warn("`option1` is deprecated. Use `import-helper`.")
    ctx.invoke(
        import_helper,
        csv_file=csv_file,
        fresh_csv=fresh_csv,
        out_file=out_file,
        root_dir=root_dir,
    )


@app.command("option2", hidden=True)
def option2_alias(
    ctx: typer.Context,
    csv_file: Optional[Path] = typer.Option(
        None, "--csv", "-c", help="Source CSV to grade. If omitted, browse from the active root."
    ),
    progress_file: Optional[Path] = typer.Option(
        None,
        "--progress-out",
        "-p",
        help="Autosave path for in-progress CSV. Default: <source_stem>__progress.csv",
    ),
    root_dir: Optional[Path] = typer.Option(
        None,
        "--root",
        help="Directory to browse for CSV files. Default: current working directory.",
    ),
) -> None:
    """Backward-compatible alias for grading-harness."""
    ui_warn("`option2` is deprecated. Use `grading-harness`.")
    ctx.invoke(
        grading_harness,
        csv_file=csv_file,
        progress_file=progress_file,
        root_dir=root_dir,
    )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Show a simple option menu when run without a subcommand."""
    if ctx.invoked_subcommand is not None:
        return

    menu = Table(show_header=False, box=box.SIMPLE_HEAVY)
    menu.add_row("[bold cyan]1[/]", "import-helper: create a ready-to-import CSV")
    menu.add_row("[bold cyan]2[/]", "grading-harness: interactive grading with autosave")
    console.print(Panel(menu, title="CourseLink Helper", border_style="cyan"))
    choice = typer.prompt("Enter 1 for import-helper or 2 for grading-harness", type=int)
    if choice == 1:
        ctx.invoke(import_helper, csv_file=None, out_file=None, root_dir=None)
    elif choice == 2:
        ctx.invoke(grading_harness, csv_file=None, progress_file=None, root_dir=None)
    else:
        raise typer.BadParameter("Invalid choice. Enter 1 or 2.")


def run() -> None:
    """Console-script entrypoint."""
    app()


if __name__ == "__main__":
    run()
