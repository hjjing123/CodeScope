from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.api.v1.findings import _dedupe_finding_payloads, _finding_payload
from app.schemas.finding import FindingPayload
from app.config import get_settings
from app.services.finding_presentation_service import build_finding_presentation


def test_build_finding_presentation_prefers_route_entry(tmp_path: Path) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = (
        tmp_path / str(version_id) / "source" / "src" / "main" / "java" / "com" / "demo"
    )
    source_root.mkdir(parents=True, exist_ok=True)
    controller_path = source_root / "UserController.java"
    controller_path.write_text(
        "package com.demo;\n\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "import org.springframework.web.bind.annotation.RequestParam;\n\n"
        "public class UserController {\n"
        '  @RequestMapping(value = "admin/user/{index}/{count}", method = RequestMethod.GET)\n'
        "  public String getUserBySearch(\n"
        "      @RequestParam(required = false) String orderBy,\n"
        "      @RequestParam(required = false) Boolean isDesc) {\n"
        '    return "ok";\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        presentation = build_finding_presentation(
            version_id=version_id,
            rule_key="any_mybatis_sqli",
            vuln_type="SQLI",
            source_file="src/main/java/com/demo/UserController.java",
            source_line=9,
            file_path="src/main/java/com/demo/dao/UserMapper.java",
            line_start=16,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert presentation["vuln_display_name"] == "SQL Injection"
    assert presentation["entry_display"] == "GET /admin/user/{index}/{count}"
    assert presentation["entry_kind"] == "route"


def test_finding_payload_exposes_vuln_and_entry_display(tmp_path: Path) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = (
        tmp_path / str(version_id) / "source" / "src" / "main" / "java" / "com" / "demo"
    )
    source_root.mkdir(parents=True, exist_ok=True)
    controller_path = source_root / "UploadController.java"
    controller_path.write_text(
        "package com.demo;\n\n"
        "import org.springframework.web.bind.annotation.PostMapping;\n"
        "import org.springframework.web.bind.annotation.RequestParam;\n\n"
        "public class UploadController {\n"
        '  @PostMapping("admin/upload")\n'
        "  public String upload(@RequestParam String fileName) {\n"
        "    return fileName;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        payload = _finding_payload(
            SimpleNamespace(
                id=uuid.uuid4(),
                project_id=uuid.uuid4(),
                version_id=version_id,
                job_id=uuid.uuid4(),
                rule_key="any_any_upload",
                rule_version=1,
                vuln_type="UPLOAD",
                severity="MED",
                status="OPEN",
                file_path="src/main/java/com/demo/UploadController.java",
                line_start=7,
                has_path=True,
                path_length=1,
                source_file="src/main/java/com/demo/UploadController.java",
                source_line=7,
                sink_file="src/main/java/com/demo/UploadController.java",
                sink_line=7,
                evidence_json={},
                created_at=datetime.now(UTC),
            )
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert payload.vuln_display_name == "Arbitrary File Upload"
    assert payload.entry_display == "POST /admin/upload"
    assert payload.entry_kind == "route"


def test_build_finding_presentation_falls_back_to_file_location() -> None:
    presentation = build_finding_presentation(
        version_id=uuid.uuid4(),
        rule_key="config_secret_hardcode",
        vuln_type="CUSTOM",
        source_file=None,
        source_line=None,
        file_path="src/main/resources/application.properties",
        line_start=8,
    )

    assert presentation["vuln_display_name"] == "Hardcoded Secret"
    assert (
        presentation["entry_display"] == "src/main/resources/application.properties:8"
    )
    assert presentation["entry_kind"] == "file"


def test_build_finding_presentation_uses_nearest_annotation_block(
    tmp_path: Path,
) -> None:
    settings = get_settings()
    old_snapshot_root = settings.snapshot_storage_root
    version_id = uuid.uuid4()
    source_root = (
        tmp_path / str(version_id) / "source" / "src" / "main" / "java" / "com" / "demo"
    )
    source_root.mkdir(parents=True, exist_ok=True)
    controller_path = source_root / "RewardController.java"
    controller_path.write_text(
        "package com.demo;\n\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "import org.springframework.web.bind.annotation.RequestParam;\n"
        "import org.springframework.web.bind.annotation.ResponseBody;\n\n"
        "public class RewardController {\n"
        '  @RequestMapping(value = "admin/reward/new", method = RequestMethod.GET)\n'
        "  public String goToAddPage() {\n"
        '    return "ok";\n'
        "  }\n\n"
        "  @ResponseBody\n"
        '  @RequestMapping(value = "admin/reward/{index}/{count}", method = RequestMethod.GET)\n'
        "  public String getRewardBySearch(\n"
        "      @RequestParam(required = false) String orderBy,\n"
        "      @RequestParam(required = false) Boolean isDesc) {\n"
        '    return "ok";\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    settings.snapshot_storage_root = str(tmp_path)
    try:
        presentation = build_finding_presentation(
            version_id=version_id,
            rule_key="any_mybatis_sqli",
            vuln_type="SQLI",
            source_file="src/main/java/com/demo/RewardController.java",
            source_line=14,
            file_path="src/main/java/com/demo/dao/RewardMapper.java",
            line_start=17,
        )
    finally:
        settings.snapshot_storage_root = old_snapshot_root

    assert presentation["entry_display"] == "GET /admin/reward/{index}/{count}"


def test_dedupe_finding_payloads_collapses_same_route_duplicates() -> None:
    created_at = datetime.now(UTC)
    stronger = FindingPayload(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        rule_key="any_mybatis_sqli",
        rule_version=1,
        vuln_type="SQLI",
        vuln_display_name="SQL Injection",
        severity="MED",
        status="OPEN",
        file_path="src/dao/UserMapper.java",
        line_start=16,
        line_end=16,
        entry_display="GET /admin/user/{index}/{count}",
        entry_kind="route",
        has_path=True,
        path_length=3,
        source_file="src/controller/UserController.java",
        source_line=139,
        sink_file="src/dao/UserMapper.java",
        sink_line=16,
        evidence_json={"dedupe_score": 120},
        created_at=created_at,
    )
    weaker = FindingPayload(
        id=uuid.uuid4(),
        project_id=stronger.project_id,
        version_id=stronger.version_id,
        job_id=stronger.job_id,
        rule_key="any_mybatis_sqli",
        rule_version=1,
        vuln_type="SQLI",
        vuln_display_name="SQL Injection",
        severity="MED",
        status="OPEN",
        file_path="src/service/UserServiceImpl.java",
        line_start=36,
        line_end=36,
        entry_display="GET /admin/user/{index}/{count}",
        entry_kind="route",
        has_path=True,
        path_length=3,
        source_file="src/controller/UserController.java",
        source_line=139,
        sink_file="src/service/UserServiceImpl.java",
        sink_line=36,
        evidence_json={"dedupe_score": 118},
        created_at=created_at,
    )

    deduped = _dedupe_finding_payloads([weaker, stronger])

    assert len(deduped) == 1
    assert deduped[0].file_path == "src/dao/UserMapper.java"
