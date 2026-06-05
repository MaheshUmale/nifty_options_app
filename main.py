import sys
import os

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
