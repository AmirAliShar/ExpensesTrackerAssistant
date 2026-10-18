"""
Test runner script for FinPilot AI automated test suite.
"""
import sys
import os
import pytest

# Ensure backend root is in python path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

if __name__ == "__main__":
    test_dir = os.path.join(backend_dir, "tests")
    print(f"Running FinPilot AI automated test suite in: {test_dir}\n")
    exit_code = pytest.main(["-v", test_dir])
    sys.exit(exit_code)
