# Generate requirements-lock.txt from requirements.txt (pip-tools).
# Install: pip install 'pip-tools>=7.3'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python -m pip install -q "pip-tools>=7.3"
pip-compile requirements.txt -o requirements-lock.txt --resolver=backtracking
Write-Host "Wrote requirements-lock.txt"
