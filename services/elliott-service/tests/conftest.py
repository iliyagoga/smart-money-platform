"""Load the shared replay package as it is installed in the live Docker image."""
import importlib.util
from pathlib import Path
import sys

source = Path(__file__).resolve().parents[2] / "backtest-service" / "src"
spec = importlib.util.spec_from_file_location("backtest_core", source / "__init__.py")
module = importlib.util.module_from_spec(spec)
sys.modules["backtest_core"] = module
spec.loader.exec_module(module)
