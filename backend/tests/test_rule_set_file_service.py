from __future__ import annotations

from app.services.rule_file_service import list_runtime_rule_files
from app.services.rule_set_file_service import resolve_scan_rule_keys


def test_resolve_scan_rule_keys_defaults_to_all_enabled_rules() -> None:
    expected_rule_keys = [item.stem for item in list_runtime_rule_files()]

    normalized_set_keys, normalized_rule_keys, resolved_rule_keys = (
        resolve_scan_rule_keys(rule_set_keys=[], rule_keys=[])
    )

    assert normalized_set_keys == []
    assert normalized_rule_keys == []
    assert resolved_rule_keys == expected_rule_keys
