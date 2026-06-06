# Multi-Agent PM System - Quick Start (Windows PowerShell)
# Usage:
#   .\quickstart.ps1                       (runs with demo fallback, no API key needed)
#   .\quickstart.ps1 -ApiKey "your-key"    (runs with live G42 Compass AI)

param(
    [string]$ApiKey = ""
)

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Multi-Agent PM System - Quick Start" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1 - check Python is installed
Write-Host "[1/5] Checking Python..." -ForegroundColor Cyan
try {
    $pyVersion = python --version 2>&1
    Write-Host "      Found: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "      ERROR: Python not found." -ForegroundColor Red
    Write-Host "      Install from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "      Tick 'Add Python to PATH' during install, then re-run this script." -ForegroundColor Yellow
    exit 1
}

# Step 2 - create .env from example
Write-Host "[2/5] Setting up environment..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "      Created .env from .env.example" -ForegroundColor Green
} else {
    Write-Host "      .env already exists - skipping" -ForegroundColor Yellow
}

if ($ApiKey -ne "") {
    (Get-Content ".env") -replace "OPENAI_API_KEY=.*", "OPENAI_API_KEY=$ApiKey" | Set-Content ".env"
    Write-Host "      Compass API key set" -ForegroundColor Green
} else {
    (Get-Content ".env") -replace "SAMPLE_MODE=.*", "SAMPLE_MODE=true" | Set-Content ".env"
    Write-Host "      No API key provided - demo fallback enabled" -ForegroundColor Yellow
}

# Step 3 - create virtual environment
Write-Host "[3/5] Creating virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "      Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "      Virtual environment already exists - skipping" -ForegroundColor Yellow
}

# Step 4 - install dependencies
Write-Host "[4/5] Installing dependencies..." -ForegroundColor Cyan
& venv\Scripts\pip install -r requirements.txt --quiet
Write-Host "      Dependencies installed" -ForegroundColor Green

# Step 5 - start the server
Write-Host "[5/5] Starting server..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  App:       http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Swagger:   http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

& venv\Scripts\python run.py
