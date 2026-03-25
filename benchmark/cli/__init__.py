import importlib

import click


class LazyGroup(click.Group):
    def __init__(self, *args, lazy_subcommands: dict[str, str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        commands = set(super().list_commands(ctx))
        commands.update(self.lazy_subcommands)
        return sorted(commands)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        target = self.lazy_subcommands.get(cmd_name)
        if not target:
            return None
        module_name, attr_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)


@click.group(
    cls=LazyGroup,
    lazy_subcommands={
        "run": "benchmark.cli.run:main",
        "grid": "benchmark.cli.grid:main",
        "migrate": "benchmark.cli.migrate:main",
        "web": "benchmark.cli.web:main",
    },
)
def bench():
    """Benchmark CLI for relace-mcp search evaluation."""


@click.group(
    cls=LazyGroup,
    lazy_subcommands={
        "build-locbench": "benchmark.cli.build_locbench:main",
        "curate": "benchmark.cli.curate:main",
        "validate": "benchmark.cli.validate:main",
    },
)
def data():
    """Dataset build, curation, and validation."""


@click.group(
    cls=LazyGroup,
    lazy_subcommands={
        "analyze": "benchmark.cli.analyze:main",
        "report": "benchmark.cli.report:main",
        "trace": "benchmark.cli.trace:main",
        "case-map": "benchmark.cli.case_map:main",
    },
)
def results():
    """Result analysis, reporting, and tracing."""


bench.add_command(data)
bench.add_command(results)
