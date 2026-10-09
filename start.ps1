# Inicia o backend com o frontend já compilado; não instala nem recompila dependências.
# Uso na raiz: .\start.ps1 -Port 8000. O servidor permanece em primeiro plano.
param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$pythonPath = Join-Path $projectPath 'backend\.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Instale as dependências do backend seguindo o README.md.' }
if (!(Test-Path -LiteralPath (Join-Path $projectPath 'frontend\dist\index.html'))) { throw 'Execute pnpm build na pasta frontend antes de iniciar.' }
Push-Location (Join-Path $projectPath 'backend')
try { & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port }
finally { Pop-Location }
