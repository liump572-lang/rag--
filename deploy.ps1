param(
    [switch]$Dev,
    [switch]$ResetData,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$dockerDir = Join-Path $root "docker"
$envFile = Join-Path $dockerDir ".env"
$envExample = Join-Path $dockerDir ".env.example"
$composeFile = Join-Path $dockerDir "docker-compose.yml"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "未找到 $Name，请先安装 Docker Desktop 并确认命令可用。"
    }
}

function Wait-HttpOk($Url, $Name, $Timeout) {
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host "  $Name 可访问：$Url" -ForegroundColor Green
                return
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    throw "$Name 在 $Timeout 秒内未就绪：$Url"
}

Write-Step "检查 Docker 环境"
Require-Command docker
docker version | Out-Null
docker compose version | Out-Null

Write-Step "准备环境变量"
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Host "  已创建 docker\.env，请填写 DEEPSEEK_API_KEY 后再用于真实 AI 问答。" -ForegroundColor Yellow
}

$envContent = Get-Content $envFile -Raw
if ($envContent -match "your-deepseek-api-key-here|sk-your-deepseek-api-key-here") {
    Write-Host "  提醒：当前 DEEPSEEK_API_KEY 仍是模板值，部署可启动，但 AI 抽取和问答会退化或失败。" -ForegroundColor Yellow
}

$profileArgs = @()
if ($Dev) {
    $profileArgs = @("--profile", "dev")
}

Write-Step "启动服务"
Push-Location $dockerDir
try {
    if ($ResetData) {
        Write-Host "  将清空 MySQL、Neo4j、ChromaDB、Redis、uploads 数据卷。" -ForegroundColor Yellow
        docker compose --env-file .env -f $composeFile down -v --remove-orphans
    } else {
        docker compose --env-file .env -f $composeFile down --remove-orphans
    }
    docker compose --env-file .env -f $composeFile up -d --build @profileArgs

    Write-Step "等待服务健康"
    Wait-HttpOk "http://localhost:8000/api/v1/health" "后端健康检查" $TimeoutSeconds
    Wait-HttpOk "http://localhost/" "前端页面" $TimeoutSeconds

    Write-Step "当前容器状态"
    docker compose --env-file .env -f $composeFile ps
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "部署完成：" -ForegroundColor Green
Write-Host "  前端：http://localhost"
Write-Host "  后端文档：http://localhost:8000/docs"
Write-Host "  健康检查：http://localhost:8000/api/v1/health"
Write-Host "  Neo4j：http://localhost:7474"
