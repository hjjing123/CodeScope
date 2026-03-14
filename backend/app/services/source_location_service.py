from __future__ import annotations

import os
import re
import uuid
from functools import lru_cache
from pathlib import Path

from app.config import get_settings


_SOURCE_SUFFIXES = (".java", ".kt", ".groovy", ".scala")
_TMP_PREFIX_RE = re.compile(
    r"(?:^|/)(?:tmp|private/tmp)/jimple2cpg-[^/]+/(.+)$", re.IGNORECASE
)


def normalize_positive_line(value: object) -> int | None:
    try:
        normalized = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if normalized is None or normalized <= 0:
        return None
    return normalized


def normalize_graph_location(
    *,
    version_id: uuid.UUID,
    file_path: str | None,
    line: object,
    func_name: str | None = None,
    code_snippet: str | None = None,
    node_ref: str | None = None,
    labels: list[str] | None = None,
    infer_line: bool = True,
) -> tuple[str | None, int | None]:
    resolved_path = resolve_snapshot_relative_source_path(
        version_id=version_id,
        raw_path=file_path,
    )
    display_path = resolved_path or guess_display_source_path(raw_path=file_path)
    normalized_line = normalize_positive_line(line)
    if infer_line and normalized_line is None and resolved_path:
        normalized_line = infer_source_line(
            version_id=version_id,
            relative_path=resolved_path,
            func_name=func_name,
            code_snippet=code_snippet,
            node_ref=node_ref,
            labels=labels,
        )
    return display_path, normalized_line


def resolve_snapshot_relative_source_path(
    *, version_id: uuid.UUID, raw_path: str | None
) -> str | None:
    normalized = _normalize_path(raw_path)
    if not normalized:
        return None

    return _resolve_snapshot_relative_source_path_cached(str(version_id), normalized)


@lru_cache(maxsize=4096)
def _resolve_snapshot_relative_source_path_cached(
    version_id_text: str, normalized: str
) -> str | None:
    version_id = uuid.UUID(version_id_text)

    source_root = _snapshot_source_root(version_id=version_id)
    if not source_root.exists() or not source_root.is_dir():
        return None

    source_root_resolved = source_root.resolve()
    candidates = _candidate_source_paths(normalized)
    for candidate in candidates:
        resolved = (source_root_resolved / candidate).resolve()
        if not resolved.exists() or not resolved.is_file():
            continue
        relative = resolved.relative_to(source_root_resolved).as_posix()
        if _is_preferred_source_relative_path(relative):
            return relative

    indexed_files = _snapshot_relative_files(str(version_id))
    best_match: str | None = None
    best_rank: tuple[int, int, int, int, int] | None = None
    for relative in indexed_files:
        rank = _rank_relative_candidate_match(relative=relative, candidates=candidates)
        if rank is None:
            continue
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best_match = relative
    return best_match


def guess_display_source_path(*, raw_path: str | None) -> str | None:
    normalized = _normalize_path(raw_path)
    if not normalized:
        return None
    candidates = _candidate_source_paths(normalized)
    source_candidates = [
        candidate
        for candidate in candidates
        if candidate.lower().endswith(_SOURCE_SUFFIXES)
    ]
    if source_candidates:
        source_candidates.sort(key=_display_candidate_rank)
        return source_candidates[0]
    non_tmp_candidates = [candidate for candidate in candidates if candidate]
    if non_tmp_candidates:
        non_tmp_candidates.sort(key=_display_candidate_rank)
        return non_tmp_candidates[0]
    return normalized


def _display_candidate_rank(candidate: str) -> tuple[int, int, int, int, int]:
    lowered = candidate.lower()
    starts_with_src = 0 if lowered.startswith("src/") else 1
    tmp_penalty = 1 if lowered.startswith("tmp/") or "/tmp/" in lowered else 0
    target_penalty = 1 if lowered.startswith("target/") or "/target/" in lowered else 0
    parts = Path(candidate).parts
    bare_name_penalty = 1 if len(parts) <= 1 else 0
    return (
        starts_with_src,
        tmp_penalty,
        target_penalty,
        bare_name_penalty,
        -len(parts),
    )


