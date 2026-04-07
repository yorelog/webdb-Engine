"""Tests for the training data pipeline."""

from __future__ import annotations

import json

import pytest

from webdb.database.models import TrainingDataType


@pytest.fixture(autouse=True)
def _use_test_db(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("WEBDB_DB_URL", db_url)
    import webdb.database.engine as eng
    eng._engine = None
    eng._SessionFactory = None
    from webdb.database.engine import init_db
    init_db(db_url)


class TestTrainingDataPipeline:
    def _seed_records(self, count: int = 4, data_type: TrainingDataType = TrainingDataType.SFT):
        from webdb.database.engine import get_session
        from webdb.database.repository import create_training_record

        with get_session() as session:
            for i in range(count):
                create_training_record(
                    session,
                    data_type=data_type,
                    input_payload={"idx": i, "text": f"sample {i}"},
                    output_payload={"label": "login" if i % 2 == 0 else "list"},
                    split="train" if i < 3 else "val",
                )

    def test_export_creates_files(self, tmp_path):
        from webdb.training.data_pipeline import TrainingDataPipeline
        self._seed_records()
        pipeline = TrainingDataPipeline(output_dir=tmp_path / "training")
        counts = pipeline.export()
        assert counts  # at least one file written

    def test_export_file_contains_jsonl(self, tmp_path):
        from webdb.training.data_pipeline import TrainingDataPipeline
        self._seed_records()
        output_dir = tmp_path / "training"
        pipeline = TrainingDataPipeline(output_dir=output_dir)
        pipeline.export()
        files = list(output_dir.glob("*.jsonl"))
        assert files
        for f in files:
            for line in f.read_text().strip().splitlines():
                obj = json.loads(line)
                assert "input" in obj
                assert "output" in obj

    def test_export_marks_as_exported(self, tmp_path):
        from webdb.database.engine import get_session
        from webdb.database.repository import get_unexported_records
        from webdb.training.data_pipeline import TrainingDataPipeline
        self._seed_records(count=3)
        pipeline = TrainingDataPipeline(output_dir=tmp_path / "training")
        pipeline.export(mark_exported=True)
        with get_session() as session:
            remaining = get_unexported_records(session)
        assert len(remaining) == 0

    def test_no_records_returns_empty_counts(self, tmp_path):
        from webdb.training.data_pipeline import TrainingDataPipeline
        pipeline = TrainingDataPipeline(output_dir=tmp_path / "training")
        counts = pipeline.export()
        assert counts == {}

    def test_load_jsonl(self, tmp_path):
        from webdb.training.data_pipeline import TrainingDataPipeline
        self._seed_records()
        output_dir = tmp_path / "training"
        pipeline = TrainingDataPipeline(output_dir=output_dir)
        pipeline.export()
        files = list(output_dir.glob("*.jsonl"))
        assert files
        rows = pipeline.load_jsonl(files[0])
        assert isinstance(rows, list)
        assert len(rows) > 0

    def test_split_train_val(self, tmp_path):
        from webdb.training.data_pipeline import TrainingDataPipeline
        self._seed_records(count=10)
        output_dir = tmp_path / "training"
        pipeline = TrainingDataPipeline(output_dir=output_dir)
        pipeline.export()
        train, val = pipeline.split_train_val(TrainingDataType.SFT, val_fraction=0.2)
        assert len(train) + len(val) > 0
