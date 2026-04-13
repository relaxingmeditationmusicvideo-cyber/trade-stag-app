#!/bin/bash
# Trade Stag — Setup & Run Script
# ════════════════════════════════

echo "╔══════════════════════════════════════════════════════╗"
echo "║   Trade Stag — NSE 500 Swing Analyzer Web App       ║"
echo "║   India-First · v7.1 Engine · FastAPI + React        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Setup Backend ──
echo "Setting up Python backend..."
cd backend

# Install Python dependencies
pip install -r requirements.txt 2>/dev/null || pip install -r requirements.txt --break-system-packages

# Copy analyzer if not present
if [ ! -f analyzer.py ]; then
    echo ""
    echo "  analyzer.py not found in backend/"
    echo "   The app will run with DEMO DATA."
    echo ""
    echo "   To use LIVE DATA:"
    echo "   1. Copy your nse500_swing_analyzer_vikrant.py to backend/analyzer.py"
    echo "   2. Restart the backend server"
    echo ""
fi

cd ..

# ── Step 2: Setup Frontend ──
echo "Setting up React frontend..."
cd frontend
npm install
cd ..

echo ""
echo "Setup complete!"
echo ""
echo "════════════════════════════════════════════════════════"
echo "  TO RUN THE APP:"
echo ""
echo "  Terminal 1 (Backend):"
echo "    cd backend"
echo "    python main.py"
echo "    -> Runs on http://localhost:8000"
echo ""
echo "  Terminal 2 (Frontend):"
echo "    cd frontend"
echo "    npm start"
echo "    -> Opens http://localhost:3000"
echo ""
echo "  FOR LIVE DATA:"
echo "    Copy your analyzer script to backend/analyzer.py"
echo "    Then POST to http://localhost:8000/api/scan"
echo "════════════════════════════════════════════════════════"
