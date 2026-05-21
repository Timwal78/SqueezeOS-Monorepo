import logging
import sys
import os

# Set working directory to this script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

logging.basicConfig(level=logging.INFO)
print("Testing SqueezeOS service initialization...")

try:
    from core.legacy import init_services
    init_services()
    print("Services initialized successfully!")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
