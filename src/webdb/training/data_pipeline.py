"""Training data pipeline.

Exports training records from the database into JSONL files ready for
supervised fine-tuning (SFT), DPO, or reward-model training.
"""

from __future__ import annotations

import json
from pathlib import Path

from webdb.config.settings import get_settings
from webdb.database.engine import get_session
from webdb.database.models import TrainingDataType
from webdb.database.repository import get_unexported_records


class TrainingDataPipeline:
    """Exports training records to JSONL files.

    Produces separate files per data type and split::

        data/training/
          sft_train.jsonl
          sft_val.jsonl
          preference_train.jsonl
          failure_train.jsonl
          reward_train.jsonl
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        self._output_dir = output_dir or get_settings().training_data_dir

    def export(
        self,
        data_type: TrainingDataType | None = None,
        mark_exported: bool = True,
    ) -> dict[str, int]:
        """Export unexported training records to JSONL.

        Returns a dict mapping filename → record count.
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = {}

        with get_session() as session:
            records = get_unexported_records(
                session,
                data_type=data_type.value if data_type else None,
            )

            # Group by (data_type, split)
            buckets: dict[tuple[str, str], list] = {}
            for rec in records:
                key = (rec.data_type.value, rec.split)
                buckets.setdefault(key, []).append(rec)

            for (dtype, split), recs in buckets.items():
                fname = self._output_dir / f"{dtype}_{split}.jsonl"
                with fname.open("a", encoding="utf-8") as fh:
                    for rec in recs:
                        line = json.dumps(
                            {
                                "id": rec.id,
                                "type": rec.data_type.value,
                                "split": rec.split,
                                "input": rec.input_payload,
                                "output": rec.output_payload,
                                "reward": rec.reward,
                            },
                            ensure_ascii=False,
                        )
                        fh.write(line + "\n")
                        if mark_exported:
                            rec.exported = True
                counts[str(fname)] = counts.get(str(fname), 0) + len(recs)

        return counts

    def load_jsonl(self, path: Path) -> list[dict]:
        """Load a JSONL file into a list of dicts."""
        rows: list[dict] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def split_train_val(
        self,
        data_type: TrainingDataType,
        val_fraction: float = 0.1,
    ) -> tuple[list[dict], list[dict]]:
        """Return (train_rows, val_rows) for a given data type."""
        train_path = self._output_dir / f"{data_type.value}_train.jsonl"
        val_path = self._output_dir / f"{data_type.value}_val.jsonl"

        all_rows: list[dict] = []
        if train_path.exists():
            all_rows += self.load_jsonl(train_path)
        if val_path.exists():
            all_rows += self.load_jsonl(val_path)

        split_idx = max(1, int(len(all_rows) * (1 - val_fraction)))
        return all_rows[:split_idx], all_rows[split_idx:]
