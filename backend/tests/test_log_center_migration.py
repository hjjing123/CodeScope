from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


class OpRecorder:
    def __init__(self) -> None:
        self.added_columns: list[tuple[str, str]] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...]]] = []
        self.executed_sql: list[str] = []
        self.altered_columns: list[tuple[str, str]] = []
        self.dropped_indexes: list[tuple[str, str]] = []
        self.dropped_columns: list[tuple[str, str]] = []

    def add_column(self, table_name: str, column: Any) -> None:
        self.added_columns.append((table_name, str(column.name)))

    def create_index(
        self, index_name: str, table_name: str, columns: list[str], unique: bool = False
    ) -> None:
        self.created_indexes.append((index_name, table_name, tuple(columns)))

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)

    def alter_column(self, table_name: str, column_name: str, **_: Any) -> None:
        self.altered_columns.append((table_name, column_name))

    def drop_index(self, index_name: str, table_name: str) -> None:
        self.dropped_indexes.append((index_name, table_name))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.dropped_columns.append((table_name, column_name))

    def f(self, value: str) -> str:
        return value


def _load_migration_module(monkeypatch):
    class _Column:
        def __init__(self, name: str) -> None:
            self.name = name

    sqlalchemy_stub = types.ModuleType("sqlalchemy")
    sqlalchemy_stub.Column = lambda name, *_args, **_kwargs: _Column(name)
    sqlalchemy_stub.String = lambda *args, **kwargs: ("String", args, kwargs)
    sqlalchemy_stub.Boolean = lambda *args, **kwargs: ("Boolean", args, kwargs)
    sqlalchemy_stub.false = lambda: False

    alembic_stub = types.ModuleType("alembic")
    alembic_stub.op = types.SimpleNamespace(f=lambda value: value)

    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy_stub)
    monkeypatch.setitem(sys.modules, "alembic", alembic_stub)

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260306_0013_log_center_query_and_delete_enhancements.py"
    )
    spec = importlib.util.spec_from_file_location("migration_20260306_0013", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_log_center_migration_upgrade_operations(monkeypatch):
    module = _load_migration_module(monkeypatch)
    recorder = OpRecorder()
    monkeypatch.setattr(module, "op", recorder)

    module.upgrade()

    assert ("system_logs", "action_zh") in recorder.added_columns
    assert ("system_logs", "action_group") in recorder.added_columns
    assert ("system_logs", "summary_zh") in recorder.added_columns
    assert ("system_logs", "is_high_value") in recorder.added_columns

    created_index_names = {item[0] for item in recorder.created_indexes}
    assert "ix_system_logs_kind_occurred" in created_index_names
    assert "ix_system_logs_kind_group_occurred" in created_index_names
    assert "ix_system_logs_kind_high_value_occurred" in created_index_names
    assert "ix_system_logs_request_kind_occurred" in created_index_names

    assert len(recorder.executed_sql) == 1
    assert "UPDATE system_logs" in recorder.executed_sql[0]
    assert ("system_logs", "is_high_value") in recorder.altered_columns


def test_log_center_migration_downgrade_operations(monkeypatch):
    module = _load_migration_module(monkeypatch)
    recorder = OpRecorder()
    monkeypatch.setattr(module, "op", recorder)

    module.downgrade()

    dropped_index_names = {item[0] for item in recorder.dropped_indexes}
    assert "ix_system_logs_kind_occurred" in dropped_index_names
    assert "ix_system_logs_kind_group_occurred" in dropped_index_names
    assert "ix_system_logs_kind_high_value_occurred" in dropped_index_names
    assert "ix_system_logs_request_kind_occurred" in dropped_index_names

    assert ("system_logs", "is_high_value") in recorder.dropped_columns
    assert ("system_logs", "summary_zh") in recorder.dropped_columns
    assert ("system_logs", "action_group") in recorder.dropped_columns
    assert ("system_logs", "action_zh") in recorder.dropped_columns
