import sys
from pathlib import Path

# Add the project root (one level up from this file) to Python's module
# search path so test files can import app.py and github_client.py directly.
sys.path.insert(0, str(Path(__file__).parent.parent))