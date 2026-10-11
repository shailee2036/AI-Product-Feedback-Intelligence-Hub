import json
import shutil
from pathlib import Path

import pytest

from feedback_hub.config import Settings
from feedback_hub.seed.validate import SOURCE_FILE, main, validate_seed_directory

SEED_DIR = Path(__file__).resolve().parents[4] / "seed-data"
CSV_FILE = "appwrite-customer-feedback.csv"


@pytest.fixture
def seed_copy(tmp_path: Path) -> Path:
    shutil.copytree(SEED_DIR, tmp_path, dirs_exist_ok=True)
    return tmp_path


def test_committed_seed_data_is_valid() -> None:
    assert validate_seed_directory(SEED_DIR, Settings()) == []


def test_cli_exit_codes(seed_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(SEED_DIR)]) == 0
    assert main([]) == 2

    (seed_copy / SOURCE_FILE).write_text("{not json", encoding="utf-8")
    assert main([str(seed_copy)]) == 1
    assert SOURCE_FILE in capsys.readouterr().err


def test_non_synthetic_and_unknown_area_rows_fail(seed_copy: Path) -> None:
    csv_path = seed_copy / CSV_FILE
    csv_path.write_text(
        csv_path.read_text(encoding="utf-8")
        + 'REAL-001,2026-07-01T00:00:00Z,survey,startup,Billing,3,low,en,false,"Real quote"\n',
        encoding="utf-8",
    )

    problems = validate_seed_directory(seed_copy, Settings())

    assert any("is_synthetic=true" in p for p in problems)
    assert any("AW-SYN-" in p for p in problems)
    assert any("'Billing'" in p for p in problems)


def test_source_config_rules(seed_copy: Path) -> None:
    source_path = seed_copy / SOURCE_FILE
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["github"]["repository_url"] = "https://github.com/someone/else"
    source["github"]["expected_license_spdx"] = "BUSL-1.1"
    source["disclaimer"] = "This is real customer feedback, trust us."
    source_path.write_text(json.dumps(source), encoding="utf-8")

    problems = validate_seed_directory(seed_copy, Settings())

    assert len(problems) == 3


def test_source_schema_rejects_pull_requests(seed_copy: Path) -> None:
    source_path = seed_copy / SOURCE_FILE
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["github"]["include_pull_requests"] = True
    source_path.write_text(json.dumps(source), encoding="utf-8")

    assert "include_pull_requests" in validate_seed_directory(seed_copy, Settings())[0]


def test_missing_csv_fixture(seed_copy: Path) -> None:
    (seed_copy / CSV_FILE).unlink()

    assert CSV_FILE in validate_seed_directory(seed_copy, Settings())[0]
