# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import PySide6
from version import windows_version_info
qt_folder = Path(PySide6.__file__).resolve().parent

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app.ico', '.'), ('assets', 'assets'), (str(qt_folder / 'translations' / 'qtbase_zh_CN.qm'), 'translations')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyInstaller', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'pymupdf4llm', 'pymupdf.layout', 'numpy', 'scipy', 'cv2', 'onnxruntime'],
    noarchive=False,
    optimize=0,
)
# Python and Qt may ship different MSVC versions. Bundle Qt's newer runtime
# at the root as well, so Python cannot preload an older DLL with the same name.
runtime_names = {'vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll',
                 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll',
                 'concrt140.dll'}
# Qt uses Windows' unversioned ICU API. A Poppler installation on PATH may
# cause the packager to pick an incompatible ICU with suffixed symbols.
a.binaries = [entry for entry in a.binaries
              if entry[0].lower() not in runtime_names | {'icuuc.dll', 'icudt78.dll'}]
for runtime_name in sorted(runtime_names):
    source = qt_folder / runtime_name
    if source.exists():
        a.binaries.append((runtime_name, str(source), 'BINARY'))
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='水印工坊',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
    version=windows_version_info(),
)
