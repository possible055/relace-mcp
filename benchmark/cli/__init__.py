import click

from .analyze import main as _cmd_analyze
from .build_locbench import main as _cmd_build_locbench
from .case_map import main as _cmd_case_map
from .curate import main as _cmd_curate
from .grid import main as _cmd_grid
from .report import main as _cmd_report
from .run import main as _cmd_run
from .trace import main as _cmd_trace
from .validate import main as _cmd_validate
from .web import main as _cmd_web


@click.group()
def bench():
    """Benchmark CLI for relace-mcp search evaluation."""


# -- data sub-group: dataset preparation --


@bench.group()
def data():
    """Dataset build, curation, and validation."""


data.add_command(_cmd_build_locbench, "build-locbench")
data.add_command(_cmd_curate, "curate")
data.add_command(_cmd_validate, "validate")

# -- top-level: execution --

bench.add_command(_cmd_run, "run")
bench.add_command(_cmd_grid, "grid")

# -- results sub-group: analysis --


@bench.group()
def results():
    """Result analysis, reporting, and tracing."""


results.add_command(_cmd_analyze, "analyze")
results.add_command(_cmd_report, "report")
results.add_command(_cmd_trace, "trace")
results.add_command(_cmd_case_map, "case-map")

# -- top-level: viewer --

bench.add_command(_cmd_web, "web")
