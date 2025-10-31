# Quick Start Guide

Get Hero's Journey SQL Assistant running in 5 minutes!

## Prerequisites

- Python 3.11+
- PostgreSQL database access
- OpenAI API key
- Slack workspace (for bot integration)

## Setup Steps

### 1. Clone/Download Project

```bash
cd select_bot_service
```

### 2. Run Setup Script

**Linux/Mac:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```bash
setup.bat
```

### 3. Configure Environment

Edit `.env` file with your credentials:

```bash
# Use your preferred editor
nano .env        # Linux/Mac
notepad .env     # Windows
```

**Minimum required settings:**
```env
OPENAI_API_KEY=sk-proj-your-actual-key
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
DB_HOST=your-database-host
DB_USER=your-db-user
DB_PASSWORD=your-db-password
```

### 4. Test Configuration

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Test database connection
python -c "from core import DatabaseManager; from config import Config; print('✅ DB OK' if DatabaseManager(Config.DB_HOST, Config.DB_NAME, Config.DB_USER, Config.DB_PASSWORD, Config.DB_PORT).test_connection() else '❌ DB Failed')"
```

### 5. Run Application

**Option A: Slack Bot**
```bash
python app.py
```

**Option B: MCP Server**
```bash
python mcp_server.py
```

**Option C: Docker (Both Services)**
```bash
cd deployment
docker-compose up -d
```

### 6. Verify It's Working

**Check health endpoint:**
```bash
curl http://localhost:3000/health
```

**Expected response:**
```json
{"status": "healthy", "database": true, "schema_tables": 7}
```

## Usage Examples

### Slack Bot

Send a message in your Slack channel:
```
Show users whose subscription expires in the next 7 days
```

Bot will respond with:
1. Generated SQL query
2. Excel file with results

### MCP Server with Claude Desktop

1. **Configure Claude Desktop**

   Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)
   or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

   ```json
   {
     "mcpServers": {
       "herojourney-sql": {
         "command": "python",
         "args": ["C:/path/to/select_bot_service/mcp_server.py"],
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

2. **Restart Claude Desktop**

3. **Use the tools**

   In Claude Desktop:
   ```
   Query the Hero's Journey database:
   "Show all users who completed Burn I marathon"
   ```

## Common Issues

### Issue: "Module not found"
**Solution:** Activate virtual environment first
```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
```

### Issue: "Database connection failed"
**Solution:**
- Check `.env` credentials are correct
- Verify database is accessible: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`
- Check firewall rules

### Issue: "OpenAI API error"
**Solution:**
- Verify API key is valid
- Check you have access to gpt-4o model
- Verify API quota

### Issue: Slack bot not responding
**Solution:**
- Check bot is running: `curl http://localhost:3000/health`
- Verify Slack event URL is configured: `https://your-domain.com/slack/events`
- Check bot has proper Slack permissions

## Next Steps

✅ **Production Deployment**: See [DEPLOYMENT.md](DEPLOYMENT.md)

✅ **Full Documentation**: See [README_PRODUCTION.md](README_PRODUCTION.md)

✅ **Customize Schema**: Edit YAML files in `docs/` folder

## Architecture Overview

```
User Question → Slack/MCP → SQL Generator → Database → Excel → Response
                              ↓
                        Schema Docs (YAML)
```

## File Structure

```
select_bot_service/
├── app.py              # Slack bot
├── mcp_server.py       # MCP server
├── config.py           # Configuration
├── core/               # Business logic
│   ├── sql_generator.py
│   ├── database.py
│   ├── schema_loader.py
│   └── excel_generator.py
├── docs/               # Schema documentation
│   ├── tables/
│   ├── examples/
│   ├── glossary.yml
│   └── semantic.yml
└── deployment/         # Docker & systemd files
```

## Key Features

- 🤖 **Natural Language**: Ask questions in Russian or English
- 📊 **Auto Excel**: Results automatically formatted in Excel
- 🔒 **Secure**: No hardcoded credentials
- 🐳 **Docker Ready**: Deploy with one command
- 📝 **Well Documented**: YAML-based schema docs
- 🔌 **MCP Compatible**: Works with Claude Desktop, IDEs

## Getting Help

1. **Check logs**: Look for error messages
2. **Review docs**: [DEPLOYMENT.md](DEPLOYMENT.md), [README_PRODUCTION.md](README_PRODUCTION.md)
3. **Test components**: Use health check endpoint
4. **Contact support**: Reach out to development team

---

**Ready to go?** Start with step 1 above!

**Questions?** Check the full documentation or contact support.
