<#
.SYNOPSIS
    Запуск «Протокола» одной командой: окружение, свободные порты, два сервера.

.DESCRIPTION
    Скрипт проверяет Python и Node.js, при первом запуске создаёт backend\.venv
    и ставит зависимости, подбирает свободные порты, прописывает адрес API
    в frontend\.env.local, поднимает FastAPI и Vite в отдельных окнах и ждёт,
    пока API начнёт отвечать. Только после этого открывается браузер.

.PARAMETER BackendPort
    Стартовый порт API. По умолчанию 8000; если занят — берётся следующий свободный.

.PARAMETER FrontendPort
    Стартовый порт интерфейса. По умолчанию 5173; если занят — следующий свободный.

.PARAMETER NoBrowser
    Не открывать браузер (удобно при проверке из скриптов).

.PARAMETER Reinstall
    Переставить зависимости бэкенда, даже если они уже установлены.

.EXAMPLE
    .\запустить.ps1

.EXAMPLE
    .\запустить.ps1 -BackendPort 8010 -FrontendPort 5180 -NoBrowser

.NOTES
    Если PowerShell не разрешает запуск скриптов (по умолчанию в Windows это
    Restricted), запускайте через cmd: запустить.cmd — он сам вызывает
    PowerShell с -ExecutionPolicy Bypass.
#>

[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoBrowser,
    [switch]$Reinstall
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# ---------------------------------------------------------------- вспомогательное

function Write-Info { param([string]$Text) Write-Host "  $Text" -ForegroundColor Gray }
function Write-Ok { param([string]$Text) Write-Host "  [ok] $Text" -ForegroundColor Green }
function Write-Warn { param([string]$Text) Write-Host "  [!]  $Text" -ForegroundColor Yellow }

function Stop-Launcher {
    param([string]$Message)
    Write-Host ''
    Write-Host "  Ошибка: $Message" -ForegroundColor Red
    Write-Host ''
    exit 1
}

# UTF-8 без BOM: с BOM Vite не увидит VITE_API_URL в первой строке.
function Set-TextFileUtf8NoBom {
    param([string]$Path, [string]$Text)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

# Порт свободен, если на него удаётся встать эксклюзивно. Get-NetTCPConnection
# без прав администратора падает с «отказано в доступе», поэтому проверяем
# сокетом: так работает и в обычном пользовательском PowerShell.
function Test-PortFree {
    param([int]$Port)
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener -ArgumentList ([System.Net.IPAddress]::Loopback), $Port
        $listener.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($listener) {
            try { $listener.Stop() } catch { }
        }
    }
}

function Find-FreePort {
    param([int]$Start, [int]$Span = 25)
    for ($port = $Start; $port -le ($Start + $Span); $port++) {
        if (Test-PortFree -Port $port) { return $port }
    }
    Stop-Launcher ("не нашёл свободный порт в диапазоне {0}..{1}. Укажите другой: .\запустить.ps1 -BackendPort 9000 -FrontendPort 5900" -f $Start, ($Start + $Span))
}

# Проверка «сервер уже отвечает 2xx» через голый сокет: так проверка не зависит
# от загруженных .NET-сборок (в Windows PowerShell 5.1 System.Net.Http не
# подгружен) и не уходит в системный прокси, в отличие от Invoke-WebRequest.
function Test-HttpOk {
    param(
        [string]$Address,
        [int]$Port,
        [string]$Path = '/'
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.BeginConnect($Address, $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(1500)) { return $false }
        $client.EndConnect($connect)

        $stream = $client.GetStream()
        $stream.ReadTimeout = 3000
        $stream.WriteTimeout = 3000

        $crlf = [string][char]13 + [string][char]10
        $request = "GET $Path HTTP/1.1" + $crlf +
        "Host: ${Address}:${Port}" + $crlf +
        "User-Agent: kt6-launcher" + $crlf +
        "Connection: close" + $crlf + $crlf

        $payload = [System.Text.Encoding]::ASCII.GetBytes($request)
        $stream.Write($payload, 0, $payload.Length)
        $stream.Flush()

        $reader = New-Object System.IO.StreamReader -ArgumentList $stream, ([System.Text.Encoding]::ASCII)
        $statusLine = $reader.ReadLine()
        return ($statusLine -match '^HTTP/\d\.\d\s+2\d\d')
    }
    catch {
        # Сервер ещё не слушает порт — это нормально на старте.
        return $false
    }
    finally {
        $client.Close()
    }
}

function Wait-HttpReady {
    param(
        [string]$Address,
        [int]$Port,
        [string]$Path = '/',
        [int]$TimeoutSec = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $tick = 0
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpOk -Address $Address -Port $Port -Path $Path) { return $true }
        $tick++
        if ($tick % 4 -eq 0) { Write-Host '.' -NoNewline -ForegroundColor DarkGray }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Find-PythonExe {
    $candidates = New-Object System.Collections.Generic.List[string]

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) {
                $candidates.Add(("$exe".Split("`n")[0]).Trim())
            }
        }
        catch { }
    }

    foreach ($name in @('python', 'python3')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) { $candidates.Add($cmd.Source) }
    }

    foreach ($candidate in $candidates) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate)) { continue }
        try {
            $version = & $candidate -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $version) { continue }
            $parts = "$version".Trim().Split('.')
            if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 9) { return $candidate }
        }
        catch { }
    }
    return $null
}

