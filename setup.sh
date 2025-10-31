#!/bin/bash
# Setup script for Hero's Journey SQL Assistant

set -e  # Exit on error

echo "=================================="
echo "Hero's Journey SQL Assistant Setup"
echo "=================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo -e "${GREEN}Found Python ${PYTHON_VERSION}${NC}"

if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo -e "${YELLOW}Warning: Python 3.11+ recommended (you have ${PYTHON_VERSION})${NC}"
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists, skipping...${NC}"
else
    python3 -m venv venv
    echo -e "${GREEN}Virtual environment created${NC}"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt
echo -e "${GREEN}Dependencies installed${NC}"

# Create .env file if it doesn't exist
echo ""
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo -e "${GREEN}.env file created${NC}"
    echo -e "${YELLOW}Please edit .env file with your actual credentials${NC}"
else
    echo -e "${YELLOW}.env file already exists${NC}"
fi

# Check required directories
echo ""
echo "Checking directories..."
if [ ! -d "docs" ]; then
    echo -e "${RED}Error: docs/ directory not found${NC}"
    exit 1
fi
if [ ! -d "docs/tables" ]; then
    echo -e "${RED}Error: docs/tables/ directory not found${NC}"
    exit 1
fi
echo -e "${GREEN}Required directories present${NC}"

# Test imports
echo ""
echo "Testing imports..."
if python3 -c "from core import SchemaLoader, SQLGenerator, DatabaseManager, ExcelGenerator" 2>/dev/null; then
    echo -e "${GREEN}Core modules import successfully${NC}"
else
    echo -e "${RED}Error: Failed to import core modules${NC}"
    exit 1
fi

# Summary
echo ""
echo "=================================="
echo -e "${GREEN}Setup completed successfully!${NC}"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials:"
echo "   nano .env"
echo ""
echo "2. Activate virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "3. Run Slack bot:"
echo "   python app.py"
echo ""
echo "4. Or run MCP server:"
echo "   python mcp_server.py"
echo ""
echo "For production deployment, see DEPLOYMENT.md"
echo ""
