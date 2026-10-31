"""
Main Application Entrypoint.
Configures FastAPI, CORS, API routes, database lifecycle, and exception handlers.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api.v1.newsletter import router as newsletter_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler for database initialization and cleanup."""
    init_db()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Independent secure reference implementation for the Cynbit backend newsletter audit.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom validation exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format Pydantic validation errors into clean, standardized JSON."""
    error_details = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        error_details.append(f"{field}: {error.get('msg')}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "; ".join(error_details)
        }
    )


# Health check endpoint
@app.get("/health", tags=["Health"])
def health_check():
    """Service health and liveness probe."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION
    }


# Include Newsletter Router
app.include_router(newsletter_router, prefix=settings.API_V1_STR)
