"""Build on Windows x64 with CPython 3.14.7; never includes local settings."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "3.14.7"

def main():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 14):
        raise SystemExit("Build requires Windows x64 and Python 3.14")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    package = out / "e10-print-server-portable-windows-x64"
    if package.exists():
        raise SystemExit("Output exists; use a fresh build directory")
    runtime = package / "python"
    runtime.mkdir(parents=True)
    archive = out / "python-embedded.zip"
    url = f"https://www.python.org/ftp/python/{VERSION}/python-{VERSION}-embed-amd64.zip"
    urllib.request.urlretrieve(url, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as z:
        z.extractall(runtime)
    (runtime / "python314._pth").write_text(
        "python314.zip\n.\nLib/site-packages\n..\nimport site\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "pip", "install", "--only-binary=:all:",
                    "--target", str(runtime / "Lib" / "site-packages"),
                    "-r", str(ROOT / "requirements.txt")], check=True)
    for name in ("e10_server.py", "windows.ps1", "start.cmd", "restart.cmd", "stop.cmd",
                 ".env.example", "LICENSE", "SECURITY.md"):
        shutil.copy2(ROOT / name, package / name)
    shutil.copy2(ROOT / ".env.example", package / ".env")
    shutil.copytree(ROOT / "reference", package / "reference")
    manager = package / "windows.ps1"
    text = manager.read_text(encoding="utf-8")
    text = text.replace("$Python = Join-Path $Root '.venv\\Scripts\\python.exe'",
                        "$Python = Join-Path $Root 'python\\python.exe'")
    text = text.replace("Run install.cmd first.", "Portable runtime missing. Extract the complete ZIP again.")
    manager.write_text(text, encoding="utf-8")
    (package / "BITTE-LESEN.txt").write_text(
        "E10 PORTABLE - Windows 11 x64 (Intel/AMD)\n\n"
        "1. Gesamtes ZIP in einen beschreibbaren Ordner entpacken.\n"
        "2. start.cmd doppelklicken. Keine Installation erforderlich.\n"
        "3. Browser: http://127.0.0.1:1312\n"
        "4. Bluetooth einschalten, E10 suchen und verbinden.\n\n"
        "restart.cmd: Neustart. stop.cmd: Beenden. Nur zwischen Druckauftraegen!\n"
        "Einstellungen: .env. Logs: .runtime\\stderr.log\n"
        "Kein Autostart, keine Adminrechte, keine Downloads beim Start.\n"
        "Endlosband verwenden. Handy-Verbindung zum Drucker vorher trennen.\n"
        "Keine Anmeldung: nicht ins Internet freigeben.\n"
        "Bluetooth-Hardwaredruck muss am eigenen E10 getestet werden.\n"
        "Bei Sicherheitsblockierung nicht pauschal den Virenschutz deaktivieren.\n",
        encoding="utf-8")
    python = runtime / "python.exe"
    subprocess.run([str(python), "-c",
        "import ssl,lzma,bleak,uvicorn,PIL,fastapi; "
        "import winrt.windows.devices.bluetooth; "
        "from e10_server import Settings,render,PrintSpec; "
        "assert Settings.read().port==1312; assert render(PrintSpec(text='Test')).height==96"],
        cwd=package, check=True)
    # Smoke-test actual embedded runtime without touching Bluetooth.
    import time
    process = subprocess.Popen([str(python), str(package / "e10_server.py")], cwd=package,
                               env={**os.environ, "SERVER_IP":"127.0.0.1", "SERVER_PORT":"19312"})
    try:
        for attempt in range(60):
            if process.poll() is not None:
                raise RuntimeError("Embedded server exited")
            try:
                with urllib.request.urlopen("http://127.0.0.1:19312/api/status", timeout=1) as r:
                    assert json.load(r)["busy"] is False
                break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError("Embedded server startup timed out")
    finally:
        process.terminate()
        process.wait(timeout=15)
    (package / "BUILD-INFO.json").write_text(json.dumps({
        "python":VERSION, "source":url, "python_archive_sha256":digest,
        "commit":os.environ.get("GITHUB_SHA", "local"),
        "tests":"Embedded runtime imports, text raster and HTTP status; no Bluetooth hardware test"
    }, indent=2), encoding="utf-8")
    # Includes wheel metadata/licenses and official Python license.
    result = shutil.make_archive(str(out / package.name), "zip", out, package.name)
    Path(result + ".sha256").write_text(hashlib.sha256(Path(result).read_bytes()).hexdigest()
                                       + "  " + Path(result).name + "\n", encoding="ascii")
    print(result)

if __name__ == "__main__":
    main()
