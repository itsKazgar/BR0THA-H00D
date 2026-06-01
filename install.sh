#!/bin/bash
# ╔══════════════════════════════════════════════╗
# ║     BR0THER-H00D — ONE CLICK INSTALL        ║
# ╚══════════════════════════════════════════════╝

CY='\033[96m'; GR='\033[92m'; YL='\033[93m'; RD='\033[91m'; BD='\033[1m'; RS='\033[0m'

echo -e "${CY}${BD}"
echo "██████╗ ██████╗  ██████╗ ████████╗██╗  ██╗███████╗██████╗       ██╗  ██╗ ██████╗  ██████╗ ██████╗"
echo "██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝██║  ██║██╔════╝██╔══██╗      ██║  ██║██╔═████╗██╔═████╗██╔══██╗"
echo "██████╔╝██████╔╝██║   ██║   ██║   ███████║█████╗  ██████╔╝█████╗███████║██║██╔██║██║██╔██║██║  ██║"
echo "██╔══██╗██╔══██╗██║   ██║   ██║   ██╔══██║██╔══╝  ██╔══██╗╚════╝██╔══██║████╔╝██║████╔╝██║██║  ██║"
echo "██████╔╝██║  ██║╚██████╔╝   ██║   ██║  ██║███████╗██║  ██║      ██║  ██║╚██████╔╝╚██████╔╝██████╔╝"
echo "╚═════╝ ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝      ╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═════╝"
echo -e "${RS}"
echo -e "${BD}Solana Alpha Collective — Install Script${RS}"
echo ""

# ── Python check ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo -e "${RD}Python3 not found. Install it first: sudo apt install python3 python3-pip python3-venv${RS}"
    exit 1
fi
echo -e "${GR}✅ Python3 found: $(python3 --version)${RS}"

# ── Venv ──────────────────────────────────────
if [ ! -d "venv" ]; then
    echo -e "${YL}Creating virtual environment...${RS}"
    python3 -m venv venv
fi
source venv/bin/activate
echo -e "${GR}✅ Virtual environment ready${RS}"

# ── Dependencies ──────────────────────────────
echo -e "${YL}Installing dependencies...${RS}"
pip install -q --upgrade pip
pip install -q requests python-dotenv feedparser beautifulsoup4 psutil solders base58 python-telegram-bot httpx
echo -e "${GR}✅ Dependencies installed${RS}"

# ── .env setup ────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GR}✅ Created .env from template${RS}"
else
    echo -e "${GR}✅ .env already exists${RS}"
fi

# ── RAM check for Hermes ──────────────────────
FREE_RAM=$(free -m | awk '/^Mem:/{print $7}')
echo ""
echo -e "${BD}System check:${RS}"
echo -e "  RAM available: ${FREE_RAM}MB"
if [ "$FREE_RAM" -gt 8000 ]; then
    echo -e "  ${GR}✅ 8GB+ RAM — Hermes AI eligible (see SETUP_HERMES.md)${RS}"
elif [ "$FREE_RAM" -gt 3000 ]; then
    echo -e "  ${YL}⚠️  3-8GB RAM — Groq API recommended (free at console.groq.com)${RS}"
else
    echo -e "  ${YL}⚠️  Low RAM — rule-based mode (still works great)${RS}"
fi

# ── Done ──────────────────────────────────────
echo ""
echo -e "${CY}${BD}╔══════════════════════════════════════════════╗${RS}"
echo -e "${CY}${BD}║   ✅ INSTALL COMPLETE                        ║${RS}"
echo -e "${CY}${BD}╠══════════════════════════════════════════════╣${RS}"
echo -e "${CY}${BD}║   Run now:  python start.py                  ║${RS}"
echo -e "${CY}${BD}║   Tier 0:   works immediately, no keys       ║${RS}"
echo -e "${CY}${BD}║   Tier 1:   add keys to .env for smarter AI  ║${RS}"
echo -e "${CY}${BD}║   Tier 2:   add wallet to .env to go live    ║${RS}"
echo -e "${CY}${BD}╚══════════════════════════════════════════════╝${RS}"
echo ""
