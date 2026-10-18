"""Build an extension ZIP from an explicit source whitelist."""
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mmd_unity_exporter"
manifest = tomllib.loads((SOURCE / "blender_manifest.toml").read_text(encoding="utf-8"))
output = ROOT / "dist" / (manifest["id"] + "-" + manifest["version"] + ".zip")
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for name in ("blender_manifest.toml", "__init__.py", "materials.py", "exporter.py"):
        archive.write(SOURCE / name, name)
    for name in ("LICENSE", "README.md"):
        archive.write(ROOT / name, name)
print(output)
