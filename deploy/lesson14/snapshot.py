"""Create a local source-only release commit without staging the shared workspace."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
target = Path(tempfile.mkdtemp(prefix="novaops-l14-release-"))
names = ["model_client.py", "bedrock_client.py", "retrieval_mcp_server.py",
         "company_brain", "maya", "webex", "vendor", "renewal", "service",
         "novaops-enterprise-agent-dataset", "deploy/lesson14", "tests", ".dockerignore"]
ignored = shutil.ignore_patterns("__pycache__", "*.pyc", ".runtime", "evidence", ".env*", "*.env", ".state")
for name in names:
    source, destination = root / name, target / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, ignore=ignored)
    else:
        shutil.copy2(source, destination)
def git(*args):
    return subprocess.check_output(["git", *args], cwd=target, text=True, stderr=subprocess.DEVNULL).strip()
git("init")
git("add", ".")
git("-c", "user.name=NovaOps Local Release", "-c", "user.email=local-release@example.invalid",
    "commit", "-m", "Lesson 14 local verification source snapshot")
release = git("rev-parse", "HEAD")
runtime = root / "deploy/lesson14/.runtime"
runtime.mkdir(exist_ok=True)
(runtime / "release.env").write_text("IMAGE_TAG=" + release + "\n")
(runtime / "release.json").write_text(json.dumps({"commit": release, "source": str(target), "published": False}, indent=2) + "\n")
print(json.dumps({"commit": release, "source": str(target), "published": False}))
