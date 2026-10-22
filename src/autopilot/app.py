from fastapi import FastAPI

from autopilot.contracts import HealthResponse


def create_app() -> FastAPI:
    app = FastAPI(title="AI Agency Autopilot")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
