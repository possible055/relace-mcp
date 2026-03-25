"""API routers for benchmark viewer.

Provides fine-grained REST API endpoints for experiment data access.
"""

from benchmark.web.api.cases import router as cases_router
from benchmark.web.api.experiments import router as experiments_router
from benchmark.web.api.metrics import router as metrics_router

__all__ = [
    "cases_router",
    "experiments_router",
    "metrics_router",
]
