import subprocess
import sys
import time
import urllib.error
import urllib.request

process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError(f"uvicorn exited with code {process.returncode}")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/docs", timeout=2) as response:
                assert response.status == 200
                print(f"/docs: HTTP {response.status}")
            with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as response:
                print(f"/health: HTTP {response.status} {response.read().decode()}")
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)
    else:
        raise RuntimeError("uvicorn did not become ready")
finally:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
