"""Tests for the local sync layer."""

from __future__ import annotations

import pytest

from webdb.sync.storage_adapters import CSVAdapter, ParquetAdapter, SQLiteAdapter, get_adapter
from webdb.sync.sync_manager import _url_to_table_name


class TestSQLiteAdapter:
    @pytest.fixture
    def adapter(self, tmp_path):
        db = tmp_path / "test.db"
        return SQLiteAdapter(db)

    def test_write_and_read(self, adapter):
        rows = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        written = adapter.write_rows("users", rows)
        assert written == 2
        result = adapter.read_rows("users")
        assert len(result) == 2
        names = {r["name"] for r in result}
        assert names == {"Alice", "Bob"}

    def test_empty_write(self, adapter):
        assert adapter.write_rows("users", []) == 0

    def test_schema_evolution(self, adapter):
        adapter.write_rows("t", [{"a": "1"}])
        adapter.write_rows("t", [{"a": "2", "b": "new_col"}])
        rows = adapter.read_rows("t")
        assert len(rows) == 2

    def test_json_serialization(self, adapter):
        rows = [{"name": "Alice", "meta": {"key": "value"}}]
        adapter.write_rows("data", rows)
        result = adapter.read_rows("data")
        assert len(result) == 1


class TestCSVAdapter:
    @pytest.fixture
    def adapter(self, tmp_path):
        return CSVAdapter(tmp_path)

    def test_write_and_read(self, adapter):
        rows = [{"col1": "a", "col2": "b"}]
        written = adapter.write_rows("table1", rows)
        assert written == 1
        result = adapter.read_rows("table1")
        assert result[0]["col1"] == "a"

    def test_empty_write(self, adapter):
        assert adapter.write_rows("t", []) == 0

    def test_append(self, adapter):
        adapter.write_rows("t", [{"x": "1"}])
        adapter.write_rows("t", [{"x": "2"}])
        rows = adapter.read_rows("t", limit=100)
        assert len(rows) == 2

    def test_missing_table_returns_empty(self, adapter):
        assert adapter.read_rows("nonexistent") == []


class TestParquetAdapter:
    pytest.importorskip("pyarrow")

    @pytest.fixture
    def adapter(self, tmp_path):
        return ParquetAdapter(tmp_path)

    def test_write_and_read(self, adapter):
        rows = [{"a": 1, "b": "hello"}]
        written = adapter.write_rows("data", rows)
        assert written == 1
        result = adapter.read_rows("data")
        assert len(result) == 1
        assert result[0]["b"] == "hello"

    def test_append(self, adapter):
        adapter.write_rows("data", [{"a": 1}])
        adapter.write_rows("data", [{"a": 2}])
        result = adapter.read_rows("data", limit=100)
        assert len(result) == 2

    def test_missing_table_returns_empty(self, adapter):
        assert adapter.read_rows("missing") == []


class TestGetAdapter:
    def test_sqlite(self, tmp_path):
        adapter = get_adapter("sqlite", tmp_path / "x.db")
        assert isinstance(adapter, SQLiteAdapter)

    def test_csv(self, tmp_path):
        adapter = get_adapter("csv", tmp_path)
        assert isinstance(adapter, CSVAdapter)

    def test_unsupported(self, tmp_path):
        with pytest.raises(ValueError):
            get_adapter("mysql", tmp_path)


class TestUrlToTableName:
    def test_basic(self):
        name = _url_to_table_name("https://example.com/data/list")
        assert "/" not in name
        assert "." not in name

    def test_long_url_truncated(self):
        name = _url_to_table_name("https://example.com/" + "a" * 200)
        assert len(name) <= 64

    def test_empty_fallback(self):
        name = _url_to_table_name("https://")
        assert name == "webdb_table"
