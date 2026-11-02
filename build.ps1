$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements.txt --index-url https://pypi.org/simple
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
python make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
$watermarkSpec = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.spec' -File | Select-Object -First 1
if (-not $watermarkSpec) { throw 'Build spec was not found.' }
python -m PyInstaller --noconfirm --clean $watermarkSpec.FullName
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host 'Build completed. The executable is in the dist directory.'
