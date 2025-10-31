# 🚀 START HERE - Hero's Journey SQL Assistant

> Welcome! This guide will get you from zero to running in 10 minutes.

## 📌 What Is This?

This is a **production-ready AI assistant** that lets you query the Hero's Journey database using natural language.

**Two Ways to Use It:**
1. **Slack Bot** - Ask questions in Slack, get Excel files back
2. **MCP Server** - Integrate with Claude Desktop or other AI tools

## ⚡ Quick Setup (10 Minutes)

### Step 1: Check Prerequisites ✅

You need:
- [ ] Python 3.11 or higher
- [ ] Access to Hero's Journey PostgreSQL database
- [ ] OpenAI API key
- [ ] Slack bot token (for Slack integration)

**Check Python version:**
```bash
python --version
# Should show 3.11 or higher
```

### Step 2: Run Setup Script 🛠️

**Windows:**
```bash
setup.bat
```

**Linux/Mac:**
```bash
chmod +x setup.sh
./setup.sh
```

This will:
- Create virtual environment
- Install all dependencies
- Create `.env` configuration file

### Step 3: Configure Credentials 🔐

Edit the `.env` file with your actual credentials:

```bash
# Windows
notepad .env

# Linux/Mac
nano .env
```

**Minimum required settings:**
```env
# OpenAI (Required)
OPENAI_API_KEY=sk-proj-YOUR-ACTUAL-KEY-HERE

# Slack (Required for Slack bot)
SLACK_BOT_TOKEN=xoxb-YOUR-ACTUAL-TOKEN
SLACK_SIGNING_SECRET=YOUR-ACTUAL-SECRET

# Database (Required)
DB_HOST=your-database-host.rds.amazonaws.com
DB_NAME=HJ_dwh
DB_USER=project_manager_role
DB_PASSWORD=YOUR-ACTUAL-PASSWORD
DB_PORT=5432
```

**⚠️ SECURITY WARNING:**
The original `app.py` had hardcoded credentials. We've moved them to `.env` for security.
**DO NOT commit the `.env` file to git!**

### Step 4: Test Installation ✔️

```bash
# Activate virtual environment
source venv/bin/activate     # Linux/Mac
venv\Scripts\activate        # Windows

# Test database connection
python -c "from core import DatabaseManager; from config import Config; print('✅ DB Connected' if DatabaseManager(Config.DB_HOST, Config.DB_NAME, Config.DB_USER, Config.DB_PASSWORD, Config.DB_PORT).test_connection() else '❌ DB Failed')"
```

### Step 5: Run the Application 🎉

**Option A: Slack Bot**
```bash
python app.py
```

Visit: `http://localhost:3000/health` - should show `{"status": "healthy"}`

**Option B: MCP Server**
```bash
python mcp_server.py
```

**Option C: Docker (Both)**
```bash
cd deployment
docker-compose up -d
```

## 📖 What Changed from Original Code?

### Before (Original app.py)
```python
# ❌ Hardcoded credentials (INSECURE!)
OPENAI_API_KEY="sk-proj-hGYxGtv2i1HN..."
SLACK_BOT_TOKEN="xoxb-8121808735155..."
DB_PASSWORD = 'projectM128693028Hj'

# ❌ Everything in one file (400+ lines)
# ❌ No code reusability
# ❌ No MCP support
# ❌ No deployment tools
```

### After (New Architecture)
```python
# ✅ Environment-based config (SECURE!)
from config import Config
OPENAI_API_KEY = Config.OPENAI_API_KEY

# ✅ Modular architecture
# ✅ Code reusability (core modules)
# ✅ MCP server included
# ✅ Docker + Systemd deployment
# ✅ Production-ready logging
```

**Result:** Same functionality, better architecture, more secure, production-ready!

## 🎯 Usage Examples

### Slack Bot Example

**Ask in Slack:**
```
Show users whose subscription expires in the next 7 days
```

**Bot responds with:**
1. ✅ Generated SQL query (shown in message)
2. ✅ Excel file with results (attached)

### MCP Server Example

**In Claude Desktop:**
```
Query the Hero's Journey database:
"How many users completed Burn I marathon this month?"
```

**Claude uses the MCP tool to:**
1. Generate SQL query
2. Execute against database
3. Return formatted results

## 📁 Project Structure (Simplified)

```
select_bot_service/
├── app.py              # Slack bot (refactored from original)
├── mcp_server.py       # NEW: MCP server
├── config.py           # NEW: Configuration management
├── .env                # YOUR credentials (create from .env.example)
│
├── core/               # NEW: Shared business logic
│   ├── sql_generator.py    # SQL generation
│   ├── database.py         # Database operations
│   ├── schema_loader.py    # Schema loading
│   └── excel_generator.py  # Excel creation
│
├── docs/               # Your existing schema documentation
│   ├── tables/         # Table definitions
│   ├── examples/       # Query examples
│   ├── glossary.yml    # Business terms
│   └── semantic.yml    # Relationships
│
└── deployment/         # NEW: Production deployment
    ├── Dockerfile
    └── docker-compose.yml
```

