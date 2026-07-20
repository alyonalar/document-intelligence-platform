param(
    [Parameter(Position = 0)]
    [ValidateSet("install", "migrate", "seed", "run", "worker", "test", "bootstrap")]
    [string]$Command = "bootstrap",

    [int]$Port = 8000,
    [double]$WorkerInterval = 2.0
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$CodexVenvPython = Join-Path $ProjectRoot ".venv-codex\Scripts\python.exe"

function Test-PythonCommand {
    param([string]$Python)

    if (-not $Python) {
        return $false
    }

    try {
        & $Python --version *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Get-BasePython {
    if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-PythonCommand "py")) {
        return "py"
    }
    if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-PythonCommand "python")) {
        return "python"
    }
    return ""
}

function Get-ProjectPython {
    if ($env:DOCUMENT_ASSISTANT_PYTHON -and (Test-PythonCommand $env:DOCUMENT_ASSISTANT_PYTHON)) {
        return $env:DOCUMENT_ASSISTANT_PYTHON
    }
    if ((Test-Path $VenvPython) -and (Test-PythonCommand $VenvPython)) {
        return $VenvPython
    }
    if ((Test-Path $CodexVenvPython) -and (Test-PythonCommand $CodexVenvPython)) {
        return $CodexVenvPython
    }

    $BasePython = Get-BasePython
    if ($BasePython) {
        return $BasePython
    }

    throw "No working Python interpreter found. Install Python or set DOCUMENT_ASSISTANT_PYTHON to python.exe."
}

function Invoke-ProjectPython {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    $Python = Get-ProjectPython
    & $Python @Arguments
}

function Install-Project {
    if (-not (Test-Path $VenvPython) -or -not (Test-PythonCommand $VenvPython)) {
        $BasePython = Get-BasePython
        if (-not $BasePython) {
            Write-Host "No system Python found; installing dependencies into the current project interpreter."
            Invoke-ProjectPython -m pip install --upgrade pip
            Invoke-ProjectPython -m pip install -r requirements-dev.txt
            return
        }

        Write-Host "Creating virtual environment in .venv"
        if ($BasePython -eq "py") {
            & py -m venv .venv
        }
        else {
            & python -m venv .venv
        }
    }

    Invoke-ProjectPython -m pip install --upgrade pip
    Invoke-ProjectPython -m pip install -r requirements-dev.txt

    if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example"
    }
}

function Invoke-Migrations {
    Invoke-ProjectPython -m alembic upgrade head
}

function Invoke-DemoSeed {
    Invoke-ProjectPython -m app.seed_demo
}

function Run-App {
    Invoke-ProjectPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
}

function Run-Worker {
    Invoke-ProjectPython -m app.worker --loop --interval $WorkerInterval
}

function Run-Tests {
    Invoke-ProjectPython -m pytest
}

switch ($Command) {
    "install" {
        Install-Project
    }
    "migrate" {
        Invoke-Migrations
    }
    "seed" {
        Invoke-DemoSeed
    }
    "run" {
        Run-App
    }
    "worker" {
        Run-Worker
    }
    "test" {
        Run-Tests
    }
    "bootstrap" {
        Install-Project
        Invoke-Migrations
        Invoke-DemoSeed
        Write-Host ""
        Write-Host "Bootstrap complete."
        Write-Host "Run the app:    .\scripts\dev.ps1 run"
        Write-Host "Run worker:     .\scripts\dev.ps1 worker"
        Write-Host "Open:           http://127.0.0.1:$Port"
    }
}
