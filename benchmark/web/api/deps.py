from fastapi import Request

from benchmark.experiments.index import ExperimentIndex
from benchmark.experiments.store import ExperimentStore


def get_store(request: Request) -> ExperimentStore:
    return request.app.state.experiment_store


def get_index(request: Request) -> ExperimentIndex:
    return request.app.state.experiment_index
