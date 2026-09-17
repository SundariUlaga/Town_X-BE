"""Modular admin API routes — all require role=admin."""

from fastapi import APIRouter

from app.api.admin.auth import router as auth_router
from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.advertisements import router as advertisements_router
from app.api.admin.properties import router as properties_router
from app.api.admin.users import router as users_router
from app.api.admin.reports import router as admin_reports_router
from app.api.admin.audit_logs import router as audit_logs_router
from app.api.admin.notifications import router as notifications_router

router = APIRouter(prefix="/api/admin", tags=["Admin"])

router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(advertisements_router)
router.include_router(properties_router)
router.include_router(users_router)
router.include_router(admin_reports_router)
router.include_router(audit_logs_router)
router.include_router(notifications_router)
