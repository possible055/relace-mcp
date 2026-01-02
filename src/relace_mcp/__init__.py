from importlib.metadata import version

__version__ = version("relace-mcp")

from .server import build_server, main

__all__ = ["__version__", "build_server", "main"]
