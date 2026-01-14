import sys
from pathlib import Path

# Add project root to Python path for benchmark module imports
# This is the canonical way to handle non-installed packages in pytest
_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))
