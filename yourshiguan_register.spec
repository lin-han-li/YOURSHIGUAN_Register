# -*- mode: python ; coding: utf-8 -*-

import json
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_dir = Path(globals().get("SPECPATH", ".")).resolve()
package_json = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
release_config = package_json.get("desktopRelease", {})
datas, binaries, hiddenimports = collect_all("curl_cffi")

entry_script = project_dir / release_config.get("entry", "yourshiguan_register.py")
binary_name = release_config.get("binaryName", "YOURSHIGUAN_Register")
windows_executable = release_config.get("windowsExecutableName", f"{binary_name}.exe")
executable_name = os.environ.get("PYI_EXECUTABLE_NAME") or (
    Path(windows_executable).stem if sys.platform == "win32" else binary_name
)
windows_icon = release_config.get("iconWindows", "")
icon_path = project_dir / windows_icon if windows_icon else None
version_file = os.environ.get("PYI_VERSION_FILE")

a = Analysis(
    [str(entry_script)],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe_kwargs = {
    "name": executable_name,
    "debug": False,
    "bootloader_ignore_signals": False,
    "strip": False,
    "upx": False,
    "upx_exclude": [],
    "runtime_tmpdir": None,
    "console": True,
    "disable_windowed_traceback": False,
    "argv_emulation": False,
    "target_arch": None,
    "codesign_identity": None,
    "entitlements_file": None,
}

if sys.platform == "win32" and icon_path and icon_path.exists():
    exe_kwargs["icon"] = str(icon_path)

if sys.platform == "win32" and version_file:
    exe_kwargs["version"] = version_file

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    **exe_kwargs,
)
