"""Single source of product version; application identity stays unchanged."""
APP_VERSION = '1.1.0'
VERSION_TUPLE = tuple(int(part) for part in APP_VERSION.split('.')) + (0,)


def windows_version_info():
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct,
    )
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE,
                          mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable('080404B0', [
            StringStruct('FileDescription', '水印工坊 · PDF 与图片水印'),
            StringStruct('FileVersion', APP_VERSION),
            StringStruct('ProductName', '水印工坊'),
            StringStruct('ProductVersion', APP_VERSION),
            StringStruct('OriginalFilename', '水印工坊.exe'),
        ])]), VarFileInfo([VarStruct('Translation', [2052, 1200])])],
    )