def infer_source_line(
    *,
    version_id: uuid.UUID,
    relative_path: str,
    func_name: str | None = None,
    code_snippet: str | None = None,
    node_ref: str | None = None,
    labels: list[str] | None = None,
) -> int | None:
    source_file = _snapshot_source_root(version_id=version_id) / relative_path
    if not source_file.exists() or not source_file.is_file():
        return None

    try:
        lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines:
        return None

    normalized_func = str(func_name or "").strip()
    normalized_labels = {
        str(item).strip() for item in labels or [] if str(item).strip()
    }
    normalized_method_full_name = _extract_method_full_name(node_ref=node_ref)
    normalized_decl_kind = _extract_variable_decl_kind(node_ref=node_ref)

    method_decl_line = _select_method_decl_line(
        lines=lines,
        method_name=normalized_func,
        method_full_name=normalized_method_full_name,
    )
    method_start, method_end = _method_context_range(
        lines=lines,
        method_name=normalized_func,
        method_full_name=normalized_method_full_name,
    )

    code_line = _find_code_snippet_line(lines=lines, code_snippet=code_snippet)
    if code_line is not None:
        return code_line

    if normalized_func == "<init>":
        constructor_name = _extract_constructor_class_name(
            node_ref=node_ref, file_path=relative_path
        )
        if constructor_name:
            constructor_line = _find_regex_line(
                lines=lines,
                pattern=rf"\bnew\s+{re.escape(constructor_name)}\s*\(",
                start=method_start,
                end=method_end,
            )
            if constructor_line is not None:
                return constructor_line
            constructor_line = _find_regex_line(
                lines=lines,
                pattern=rf"\bnew\s+{re.escape(constructor_name)}\s*\(",
            )
            if constructor_line is not None:
                return constructor_line

    variable_name = _extract_variable_name(node_ref=node_ref)
    if variable_name:
        if normalized_decl_kind == "param":
            if method_decl_line is not None:
                variable_line = _find_token_line_in_range(
                    lines=lines,
                    token=variable_name,
                    start=method_decl_line,
                    end=min(len(lines), method_decl_line + 12),
                )
                if variable_line is not None:
                    return variable_line
                return method_decl_line
            variable_line = _find_token_line_in_range(
                lines=lines,
                token=variable_name,
                start=1,
                end=len(lines),
            )
            if variable_line is not None:
                return variable_line
        else:
            variable_line = _find_token_line_in_range(
                lines=lines,
                token=variable_name,
                start=method_start,
                end=method_end,
            )
            if variable_line is not None:
                return variable_line
            variable_line = _find_token_line_in_range(
                lines=lines,
                token=variable_name,
                start=1,
                end=len(lines),
            )
            if variable_line is not None:
                return variable_line

    if normalized_func and "Method" in normalized_labels:
        if method_decl_line is not None:
            return method_decl_line

    if normalized_func and ({"Var", "Argument", "Reference"} & normalized_labels):
        if method_decl_line is not None:
            return method_decl_line

    if normalized_func and normalized_func not in {"<init>", "<clinit>"}:
        call_line = _find_regex_line(
            lines=lines,
            pattern=rf"(?:\.|\b){re.escape(normalized_func)}\s*\(",
            skip_decl_token=normalized_func,
        )
        if call_line is not None:
            return call_line
    return None


def _snapshot_source_root(*, version_id: uuid.UUID) -> Path:
    return _absolute_snapshot_root() / str(version_id) / "source"


def _absolute_snapshot_root() -> Path:
    normalized = Path(os.path.normpath(str(get_settings().snapshot_storage_root)))
    if normalized.is_absolute():
        return normalized
    backend_root = Path(__file__).resolve().parents[2]
    return Path(os.path.normpath(str(backend_root / normalized)))


def _normalize_path(raw_path: str | None) -> str:
    return str(raw_path or "").replace("\\", "/").strip()


