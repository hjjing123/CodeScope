from fastapi import APIRouter

from app.api.v1 import (
    ai,
    audit_logs,
    auth,
    findings,
    jobs,
    log_center,
    project_imports,
    project_member_resources,
    project_members,
    projects,
    runtime_logs,
    rules,
    users,
    versions,
)


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(ai.router)
api_router.include_router(audit_logs.router)
api_router.include_router(runtime_logs.router)
api_router.include_router(log_center.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(project_members.router)
api_router.include_router(project_member_resources.router)
api_router.include_router(versions.router)
api_router.include_router(project_imports.router)
api_router.include_router(jobs.router)
api_router.include_router(findings.router)
api_router.include_router(rules.router)
