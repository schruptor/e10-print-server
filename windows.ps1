param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('install','start','restart','stop')]
    [string]$Action
)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Server = Join-Path $Root 'e10_server.py'
$Runtime = Join-Path $Root '.runtime'
$StateFile = Join-Path $Runtime 'server.json'
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
Set-Location -LiteralPath $Root

function Get-Server {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $null }
    $state = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
    $proc = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if (-not $proc) {
        Remove-Item -LiteralPath $StateFile
        return $null
    }
    # PID reuse must never stop an unrelated process.
    if ($proc.StartTime.ToUniversalTime().Ticks.ToString() -ne $state.started) {
        Remove-Item -LiteralPath $StateFile
        return $null
    }
    $info = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)"
    if (-not $info -or -not $info.CommandLine -or
        -not $info.CommandLine.Contains('"' + $Server + '"')) {
        throw 'Process identity cannot be verified. No process was stopped.'
    }
    return $proc
}

function Stop-Server {
    $proc = Get-Server
    if (-not $proc) { Write-Host 'E10 server is not running (managed by these scripts).'; return }
    # Windows Stop-Process terminates immediately; only stop between print jobs.
    Stop-Process -Id $proc.Id -ErrorAction Stop
    if (-not $proc.WaitForExit(10000)) { throw 'Server did not exit. Restart cancelled.' }
    Remove-Item -LiteralPath $StateFile -ErrorAction SilentlyContinue
    Write-Host 'E10 server stopped.'
}

function Install-Server {
    if (Get-Server) { throw 'Stop the server with stop.cmd before installing.' }
    if (-not (Test-Path -LiteralPath $Python)) {
        if (Test-Path -LiteralPath (Join-Path $Root '.venv')) {
            throw 'An incompatible .venv exists. Do not copy a Mac/Linux .venv to Windows. Use a fresh project folder.'
        }
        $found = $false
        if (Get-Command py -ErrorAction SilentlyContinue) {
            foreach ($version in @('3.14','3.13','3.12')) {
                $ErrorActionPreference = 'Continue'
                & py "-$version" -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)" 2>$null
                $probeExit = $LASTEXITCODE
                $ErrorActionPreference = 'Stop'
                if ($probeExit -eq 0) {
                    & py "-$version" -m venv (Join-Path $Root '.venv')
                    if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
                    $found = $true
                    break
                }
            }
        }
        if (-not $found -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & python -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] <= (3,14) else 1)"
            if ($LASTEXITCODE -eq 0) {
                & python -m venv (Join-Path $Root '.venv')
                if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
                $found = $true
            }
        }
        if (-not $found) { throw 'Install CPython 3.12, 3.13 or 3.14 with the Python launcher, then run install.cmd again.' }
    }
    & $Python -m pip install -r (Join-Path $Root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the Internet connection and pip output.' }
    if (-not (Test-Path -LiteralPath (Join-Path $Root '.env'))) {
        Copy-Item -LiteralPath (Join-Path $Root '.env.example') -Destination (Join-Path $Root '.env')
    }
    Write-Host 'Installed. Edit .env if needed, then run start.cmd.'
}

function Start-Server {
    if (Get-Server) { Write-Host 'E10 server is already running.'; return }
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Run install.cmd first.' }
    if (-not (Test-Path -LiteralPath (Join-Path $Root '.env'))) { throw 'Missing .env. Run install.cmd first.' }
    # Read the same settings as the server, including environment variable precedence.
    $raw = & $Python -c 'import json; from e10_server import Settings; s=Settings.read(); print(json.dumps(dict(host=s.host,port=s.port,scheme=s.scheme)))'
    if ($LASTEXITCODE -ne 0) { throw 'Invalid server configuration. Check .env.' }
    $config = ($raw -join '') | ConvertFrom-Json
    # Refuse to kill or replace an unmanaged listener.
    if (Get-NetTCPConnection -LocalPort $config.port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $($config.port) is already in use. Stop that instance manually or change SERVER_PORT."
    }
    $stdout = Join-Path $Runtime 'stdout.log'
    $stderr = Join-Path $Runtime 'stderr.log'
    $proc = Start-Process -FilePath $Python -ArgumentList @('-u', ('"' + $Server + '"')) -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    @{
        pid = $proc.Id
        started = $proc.StartTime.ToUniversalTime().Ticks.ToString()
    } | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
    try {
        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            $proc.Refresh()
            if ($proc.HasExited) { throw "Server exited. See $stderr" }
            $listeners = @(Get-NetTCPConnection -LocalPort $config.port -State Listen -ErrorAction SilentlyContinue)
            if ($listeners | Where-Object { $_.OwningProcess -eq $proc.Id }) { $ready = $true; break }
            Start-Sleep -Milliseconds 250
        }
        if (-not $ready) { throw "Server did not open its port. See $stderr" }
    } catch {
        Stop-Server
        throw
    }
    $browserHost = $config.host
    if ($browserHost -eq '0.0.0.0') { $browserHost = '127.0.0.1' }
    if ($browserHost -eq '::') { $browserHost = '::1' }
    if ($browserHost.Contains(':')) { $browserHost = '[' + $browserHost + ']' }
    $url = '{0}://{1}:{2}' -f $config.scheme,$browserHost,$config.port
    Write-Host "E10 server listening: $url"
    Write-Host "Logs: $Runtime"
    try { Start-Process $url } catch { Write-Warning "Open $url in a browser." }
}

$lock = $null
try {
    # Exclusive file handle prevents overlapping start/restart/install commands.
    $lock = [IO.File]::Open((Join-Path $Runtime 'manager.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    switch ($Action) {
        'install' { Install-Server }
        'start'   { Start-Server }
        'stop'    { Stop-Server }
        'restart' { Stop-Server; Start-Server }
    }
} catch {
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