# ---------------------------------------------------------------- пути

$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$venvDir = Join-Path $backendDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$requirements = Join-Path $backendDir 'requirements.txt'

Write-Host ''
Write-Host '=== Протокол: подготовка окружения ===' -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $backendDir)) { Stop-Launcher "не нашёл папку backend рядом со скриптом ($root)" }
if (-not (Test-Path -LiteralPath $frontendDir)) { Stop-Launcher "не нашёл папку frontend рядом со скриптом ($root)" }

# ---------------------------------------------------------------- python

$python = Find-PythonExe
if (-not $python) {
    Stop-Launcher 'не нашёл Python 3.9+. Установите Python с python.org и включите «Add python.exe to PATH».'
}
$pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
Write-Ok "Python: $python ($pythonVersion)"

# ---------------------------------------------------------------- venv + pip

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Info 'Создаю виртуальное окружение backend\.venv…'
    & $python -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        Stop-Launcher "не удалось создать виртуальное окружение ($python -m venv `"$venvDir`")"
    }
}

# Метка с хешем requirements.txt: зависимости переставляются только когда
# список изменился, а не при каждом запуске.
$stampFile = Join-Path $venvDir '.requirements.sha256'
$requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
$needInstall = $Reinstall.IsPresent
if (-not $needInstall) {
    if (Test-Path -LiteralPath $stampFile) {
        $needInstall = ((Get-Content -LiteralPath $stampFile -Raw).Trim() -ne $requirementsHash)
    }
    else {
        $needInstall = $true
    }
}

if ($needInstall) {
    Write-Info 'Ставлю зависимости бэкенда (первый раз это около минуты)…'
    & $venvPython -m pip install --disable-pip-version-check --quiet --upgrade pip
    & $venvPython -m pip install --disable-pip-version-check --quiet -r $requirements
    if ($LASTEXITCODE -ne 0) {
        Stop-Launcher "pip install завершился с кодом $LASTEXITCODE. Проверьте интернет и повторите: .\запустить.ps1 -Reinstall"
    }
    Set-Content -LiteralPath $stampFile -Value $requirementsHash -Encoding ASCII
}
Write-Ok 'Зависимости бэкенда на месте'

# ---------------------------------------------------------------- node + npm

$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $node) { Stop-Launcher 'не нашёл Node.js. Установите LTS с nodejs.org и перезапустите терминал.' }
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { Stop-Launcher 'не нашёл npm.cmd рядом с node. Переустановите Node.js (в комплекте идёт npm).' }
Write-Ok "Node.js: $(& node --version) / npm: $(& npm.cmd --version)"

if (-not (Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules'))) {
    Write-Info 'Ставлю зависимости фронтенда (первый раз это занимает пару минут)…'
    Push-Location $frontendDir
    try {
        cmd /c 'npm install --no-audit --no-fund'
        if ($LASTEXITCODE -ne 0) {
            Stop-Launcher "npm install завершился с кодом $LASTEXITCODE. Удалите frontend\node_modules и повторите запуск."
        }
    }
    finally {
        Pop-Location
    }
}
Write-Ok 'Зависимости фронтенда на месте'

# ---------------------------------------------------------------- порты и адреса

$apiPort = Find-FreePort -Start $BackendPort
$uiPort = Find-FreePort -Start $FrontendPort
while ($uiPort -eq $apiPort) {
    $uiPort = Find-FreePort -Start ($uiPort + 1) -Span 5
}

if ($apiPort -ne $BackendPort) { Write-Warn "порт $BackendPort занят — API будет на $apiPort" }
if ($uiPort -ne $FrontendPort) { Write-Warn "порт $FrontendPort занят — интерфейс будет на $uiPort" }

$origin = "http://127.0.0.1:$uiPort"
$apiBase = "http://127.0.0.1:$apiPort/api"

# Адрес API для Vite и разрешённый origin для CORS на бэкенде. CORS читается
# из окружения дочернего процесса, поэтому .env трогать не нужно.
Set-TextFileUtf8NoBom -Path (Join-Path $frontendDir '.env.local') -Text "# Создано запустить.ps1: адрес API текущего запуска.`nVITE_API_URL=$apiBase`n"
$env:CORS_ORIGINS = "$origin,http://localhost:$uiPort"

Write-Host ''
Write-Host "  Бэкенд   : http://127.0.0.1:$apiPort  (Swagger: /docs)" -ForegroundColor Green
Write-Host "  Фронтенд : $origin" -ForegroundColor Green
Write-Host '  Демо     : demo / demo12345, student / student123' -ForegroundColor DarkGray
Write-Host ''

# ---------------------------------------------------------------- два сервера

# cmd /s /k: /s делает разбор кавычек предсказуемым (путь с пробелами — не проблема),
# /k оставляет окно открытым, чтобы traceback при падении не исчез.
$backendCommand = "`"$venvPython`" -m uvicorn main:app --host 127.0.0.1 --port $apiPort"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/s', '/k', "`"$backendCommand`"" -WorkingDirectory $backendDir

