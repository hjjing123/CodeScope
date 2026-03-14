from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from neo4j.graph import Path as Neo4jPath


DEFAULT_FORBIDDEN_REL_TYPES = frozenset({"AST", "IN_FILE"})
DEFAULT_FORBIDDEN_REL_MATCH = "all"
FORBIDDEN_REL_MATCH_VALUES = {"all", "any"}
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class PathPostprocessConfig:
    enabled: bool = True
    forbidden_rel_types: frozenset[str] = DEFAULT_FORBIDDEN_REL_TYPES
    forbidden_rel_match: str = DEFAULT_FORBIDDEN_REL_MATCH
    dedupe_within_record: bool = True
    dedupe_across_rows: bool = True
    drop_empty_path_rows: bool = True


@dataclass
class PathPostprocessStats:
    raw_rows: int = 0
    kept_rows: int = 0
    dropped_duplicate_rows: int = 0
    dropped_empty_rows: int = 0
    dropped_paths_for_rel: int = 0
    dropped_paths_duplicate: int = 0


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def _csv_set_env(name: str, default: frozenset[str]) -> frozenset[str]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        return frozenset()
    return frozenset(values)


def _choice_env(name: str, default: str, allowed: set[str]) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in allowed:
        return value
    return default


def load_path_postprocess_config() -> PathPostprocessConfig:
    enabled = _bool_env(
        "PATH_RESULT_POST_ENABLED", _bool_env("PATH_FILTER_ENABLED", True)
    )
    forbidden = _csv_set_env(
        "PATH_RESULT_POST_FORBIDDEN_REL_TYPES",
        _csv_set_env("PATH_FILTER_FORBID_REL_TYPES", DEFAULT_FORBIDDEN_REL_TYPES),
    )
    forbidden_match = _choice_env(
        "PATH_RESULT_POST_FORBIDDEN_REL_MATCH",
        _choice_env(
            "PATH_FILTER_FORBID_REL_MATCH",
            DEFAULT_FORBIDDEN_REL_MATCH,
            FORBIDDEN_REL_MATCH_VALUES,
        ),
        FORBIDDEN_REL_MATCH_VALUES,
    )
    return PathPostprocessConfig(
        enabled=enabled,
        forbidden_rel_types=forbidden,
        forbidden_rel_match=forbidden_match,
        dedupe_within_record=_bool_env("PATH_RESULT_POST_DEDUPE_WITHIN_RECORD", True),
        dedupe_across_rows=_bool_env("PATH_RESULT_POST_DEDUPE_ROWS", True),
        drop_empty_path_rows=_bool_env("PATH_RESULT_POST_DROP_EMPTY_PATH_ROWS", True),
    )


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_file_component(value: Any) -> str:
    raw = _norm_text(value).replace("\\", "/")
    if not raw:
        return ""
    marker = "/source/"
    if marker in raw:
        return raw.split(marker, 1)[1]
    return Path(raw).name


def _node_fingerprint_part(node: Any) -> str:
    labels = ":".join(sorted(node.labels)) if getattr(node, "labels", None) else "Node"
    name = _norm_text(
        node.get("name")
        or node.get("selector")
        or node.get("method")
        or node.get("methodFullName")
    )
    node_type = _norm_text(node.get("type"))
    file_name = _normalize_file_component(node.get("file"))
    line = _norm_text(node.get("line"))
    return f"{labels}({name}|{node_type}|{file_name}:{line})"


def _rel_fingerprint_part(rel: Any) -> str:
    rel_type = _norm_text(getattr(rel, "type", "REL"))
    selector = _norm_text(rel.get("selector") or rel.get("name") or rel.get("method"))
    arg_pos = _norm_text(rel.get("argPosition"))
    return f"{rel_type}({selector}|{arg_pos})"


def structural_path_fingerprint(path: Neo4jPath) -> str:
    node_parts = ",".join(_node_fingerprint_part(node) for node in path.nodes)
    rel_parts = ",".join(_rel_fingerprint_part(rel) for rel in path.relationships)
    return f"N[{node_parts}]|R[{rel_parts}]"