def _candidate_source_paths(raw_path: str) -> list[str]:
    candidates: list[str] = []

    def _add(value: str | None) -> None:
        cleaned = str(value or "").strip().lstrip("/")
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    normalized = _normalize_path(raw_path)
    compiled_candidates = [
        normalized,
        _strip_source_prefix(normalized),
        _strip_tmp_compile_prefix(normalized),
    ]
    source_variants: list[str] = []
    for current in compiled_candidates:
        if current.lower().endswith(".class"):
            source_variants.extend(
                [
                    f"{current[:-6]}.java",
                    _strip_source_prefix(f"{current[:-6]}.java"),
                    _strip_tmp_compile_prefix(f"{current[:-6]}.java"),
                ]
            )
    for item in source_variants:
        _add(item)
    for item in compiled_candidates:
        _add(item)

    for current in list(candidates):
        _add(Path(current).name)
    return candidates


@lru_cache(maxsize=128)
def _snapshot_relative_files(version_id_text: str) -> tuple[str, ...]:
    source_root = _snapshot_source_root(version_id=uuid.UUID(version_id_text))
    if not source_root.exists() or not source_root.is_dir():
        return ()
    files: list[str] = []
    for entry in source_root.rglob("*"):
        if entry.is_file():
            files.append(entry.relative_to(source_root).as_posix())
    return tuple(sorted(files))


def _rank_relative_candidate_match(
    *, relative: str, candidates: list[str]
) -> tuple[int, int, int, int, int] | None:
    candidate_index: int | None = None
    exact = 1
    for index, candidate in enumerate(candidates):
        if not candidate:
            continue
        if relative == candidate:
            candidate_index = index
            exact = 0
            break
        if relative.endswith(candidate) or candidate.endswith(relative):
            candidate_index = index
            break
    if candidate_index is None:
        return None
    preferred_source = 0 if _is_preferred_source_relative_path(relative) else 1
    class_penalty = 1 if relative.lower().endswith(".class") else 0
    path_depth = len(Path(relative).parts)
    return (candidate_index, preferred_source, class_penalty, exact, path_depth)


def _is_preferred_source_relative_path(relative: str) -> bool:
    lowered = relative.lower()
    if lowered.endswith(_SOURCE_SUFFIXES) and (
        lowered.startswith("src/") or "/src/" in lowered
    ):
        return True
    return False


def _strip_source_prefix(value: str) -> str:
    lowered = value.lower()
    marker = "/source/"
    index = lowered.rfind(marker)
    if index >= 0:
        return value[index + len(marker) :]
    if lowered.startswith("source/"):
        return value[len("source/") :]
    return value


def _strip_tmp_compile_prefix(value: str) -> str:
    normalized = _normalize_path(value)
    match = _TMP_PREFIX_RE.search(normalized)
    if match:
        return match.group(1)

    lowered = normalized.lower()
    markers = (
        "src/main/java/",
        "src/test/java/",
        "src/main/kotlin/",
        "src/test/kotlin/",
        "src/main/groovy/",
        "src/test/groovy/",
        "com/",
        "org/",
        "io/",
        "net/",
        "javax/",
        "jakarta/",
    )
    for marker in markers:
        index = lowered.find(marker)
        if index >= 0:
            return normalized[index:]
    return normalized


def _find_code_snippet_line(
    *, lines: list[str], code_snippet: str | None
) -> int | None:
    snippet = str(code_snippet or "").strip()
    if not snippet or len(snippet) < 3:
        return None
    condensed = re.sub(r"\s+", "", snippet)
    if not condensed or len(condensed) < 3:
        return None
    for index, line in enumerate(lines, start=1):
        if _is_ignorable_source_line(line):
            continue
        if condensed in re.sub(r"\s+", "", line):
            return index
    return None


def _find_regex_line(
    *,
    lines: list[str],
    pattern: str,
    start: int | None = None,
    end: int | None = None,
    skip_decl_token: str | None = None,
) -> int | None:
    compiled = re.compile(pattern)
    lo = max(1, int(start or 1))
    hi = min(len(lines), int(end or len(lines)))
    if lo > hi:
        return None
    for index in range(lo, hi + 1):
        line = lines[index - 1]
        if _is_ignorable_source_line(line):
            continue
        if not compiled.search(line):
            continue
        if skip_decl_token and _likely_method_decl_line(line, skip_decl_token):
            continue
        return index
    return None