$frontendCommand = "npm run dev -- --host 127.0.0.1 --port $uiPort --strictPort"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/s', '/k', "`"$frontendCommand`"" -WorkingDirectory $frontendDir

# ---------------------------------------------------------------- ожидание готовности

Write-Info 'Жду ответа API…'
if (-not (Wait-HttpReady -Address '127.0.0.1' -Port $apiPort -Path '/api/system/health' -TimeoutSec 120)) {
    Write-Host ''
    Write-Host '  API не ответил за 120 секунд.' -ForegroundColor Red
    Write-Host '  Причина видна в окне с заголовком uvicorn — оно осталось открытым.' -ForegroundColor Yellow
    Write-Host '  Частая причина: занятый или недоступный порт, упавшая зависимость.' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}
Write-Host ''
Write-Ok 'API отвечает'

Write-Info 'Жду ответа Vite…'
if (-not (Wait-HttpReady -Address '127.0.0.1' -Port $uiPort -Path '/' -TimeoutSec 90)) {
    Write-Host ''
    Write-Host '  Vite не ответил за 90 секунд — смотрите его окно.' -ForegroundColor Red
    Write-Host ''
    exit 1
}
Write-Host ''
Write-Ok 'Vite отвечает'

# ---------------------------------------------------------------- браузер

if (-not $NoBrowser) {
    try {
        Start-Process $origin
    }
    catch {
        Write-Warn "не смог открыть браузер сам — откройте вручную: $origin"
    }
}

Write-Host ''
Write-Host '=== Готово ===' -ForegroundColor Cyan
Write-Host "  Интерфейс : $origin"
Write-Host "  API       : http://127.0.0.1:$apiPort/api  (документация: /docs)"
Write-Host '  Демо-вход : demo / demo12345   или   student / student123'
Write-Host '  Остановка : закройте два окна серверов (Ctrl+C или крестик).'
Write-Host ''
