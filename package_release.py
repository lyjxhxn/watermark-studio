"""Assemble a portable release with source, documentation and license texts."""
from pathlib import Path
from importlib import metadata
import shutil
import sys
import subprocess
import urllib.request
import zipfile

root = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(root / 'make_demo_assets.py')], check=True)
release = root.parent / '水印工坊'
release.mkdir(exist_ok=True)
licenses = release / 'licenses'
licenses.mkdir(exist_ok=True)

for name in ['pymupdf', 'PySide6-Essentials', 'shiboken6', 'Pillow', 'PyInstaller']:
    distribution = metadata.distribution(name)
    folder = licenses / name
    folder.mkdir(exist_ok=True)
    (folder / 'METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
    for entry in distribution.files or []:
        if any(word in str(entry).upper() for word in ['LICENSE', 'COPYING']):
            source = distribution.locate_file(entry)
            if source.is_file():
                shutil.copy2(source, folder / source.name)

shutil.copy2(Path(sys.base_prefix) / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
for name, url in [
    ('AGPL-3.0.txt', 'https://www.gnu.org/licenses/agpl-3.0.txt'),
    ('GPL-3.0.txt', 'https://www.gnu.org/licenses/gpl-3.0.txt'),
    ('LGPL-3.0.txt', 'https://www.gnu.org/licenses/lgpl-3.0.txt'),
]:
    target = licenses / name
    if not target.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'WatermarkStudio/1.0'})
        with urllib.request.urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())

shutil.copy2(licenses / 'AGPL-3.0.txt', root / 'LICENSE')
for name in ['LICENSE', 'README.md', '使用说明.md', 'THIRD_PARTY_NOTICES.md']:
    shutil.copy2(root / name, release / name)

source_folder = release / '源码'
source_folder.mkdir(exist_ok=True)
for name in ['main.py', 'engine.py', 'single_instance.py', 'requirements.txt', 'build.ps1', 'make_icon.py',
             'package_release.py', 'make_demo_assets.py', '水印工坊.spec', '.gitignore', '.gitattributes',
             'app.ico', 'app.png', 'LICENSE', 'README.md', '使用说明.md', 'THIRD_PARTY_NOTICES.md']:
    shutil.copy2(root / name, source_folder / name)
(source_folder / 'tests').mkdir(exist_ok=True)
shutil.copytree(root / 'assets', source_folder / 'assets', dirs_exist_ok=True)
shutil.copytree(root / 'docs', source_folder / 'docs', dirs_exist_ok=True)
shutil.copytree(root / 'docs', release / 'docs', dirs_exist_ok=True)
shutil.copy2(root / 'tests/test_app.py', source_folder / 'tests/test_app.py')
obsolete_local_check = source_folder / 'tests/check_real_pdf.py'
if obsolete_local_check.exists():
    obsolete_local_check.unlink()
shutil.copy2(root / 'tests/test_single_instance.py', source_folder / 'tests/test_single_instance.py')
for filename, destination in [
    ('desktop.png', '界面预览.png'),
    ('export-settings.png', '分辨率与压缩滑块.png'),
    ('color-dialog.png', '颜色弹窗预览.png'),
    ('context-menu.png', '中文右键菜单预览.png'),
    ('controls.png', '按钮样式预览.png'),
    ('color-swatches.png', '颜色图标预览.png'),
]:
    shutil.copy2(root / 'docs/images' / filename, release / destination)
shutil.copy2(root / 'dist/水印工坊.exe', release / '水印工坊.exe')

archive = root.parent / '水印工坊_Windows版.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
    for file in sorted(release.rglob('*')):
        if file.is_file():
            zipped.write(file, file.relative_to(release.parent))
print(f'Release: {release}')
print(f'Executable: {(release / "水印工坊.exe").stat().st_size:,} bytes')
print(f'Archive: {archive} ({archive.stat().st_size:,} bytes)')