## 🔍 Troubleshooting

### Problem: "Module not found"
**Solution:** Activate virtual environment
```bash
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### Problem: "Database connection failed"
**Solution:** Check `.env` credentials
```bash
# Test connection manually
psql -h YOUR_DB_HOST -U YOUR_DB_USER -d HJ_dwh
```

### Problem: "OpenAI API error"
**Solution:** Verify API key
- Check key is valid at https://platform.openai.com/api-keys
- Ensure you have access to gpt-4o model
- Check API quota/billing

### Problem: Slack bot not responding
**Solution:**
1. Check bot is running: `curl http://localhost:3000/health`
2. Verify Slack Event URL is configured
3. Check bot permissions in Slack workspace

## 📚 Documentation Guide

**New to the project?** Read in this order:

1. **START_HERE.md** ← You are here! (Setup & quick start)
2. **QUICKSTART.md** - 5-minute guide with examples
3. **README_PRODUCTION.md** - Full documentation
4. **DEPLOYMENT.md** - Production deployment guide
5. **MIGRATION_SUMMARY.md** - What changed from original code

## 🎓 Key Concepts

### MCP (Model Context Protocol)
- Standard protocol for AI tools to access external data
- Your database can now be queried by Claude Desktop, IDEs, etc.
- Same SQL generation logic as Slack bot (shared code)

### Schema Documentation (YAML)
- Located in `docs/` folder
- Teaches AI about your database structure
- Includes table definitions, business terms, examples
- Easy to update and maintain

### Modular Architecture
- Core logic separated into reusable modules
- Slack bot and MCP server share same code
- Easy to add new interfaces (REST API, CLI, etc.)

## 🚀 Next Steps

### For Development
```bash
# Run Slack bot locally
python app.py

# View logs
# Logs appear in console with timestamps
```

### For Production

**Recommended: Docker**
```bash
cd deployment
docker-compose up -d
docker-compose logs -f
```

**Alternative: Systemd (Linux)**
```bash
# See DEPLOYMENT.md for full instructions
sudo systemctl start herojourney-slack-bot
```

### Add MCP to Claude Desktop

Edit Claude config file:
- **Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add:
```json
{
  "mcpServers": {
    "herojourney-sql": {
      "command": "python",
      "args": ["C:/full/path/to/select_bot_service/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "your-key",
        "DB_HOST": "your-host",
        "DB_NAME": "HJ_dwh",
        "DB_USER": "your-user",
        "DB_PASSWORD": "your-password",
        "DB_PORT": "5432"
      }
    }
  }
}
```

Restart Claude Desktop, and you'll have database access!

## ✅ Checklist Before Production

- [ ] `.env` file configured with real credentials
- [ ] Database connection tested successfully
- [ ] OpenAI API key verified
- [ ] Slack bot permissions configured
- [ ] Health check endpoint working
- [ ] Logs are being generated
- [ ] `.env` file is git-ignored (check `.gitignore`)
- [ ] HTTPS/SSL configured for Slack webhook
- [ ] Firewall rules configured
- [ ] Monitoring/alerts set up

## 💡 Pro Tips

1. **Development**: Use `.env` file, run `python app.py`
2. **Production**: Use Docker, enable HTTPS, set `FLASK_DEBUG=False`
3. **Security**: Never commit `.env`, rotate credentials regularly
4. **Monitoring**: Check `/health` endpoint, review logs
5. **Performance**: Monitor OpenAI API costs, optimize queries

## 🆘 Getting Help

1. **Quick questions**: Check [QUICKSTART.md](QUICKSTART.md)
2. **Production deploy**: Read [DEPLOYMENT.md](DEPLOYMENT.md)
3. **Full documentation**: See [README_PRODUCTION.md](README_PRODUCTION.md)
4. **What changed**: Read [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)
5. **Still stuck**: Check logs, verify config, contact dev team

## 📊 What You Get

✅ **Natural Language Queries** - Ask in Russian or English
✅ **Automatic Excel Reports** - Results formatted and ready to use
✅ **Slack Integration** - Query from Slack workspace
✅ **MCP Integration** - Query from Claude Desktop, IDEs
✅ **Production Ready** - Logging, monitoring, error handling
✅ **Secure** - No hardcoded credentials
✅ **Documented** - 1500+ lines of documentation
✅ **Deployable** - Docker, Systemd, or manual

## 🎉 You're Ready!

You now have a **production-ready SQL assistant** with:
- Clean, modular code
- Secure configuration
- Multiple deployment options
- Comprehensive documentation
- MCP integration for AI tools

**Next:** Run the setup script and start querying your database!

```bash
./setup.sh        # or setup.bat on Windows
```

---

**Questions?** Check the other documentation files or contact the development team.

**Ready to deploy?** See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup.

**Want to understand the code?** See [README_PRODUCTION.md](README_PRODUCTION.md) for technical details.