def _find_token_line_in_range(
    *,
    lines: list[str],
    token: str,
    start: int | None,
    end: int | None,
    skip_decl: bool = False,
) -> int | None:
    normalized_token = str(token or "").strip()
    if not lines or not normalized_token:
        return None
    lo = max(1, int(start or 1))
    hi = min(len(lines), int(end or len(lines)))
    if lo > hi:
        return None
    pattern = re.compile(rf"\b{re.escape(normalized_token)}\b")
    for index in range(lo, hi + 1):
        line = lines[index - 1]
        if _is_ignorable_source_line(line):
            continue
        if not pattern.search(line):
            continue
        if skip_decl and _likely_method_decl_line(line, normalized_token):
            continue
        return index
    return None


def _is_ignorable_source_line(line_text: str) -> bool:
    stripped = str(line_text or "").strip()
    return (
        not stripped
        or stripped.startswith("//")
        or stripped.startswith("/*")
        or stripped.startswith("*")
    )


def _likely_control_stmt(line_text: str) -> bool:
    stripped = str(line_text or "").strip().lower()
    for keyword in (
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "throw",
        "new",
        "else",
    ):
        if stripped.startswith(f"{keyword} ") or stripped.startswith(f"{keyword}("):
            return True
    return False


def _likely_method_decl_line(line_text: str, method_name: str) -> bool:
    normalized_method = str(method_name or "").strip()
    stripped = str(line_text or "").strip()
    if not stripped or not normalized_method:
        return False
    if _likely_control_stmt(stripped):
        return False
    if re.search(rf"\.\s*{re.escape(normalized_method)}\s*\(", stripped):
        return False
    if not re.search(rf"\b{re.escape(normalized_method)}\s*\(", stripped):
        return False
    if re.search(
        r"\b(public|private|protected|static|final|abstract|native|synchronized|default)\b",
        stripped,
    ):
        return True
    if re.search(r"\)\s*(throws\b|[{;])", stripped):
        return True
    prefix = stripped.split(normalized_method, 1)[0]
    if prefix and re.search(r"[A-Za-z0-9_<>\[\]]\s+$", prefix):
        return True
    return False


def _signature_window(lines: list[str], start_line: int, max_lines: int = 12) -> str:
    if start_line <= 0:
        return ""
    out: list[str] = []
    for index in range(start_line - 1, min(len(lines), start_line - 1 + max_lines)):
        segment = lines[index].strip()
        if segment:
            out.append(segment)
        if ")" in segment and ("{" in segment or ";" in segment or "throws" in segment):
            break
        if "{" in segment:
            break
    return " ".join(out)


def _extract_param_text_from_signature(signature: str, method_name: str) -> str:
    normalized_signature = str(signature or "")
    normalized_method = str(method_name or "").strip()
    if not normalized_signature or not normalized_method:
        return ""
    match = re.search(rf"\b{re.escape(normalized_method)}\s*\(", normalized_signature)
    if not match:
        return ""
    start_index = match.end() - 1
    depth = 0
    params_start = start_index + 1
    for index in range(start_index, len(normalized_signature)):
        char = normalized_signature[index]
        if char == "(":
            depth += 1
            if depth == 1:
                params_start = index + 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return normalized_signature[params_start:index]
    return ""


def _count_params_text(raw: str) -> int:
    text = str(raw or "").strip()
    if not text:
        return 0
    depth_angle = 0
    depth_round = 0
    depth_square = 0
    count = 1
    for char in text:
        if char == "<":
            depth_angle += 1
        elif char == ">":
            depth_angle = max(0, depth_angle - 1)
        elif char == "(":
            depth_round += 1
        elif char == ")":
            depth_round = max(0, depth_round - 1)
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square = max(0, depth_square - 1)
        elif (
            char == "," and depth_angle == 0 and depth_round == 0 and depth_square == 0
        ):
            count += 1
    return count


def _parse_param_count_from_method_full_name(method_full_name: str | None) -> int:
    normalized = str(method_full_name or "").strip()
    if not normalized or "(" not in normalized or ")" not in normalized:
        return -1
    if ":" in normalized:
        normalized = normalized.split(":", 1)[1]
    match = re.search(r"\((.*)\)", normalized)
    if not match:
        return -1
    return _count_params_text(match.group(1))


