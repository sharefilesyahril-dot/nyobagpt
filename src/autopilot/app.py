from fastapi import FastAPI

from autopilot.contracts import HealthResponse
from autopilot.identity.routes import router as identity_router
from autopilot.ventures.routes import router as ventures_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Agency Autopilot")
    app.include_router(identity_router)
    app.include_router(ventures_router)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
