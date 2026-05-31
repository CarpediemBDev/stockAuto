import os
import sys
import traceback
import importlib

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set dummy environment variables to prevent crashes due to missing env vars during imports
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("KIS_APP_KEY", "dummy_key")
os.environ.setdefault("KIS_APP_SECRET", "dummy_secret")
os.environ.setdefault("KIS_ACCOUNT_NO", "dummy_acc")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "dummy_token")
os.environ.setdefault("GEMINI_API_KEY", "dummy_gemini")

def check_imports():
    app_dir = os.path.join(backend_dir, "app")
    errors = 0
    successes = 0
    
    print("=== Start Import Checking of backend/app ===")
    for root, dirs, files in os.walk(app_dir):
        if "__pycache__" in root:
            continue
            
        for file in files:
            if not file.endswith(".py"):
                continue
                
            # Convert file path to module name
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, backend_dir)
            module_name = rel_path.replace(os.sep, ".").replace(".py", "")
            
            try:
                # Try importing
                importlib.import_module(module_name)
                print(f"[SUCCESS] {module_name}")
                successes += 1
            except Exception as e:
                print(f"[FAILURE] {module_name}")
                print(f"Error: {e}")
                traceback.print_exc(file=sys.stdout)
                print("-" * 50)
                errors += 1
                
    print("\n=== Import Check Summary ===")
    print(f"Total Successes: {successes}")
    print(f"Total Failures: {errors}")
    if errors > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    check_imports()
