"""Minimal package smoke test for CI and release builds."""

from __future__ import annotations

import importlib.metadata
import subprocess


EXPECTED_ENTRYPOINT = "course_link_helper.cli:run"


def main() -> None:
    import course_link_helper.cli  # noqa: F401

    entry_points = {
        entry_point.name: entry_point.value
        for entry_point in importlib.metadata.entry_points(group="console_scripts")
    }
    actual_entrypoint = entry_points.get("courselink-grader")
    if actual_entrypoint != EXPECTED_ENTRYPOINT:
        raise SystemExit(
            f"Expected console script 'courselink-grader' -> {EXPECTED_ENTRYPOINT!r}, "
            f"got {actual_entrypoint!r}"
        )

    result = subprocess.run(
        ["courselink-grader", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"CLI smoke test failed with exit code {result.returncode}:\n"
            f"{result.stdout}\n{result.stderr}"
        )

    if "Prepare CourseLink CSV files" not in result.stdout:
        raise SystemExit("CLI help output did not contain the expected help text.")


if __name__ == "__main__":
    main()

