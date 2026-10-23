from fastapi import FastAPI

from autopilot.audit.routes import router as audit_router
from autopilot.contracts import HealthResponse
from autopilot.governance.routes import router as governance_router
from autopilot.identity.routes import router as identity_router
from autopilot.ventures.routes import router as ventures_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Agency Autopilot")
    app.include_router(audit_router)
    app.include_router(identity_router)
    app.include_router(governance_router)
    app.include_router(ventures_router)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
