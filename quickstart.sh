#!/bin/bash
# Multi-Agent PM System — Quick Start (Mac / Linux)
# Usage:
#   ./quickstart.sh                        (runs with demo fallback — no API key needed)
#   ./quickstart.sh "your-compass-key"     (runs with live G42 Compass AI)

API_KEY=${1:-""}

echo ""
echo "================================================"
echo "  Multi-Agent PM System — Quick Start"
echo "================================================"
echo ""

# Step 1 — create .env from example
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[1/3] Created .env from .env.example"
else
    echo "[1/3] .env already exists — skipping"
fi

# Step 2 — inject API key if provided
if [ -n "$API_KEY" ]; then
    sed -i "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$API_KEY/" .env
    echo "[2/3] Compass API key set"
else
    sed -i "s/SAMPLE_MODE=.*/SAMPLE_MODE=true/" .env
    echo "[2/3] No API key provided — running with built-in demo fallback"
fi

# Step 3 — build and start
echo "[3/3] Building and starting Docker container..."
echo ""
docker compose up --build

echo ""
echo "App running at: http://localhost:8000"
echo "Swagger UI:     http://localhost:8000/docs"
echo ""