def _is_path_allowed(path: Neo4jPath, cfg: PathPostprocessConfig) -> bool:
    if not cfg.forbidden_rel_types:
        return True
    rel_types = [rel.type for rel in path.relationships]
    if not rel_types:
        return True
    forbidden_hits = sum(
        1 for rel_type in rel_types if rel_type in cfg.forbidden_rel_types
    )
    if forbidden_hits == 0:
        return True
    if cfg.forbidden_rel_match == "all":
        return forbidden_hits < len(rel_types)
    return False


def _looks_like_path(value: Any) -> bool:
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def _normalize_value(
    value: Any,
    cfg: PathPostprocessConfig,
    fingerprint_fn: Callable[[Neo4jPath], str],
) -> tuple[Any, bool, list[str], int, int]:
    had_path = False
    path_fingerprints: list[str] = []
    dropped_for_rel = 0
    dropped_dup = 0

    if _looks_like_path(value):
        had_path = True
        if cfg.enabled and not _is_path_allowed(value, cfg):
            return None, had_path, path_fingerprints, 1, 0
        path_fingerprints.append(fingerprint_fn(value))
        return value, had_path, path_fingerprints, 0, 0

    if isinstance(value, list):
        out: list[Any] = []
        seen: set[str] = set()
        for item in value:
            if _looks_like_path(item):
                had_path = True
                if cfg.enabled and not _is_path_allowed(item, cfg):
                    dropped_for_rel += 1
                    continue
                fingerprint = fingerprint_fn(item)
                if cfg.enabled and cfg.dedupe_within_record and fingerprint in seen:
                    dropped_dup += 1
                    continue
                seen.add(fingerprint)
                path_fingerprints.append(fingerprint)
                out.append(item)
                continue
            out.append(item)
        return out, had_path, path_fingerprints, dropped_for_rel, dropped_dup

    return value, had_path, path_fingerprints, 0, 0


def postprocess_result_records(
    records: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    cfg: PathPostprocessConfig,
    fingerprint_fn: Callable[[Neo4jPath], str] = structural_path_fingerprint,
) -> tuple[list[dict[str, Any]], PathPostprocessStats]:
    stats = PathPostprocessStats(raw_rows=len(records))
    if not cfg.enabled:
        out = [{key: record.get(key) for key in keys} for record in records]
        stats.kept_rows = len(out)
        return out, stats

    out: list[dict[str, Any]] = []
    seen_row_fingerprints: set[str] = set()
    for record in records:
        row: dict[str, Any] = {}
        had_any_path = False
        row_path_fingerprints: list[str] = []
        row_drop_for_rel = 0
        row_drop_dup_path = 0

        for key in keys:
            raw_value = record.get(key)
            normalized, had_path, fingerprints, drop_rel, drop_dup = _normalize_value(
                raw_value,
                cfg,
                fingerprint_fn,
            )
            if (
                (not had_path)
                and ("path" in key.lower())
                and (raw_value is None or isinstance(raw_value, list))
            ):
                had_path = True
            row[key] = normalized
            if had_path:
                had_any_path = True
                row_path_fingerprints.extend(f"{key}:{item}" for item in fingerprints)
            row_drop_for_rel += drop_rel
            row_drop_dup_path += drop_dup

        stats.dropped_paths_for_rel += row_drop_for_rel
        stats.dropped_paths_duplicate += row_drop_dup_path

        if cfg.drop_empty_path_rows and had_any_path and not row_path_fingerprints:
            stats.dropped_empty_rows += 1
            continue

        if cfg.dedupe_across_rows and row_path_fingerprints:
            row_fingerprint = "|".join(row_path_fingerprints)
            if row_fingerprint in seen_row_fingerprints:
                stats.dropped_duplicate_rows += 1
                continue
            seen_row_fingerprints.add(row_fingerprint)

        out.append(row)

    stats.kept_rows = len(out)
    return out, stats
