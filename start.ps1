param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath 'backend\.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Instale as dependências do backend seguindo o README.md.' }
if (!(Test-Path -LiteralPath (Join-Path $projectPath 'frontend\dist\index.html'))) { throw 'Execute pnpm build na pasta frontend antes de iniciar.' }
Push-Location (Join-Path $projectPath 'backend')
try { & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port }
finally { Pop-Location }