def _find_method_declarations(
    *, lines: list[str], method_name: str
) -> list[dict[str, int]]:
    normalized_method = str(method_name or "").strip()
    if not lines or not normalized_method:
        return []
    out: list[dict[str, int]] = []
    pattern = re.compile(rf"\b{re.escape(normalized_method)}\s*\(")
    for index, line in enumerate(lines, start=1):
        if _is_ignorable_source_line(line):
            continue
        if not pattern.search(line):
            continue
        window = _signature_window(lines, index)
        if not _likely_method_decl_line(window, normalized_method):
            continue
        params = _extract_param_text_from_signature(window, normalized_method)
        out.append({"line": index, "param_count": _count_params_text(params)})
    return out


def _select_method_decl_line(
    *, lines: list[str], method_name: str, method_full_name: str | None
) -> int | None:
    declarations = _find_method_declarations(lines=lines, method_name=method_name)
    if not declarations:
        return None
    target_count = _parse_param_count_from_method_full_name(method_full_name)
    if target_count >= 0:
        for declaration in declarations:
            if declaration.get("param_count") == target_count:
                return int(declaration["line"])
    return int(declarations[0]["line"])


def _brace_delta(line_text: str) -> int:
    if not line_text:
        return 0
    in_single = False
    in_double = False
    escape = False
    delta = 0
    index = 0
    while index < len(line_text):
        char = line_text[index]
        next_char = line_text[index + 1] if index + 1 < len(line_text) else ""
        if not in_single and not in_double and char == "/" and next_char == "/":
            break
        if not in_double and char == "'" and not escape:
            in_single = not in_single
        elif not in_single and char == '"' and not escape:
            in_double = not in_double
        elif not in_single and not in_double:
            if char == "{":
                delta += 1
            elif char == "}":
                delta -= 1
        escape = (char == "\\") and not escape
        if char != "\\":
            escape = False
        index += 1
    return delta


def _method_range_for_decl(lines: list[str], decl_line: int) -> tuple[int, int]:
    if not lines or decl_line <= 0:
        return (-1, -1)
    open_line = -1
    max_open_scan = min(len(lines), decl_line + 25)
    for index in range(decl_line, max_open_scan + 1):
        if "{" in lines[index - 1]:
            open_line = index
            break
    if open_line <= 0:
        return (decl_line, min(len(lines), decl_line + 40))
    depth = 0
    end_line = min(len(lines), open_line + 400)
    for index in range(open_line, min(len(lines), open_line + 5000) + 1):
        depth += _brace_delta(lines[index - 1])
        if depth <= 0 and index > open_line:
            end_line = index
            break
    return (decl_line, end_line)


def _method_context_range(
    *, lines: list[str], method_name: str, method_full_name: str | None
) -> tuple[int | None, int | None]:
    decl_line = _select_method_decl_line(
        lines=lines,
        method_name=method_name,
        method_full_name=method_full_name,
    )
    if decl_line is None:
        return (None, None)
    start, end = _method_range_for_decl(lines, decl_line)
    if start <= 0 or end <= 0:
        return (None, None)
    return (start, end)


def _extract_constructor_class_name(
    *, node_ref: str | None, file_path: str
) -> str | None:
    text = str(node_ref or "")
    match = re.search(r"([A-Za-z_$][\w$]*)\.<init>", text)
    if match:
        return match.group(1)
    stem = Path(file_path).stem
    return stem or None


def _extract_variable_name(*, node_ref: str | None) -> str | None:
    tokens = [
        token.strip() for token in str(node_ref or "").split("|") if token.strip()
    ]
    if len(tokens) >= 6 and tokens[4] in {
        "param",
        "local",
        "member",
        "field",
        "id",
        "decl",
    }:
        return tokens[5]
    return None


def _extract_variable_decl_kind(*, node_ref: str | None) -> str | None:
    tokens = [
        token.strip() for token in str(node_ref or "").split("|") if token.strip()
    ]
    if len(tokens) >= 6 and tokens[0] == "Var":
        decl_kind = tokens[4].lower()
        return decl_kind or None
    return None


def _extract_method_full_name(*, node_ref: str | None) -> str | None:
    tokens = [
        token.strip() for token in str(node_ref or "").split("|") if token.strip()
    ]
    for token in reversed(tokens):
        if ":" in token and "(" in token and ")" in token:
            return token
    return None
