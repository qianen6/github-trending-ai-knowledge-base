$ErrorActionPreference = 'Stop'
$python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
& $python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Failed to create .venv' }
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'Default PyPI failed; retrying with the Tsinghua PyPI mirror.'
    & $venvPython -m pip install -i 'https://pypi.tuna.tsinghua.edu.cn/simple' -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install requirements from both package indexes' }
}
& $venvPython (Join-Path $PSScriptRoot 'scripts\bootstrap.py') --root $PSScriptRoot --check
if ($LASTEXITCODE -ne 0) { throw 'Workspace verification failed' }
Write-Output 'SETUP PASS: activate with .\.venv\Scripts\Activate.ps1'
