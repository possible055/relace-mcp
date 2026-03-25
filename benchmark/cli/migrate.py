import json

import click

from ..experiments.migrate import migrate_all


@click.command()
def main() -> None:
    """Migrate legacy benchmark artifacts to the canonical layout."""
    summary = migrate_all()
    click.echo(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
