[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoPause,
    [ValidateRange(5, 180)][int]$ReadyTimeoutSeconds = 60
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$baseUrl = 'http://127.0.0.1:8000'
$launcherLock = $null
$ownsLock = $false
$exitCode = 0
$stderrPath = $null

function Get-PortListeners {
    @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -eq 8000 })
}

function Test-ProjectProcess([int]$ProcessId) {
    # Windows venv python.exe launches a child using the base interpreter.
    # Verify the listener or its live parent, including the exact venv path.
    $childCreated = $null
    for ($depth = 0; $depth -lt 4 -and $ProcessId -gt 0; $depth++) {
        $info = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        if (-not $info) { return $false }
        if ($childCreated -and $info.CreationDate -gt $childCreated) { return $false }
        if (($info.ExecutablePath -ieq $pythonPath) -and
            ($info.CommandLine -match '(?i)\s-m\s+uvicorn\s+app\.main:app(?:\s|$)')) {
            return $true
        }
        $childCreated = $info.CreationDate
        $ProcessId = [int]$info.ParentProcessId
    }
    return $false
}

function Assert-ProjectListeners($Listeners) {
    foreach ($ownerId in @($Listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        if (-not (Test-ProjectProcess -ProcessId $ownerId)) {
            throw "8000 端口被其他或无法确认身份的程序占用（PID $ownerId）。未结束任何进程，请先确认该程序用途。"
        }
    }
}

function Get-Readiness {
    $request = [System.Net.HttpWebRequest]::Create("$baseUrl/health/ready")
    $request.Proxy = $null
    $request.Timeout = 8000
    $request.ReadWriteTimeout = 8000
    $request.AllowAutoRedirect = $false
    $response = $null
    try {
        try { $response = $request.GetResponse() }
        catch [System.Net.WebException] {
            if (-not $_.Exception.Response) { return 'not_reachable' }
            $response = $_.Exception.Response
        }
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        try { $body = $reader.ReadToEnd() | ConvertFrom-Json }
        finally { $reader.Dispose() }
        if ([int]$response.StatusCode -eq 200 -and $body.status -eq 'ready') { return 'ready' }
        if ($body.status -in @('not_configured', 'migration_required', 'unavailable')) { return $body.status }
        return 'unexpected_response'
    }
    catch { return 'unexpected_response' }
    finally { if ($response) { $response.Dispose() } }
}

try {
    Write-Host '人生冒险之旅：正在检查本地服务……'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw '未找到项目 .venv\Scripts\python.exe。请恢复项目 Python 虚拟环境；启动器不会自动安装或重建环境。'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'app\main.py') -PathType Leaf)) {
        throw '未找到 app\main.py，请将 scripts 目录与原项目一起保存。'
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $rootHash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot.ToLowerInvariant()))).Replace('-', '') }
    finally { $sha.Dispose() }
    $launcherLock = New-Object System.Threading.Mutex($false, "Local\AdventureCampLauncher-$rootHash")
    try { $ownsLock = $launcherLock.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $ownsLock = $true }
    if (-not $ownsLock) {
        Write-Host '另一个启动器正在检查或启动服务，请等待它完成。'
    }
    else {
        $listeners = @(Get-PortListeners)
        $serverProcess = $null
        if ($listeners.Count -gt 0) {
            Assert-ProjectListeners $listeners
            Write-Host '当前项目已在运行，不重复启动。正在检查数据库就绪状态……'
        }
        else {
            $logRoot = Join-Path $env:LOCALAPPDATA 'AdventureCamp\logs'
            New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
            $runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
            $stdoutPath = Join-Path $logRoot "$runId.stdout.log"
            $stderrPath = Join-Path $logRoot "$runId.stderr.log"
            $serverProcess = Start-Process -FilePath $pythonPath -WorkingDirectory $projectRoot `
                -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log') `
                -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
            Write-Host '服务已启动，等待健康检查（通常数秒，最长约一分钟）……'
            Write-Host "错误日志：$stderrPath"
        }
        $deadline = [DateTime]::UtcNow.AddSeconds($ReadyTimeoutSeconds)
        $lastState = 'not_reachable'
        $ready = $false
        do {
            if ($serverProcess) {
                $serverProcess.Refresh()
                if ($serverProcess.HasExited) {
                    throw "服务进程已退出（退出码 $($serverProcess.ExitCode)）。请查看上方错误日志，检查 Python 依赖和现有配置。"
                }
            }
            $listeners = @(Get-PortListeners)
            if ($listeners.Count -gt 0) {
                Assert-ProjectListeners $listeners
                $lastState = Get-Readiness
                if ($lastState -eq 'ready') { $ready = $true; break }
                if ($lastState -eq 'not_configured') { throw '服务已运行，但数据库未配置。请检查现有 .env 的 DATABASE_URL；未修改配置或数据库。' }
                if ($lastState -eq 'migration_required') { throw '服务已运行，但数据库迁移版本与应用不一致。请人工检查；启动器不会自动执行迁移。' }
            }
            Start-Sleep -Milliseconds 750
        } while ([DateTime]::UtcNow -lt $deadline)
        if (-not $ready) {
            if ($lastState -eq 'unavailable') {
                throw '健康检查超时：服务已运行，但数据库连接失败。请检查网络及 Supabase 可用性，恢复后可再次双击启动器。'
            }
            throw "健康检查超时（$lastState）。请查看错误日志；不会打开未就绪的网页或结束任何进程。"
        }
        Write-Host "服务已就绪：$baseUrl"
        if (-not $NoBrowser) {
            try { Start-Process -FilePath $baseUrl | Out-Null }
            catch { throw "服务已就绪，但无法打开默认浏览器。请手动访问 $baseUrl" }
        }
    }
}
catch {
    $exitCode = 1
    Write-Host ''
    Write-Host "启动未完成：$($_.Exception.Message)" -ForegroundColor Red
    if ($stderrPath) { Write-Host "错误日志：$stderrPath" }
    if (-not $NoPause) { Read-Host '按 Enter 关闭此窗口' | Out-Null }
}
finally {
    if ($ownsLock) { $launcherLock.ReleaseMutex() }
    if ($launcherLock) { $launcherLock.Dispose() }
}
exit $exitCode
