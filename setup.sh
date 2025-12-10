#!/bin/bash
# Quick setup and verification script for SentinelRouter

set -e  # Exit on error

echo "=================================================="
echo "SentinelRouter - Setup & Verification"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "🐍 Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo -e "${RED}❌ Python 3.11+ required. Found: $python_version${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python $python_version found${NC}"
echo ""

# Check for .env file
echo "🔑 Checking environment configuration..."
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  No .env file found. Creating from .env.example...${NC}"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${YELLOW}📝 Please edit .env and add your API keys:${NC}"
        echo "   - DEEPSEEK_API_KEY"
        echo "   - ANTHROPIC_API_KEY"
        echo ""
    else
        echo -e "${RED}❌ .env.example not found!${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Check if API keys are set
if grep -q "your_.*_api_key_here" .env 2>/dev/null; then
    echo -e "${YELLOW}⚠️  API keys appear to be placeholder values in .env${NC}"
    echo "   Please update with real keys before running the server."
    echo ""
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
    echo ""
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# Run verification script
echo "🔍 Running verification checks..."
python3 verify_fixes.py
verification_result=$?

if [ $verification_result -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=================================================="
    echo "✅ Setup Complete!"
    echo "==================================================${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Update .env with your API keys (if not done already)"
    echo ""
    echo "2. Run tests:"
    echo "   pytest tests/ -v"
    echo ""
    echo "3. Start development server:"
    echo "   uvicorn sentinelrouter.server:app --reload --port 8000"
    echo ""
    echo "4. Or build and run with Docker:"
    echo "   docker-compose up --build"
    echo ""
    echo "5. Test the API:"
    echo "   curl -X POST http://localhost:8000/v1/chat/completions \\"
    echo "     -H 'Content-Type: application/json' \\"
    echo "     -d '{\"messages\": [{\"role\": \"user\", \"content\": \"Hello!\"}], \"session_id\": \"test\"}'"
    echo ""
else
    echo ""
    echo -e "${RED}=================================================="
    echo "❌ Verification Failed"
    echo "==================================================${NC}"
    echo ""
    echo "Please fix the issues above before proceeding."
    exit 1
fi
