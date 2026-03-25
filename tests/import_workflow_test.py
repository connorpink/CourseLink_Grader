"""Regression tests for safe import prep flows."""

from __future__ import annotations

import csv
import types
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def install_stubs() -> None:
    if "typer" not in sys.modules:
        typer = types.ModuleType("typer")

        class BadParameter(Exception):
            pass

        class Exit(Exception):
            def __init__(self, code: int = 0) -> None:
                super().__init__(code)
                self.code = code

        class Context:
            def invoke(self, func, **kwargs):
                return func(**kwargs)

        class Typer:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def command(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def callback(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def __call__(self, *args, **kwargs):
                return None

        def Option(default=None, *args, **kwargs):
            return default

        def prompt(*args, **kwargs):
            raise AssertionError("Interactive prompt stub should not be called in tests")

        def confirm(*args, **kwargs):
            raise AssertionError("Interactive confirm stub should not be called in tests")

        typer.BadParameter = BadParameter
        typer.Exit = Exit
        typer.Context = Context
        typer.Typer = Typer
        typer.Option = Option
        typer.prompt = prompt
        typer.confirm = confirm
        sys.modules["typer"] = typer

    if "prompt_toolkit" not in sys.modules:
        prompt_toolkit = types.ModuleType("prompt_toolkit")

        def prompt(*args, **kwargs):
            raise AssertionError("Interactive prompt_toolkit stub should not be called in tests")

        prompt_toolkit.prompt = prompt
        sys.modules["prompt_toolkit"] = prompt_toolkit

        application = types.ModuleType("prompt_toolkit.application")

        class Application:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def run(self):
                return None

        application.Application = Application
        sys.modules["prompt_toolkit.application"] = application

        completion = types.ModuleType("prompt_toolkit.completion")

        class Completion:
            def __init__(self, *args, **kwargs) -> None:
                pass

        class Completer:
            pass

        completion.Completion = Completion
        completion.Completer = Completer
        sys.modules["prompt_toolkit.completion"] = completion

        key_binding = types.ModuleType("prompt_toolkit.key_binding")

        class KeyBindings:
            def add(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

        key_binding.KeyBindings = KeyBindings
        sys.modules["prompt_toolkit.key_binding"] = key_binding

        layout = types.ModuleType("prompt_toolkit.layout")

        class Layout:
            def __init__(self, *args, **kwargs) -> None:
                pass

        layout.Layout = Layout
        sys.modules["prompt_toolkit.layout"] = layout

        containers = types.ModuleType("prompt_toolkit.layout.containers")

        class HSplit:
            def __init__(self, *args, **kwargs) -> None:
                pass

        containers.HSplit = HSplit
        sys.modules["prompt_toolkit.layout.containers"] = containers

        widgets = types.ModuleType("prompt_toolkit.widgets")

        class Frame:
            def __init__(self, *args, **kwargs) -> None:
                pass

        class Label:
            def __init__(self, text="") -> None:
                self.text = text

        class RadioList:
            def __init__(self, values):
                self.values = values
                self.current_value = values[0][0] if values else None
                self._selected_index = 0

        widgets.Frame = Frame
        widgets.Label = Label
        widgets.RadioList = RadioList
        sys.modules["prompt_toolkit.widgets"] = widgets

    if "rich" not in sys.modules:
        rich = types.ModuleType("rich")
        box = types.SimpleNamespace(SIMPLE_HEAVY="simple_heavy", SIMPLE="simple")
        rich.box = box
        sys.modules["rich"] = rich

        console_module = types.ModuleType("rich.console")

        class Console:
            def print(self, *args, **kwargs) -> None:
                pass

        console_module.Console = Console
        sys.modules["rich.console"] = console_module

        panel_module = types.ModuleType("rich.panel")

        class Panel:
            def __init__(self, *args, **kwargs) -> None:
                pass

        panel_module.Panel = Panel
        sys.modules["rich.panel"] = panel_module

        table_module = types.ModuleType("rich.table")

        class Table:
            def __init__(self, *args, **kwargs) -> None:
                pass

            def add_row(self, *args, **kwargs) -> None:
                pass

        table_module.Table = Table
        sys.modules["rich.table"] = table_module


install_stubs()

import typer
from course_link_helper import cli


HEADERS = [
    "OrgDefinedId",
    "Username",
    "Last Name",
    "First Name",
    "Email",
    "Sections",
    "Lab 8 Points Grade <Numeric MaxPoints:75 Weight:1.5>",
    "End-of-Line Indicator",
]


def make_row(org_id: str, first: str, last: str, grade: str) -> list[str]:
    return [
        org_id,
        f"#{first.lower()}.{last.lower()}",
        last,
        first,
        f"{first.lower()}@example.com",
        "L01",
        grade,
        "#",
    ]


def read_rows(path: Path) -> list[list[str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        return list(reader)


def write_csv(path: Path, rows: list[list[str]]) -> None:
    cli.write_sheet(path, HEADERS, rows, "utf-8")


def assert_bad_parameter(fn, expected_fragment: str) -> None:
    try:
        fn()
    except typer.BadParameter as exc:
        if expected_fragment not in str(exc):
            raise AssertionError(f"Expected {expected_fragment!r} in {exc!r}") from exc
        return
    raise AssertionError("Expected typer.BadParameter")


def main() -> None:
    with TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        original = tmp / "grades.csv"
        progress = tmp / "grades__progress.csv"
        ready = tmp / "grades__progress__ready_to_import.csv"
        fresh = tmp / "grades_fresh.csv"
        plain_ready = tmp / "grades__ready_to_import.csv"

        original_rows = [
            make_row("#1", "Alice", "Able", "10"),
            make_row("#2", "Bob", "Baker", ""),
            make_row("#3", "Cara", "Clark", "5"),
        ]
        write_csv(original, original_rows)

        cli.write_progress_metadata(progress, original)

        write_csv(progress, original_rows)
        kept, removed = cli.prepare_import_output(tmp, progress, ready)
        assert kept == 0
        assert removed == 3
        assert read_rows(ready) == []

        progress_rows = [
            make_row("#1", "Alice", "Able", "10"),
            make_row("#2", "Bob", "Baker", "12"),
            make_row("#3", "Cara", "Clark", "5"),
        ]
        write_csv(progress, progress_rows)
        kept, removed = cli.prepare_import_output(tmp, progress, ready)
        assert kept == 1
        assert removed == 2
        changed_only_rows = read_rows(ready)
        assert len(changed_only_rows) == 1
        assert changed_only_rows[0][0] == "#2"
        assert changed_only_rows[0][6] == "12"

        progress_rows = [
            make_row("#1", "Alice", "Able", "11"),
            make_row("#2", "Bob", "Baker", ""),
            make_row("#3", "Cara", "Clark", "5"),
        ]
        write_csv(progress, progress_rows)
        kept, _ = cli.prepare_import_output(tmp, progress, ready)
        assert kept == 1
        assert read_rows(ready)[0][0] == "#1"
        assert read_rows(ready)[0][6] == "11"

        fresh_rows = [
            make_row("#1", "Alice", "Able", "99"),
            make_row("#2", "Bob", "Baker", "1"),
            make_row("#3", "Cara", "Clark", "6"),
        ]
        write_csv(fresh, fresh_rows)
        kept, _ = cli.prepare_import_output(tmp, progress, ready, fresh_csv=fresh)
        assert kept == 1
        fresh_merge_rows = read_rows(ready)
        assert fresh_merge_rows[0][0] == "#1"
        assert fresh_merge_rows[0][6] == "11"
        assert fresh_merge_rows[0][5] == "L01"

        write_csv(original, original_rows)
        kept, removed = cli.prepare_import_output(tmp, original, plain_ready)
        assert kept == 2
        assert removed == 1
        plain_rows = read_rows(plain_ready)
        assert [row[0] for row in plain_rows] == ["#1", "#3"]

        legacy_original = tmp / "legacy.csv"
        legacy_progress = tmp / "legacy__progress.csv"
        write_csv(legacy_original, [make_row("#9", "Dana", "Drew", "7")])
        write_csv(legacy_progress, [make_row("#9", "Dana", "Drew", "7")])
        legacy_original.unlink()
        assert_bad_parameter(
            lambda: cli.prepare_import_output(tmp, legacy_progress, tmp / "legacy_ready.csv"),
            "Could not find the original export",
        )

        bad_fresh = tmp / "bad_fresh.csv"
        cli.write_sheet(
            bad_fresh,
            HEADERS[:-1],
            [make_row("#1", "Alice", "Able", "10")[:-1]],
            "utf-8",
        )
        assert_bad_parameter(
            lambda: cli.prepare_import_output(tmp, progress, ready, fresh_csv=bad_fresh),
            "does not match the original export headers",
        )

        assert_bad_parameter(
            lambda: cli.prepare_import_output(tmp, original, plain_ready, fresh_csv=fresh),
            "--fresh-csv can only be used",
        )


if __name__ == "__main__":
    main()
