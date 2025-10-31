# Hero's Journey SQL Assistant - Production Edition

> AI-powered SQL query generation for Hero's Journey data warehouse with Slack integration and MCP support

## Overview

This production-ready application provides natural language access to Hero's Journey database through:
- **Slack Bot**: Query database directly from Slack, receive Excel results
- **MCP Server**: Expose database access to AI tools (Claude Desktop, IDEs, etc.)

## Features

### Core Capabilities
- ✅ Natural language to SQL query generation (Russian/English)
- ✅ Automatic query execution against PostgreSQL
- ✅ Excel file generation from query results
- ✅ Slack integration with file upload
- ✅ MCP server for AI tool integration
- ✅ Comprehensive schema documentation system
- ✅ Production-ready logging and error handling

### Architecture Highlights
- 🏗️ **Modular Design**: Shared core modules for reusability
- 🔒 **Security**: Environment-based configuration, no hardcoded credentials
- 📊 **Logging**: Structured logging for debugging and monitoring
- 🐳 **Docker Ready**: Containerized deployment with Docker Compose
- 🔄 **Systemd Support**: Linux service management
- 🏥 **Health Checks**: Built-in health monitoring endpoints

## Project Structure

```
select_bot_service/
├── app.py                      # Slack bot service
├── mcp_server.py              # MCP server implementation
├── config.py                  # Configuration management
├── requirements.txt           # Python dependencies
│
├── core/                      # Shared business logic
│   ├── schema_loader.py       # YAML schema loading
│   ├── sql_generator.py       # OpenAI SQL generation
│   ├── database.py            # PostgreSQL operations
│   └── excel_generator.py     # Excel file creation
│
├── utils/                     # Utilities
│   └── logger.py              # Logging configuration
│
├── docs/                      # Database schema documentation
│   ├── tables/                # Table definitions (YAML)
│   ├── examples/              # Query examples
│   ├── glossary.yml           # Business terms
│   └── semantic.yml           # Relationships & metrics
│
└── deployment/                # Production deployment
    ├── Dockerfile
    ├── docker-compose.yml
    └── systemd/               # Linux service files
```

## Quick Start

### 1. Setup Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required environment variables:
```
OPENAI_API_KEY=your-openai-key
SLACK_BOT_TOKEN=xoxb-your-slack-token
SLACK_SIGNING_SECRET=your-slack-secret
DB_HOST=your-database-host
DB_USER=your-database-user
DB_PASSWORD=your-database-password
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 3. Run Services

**Option A: Docker (Recommended)**
```bash
cd deployment
docker-compose up -d
```

**Option B: Manual**
```bash
# Slack Bot
python app.py

# MCP Server (separate terminal)
python mcp_server.py
```

### 4. Verify Installation

```bash
# Check health
curl http://localhost:3000/health

# Expected response:
# {"status": "healthy", "database": true, "schema_tables": 7}
```

## Usage

### Slack Bot

Ask questions in natural language:

**Examples:**
- "Show users whose subscription expires in the next 7 days"
- "Покажи всех пользователей на марафоне Hero's Week"
- "How many payments were made for Burn I program this month?"

**Response:**
1. Generated SQL query (formatted)
2. Excel file with results (if data exists)
3. Error message (if query failed)

### MCP Server

Connect from Claude Desktop or other MCP clients.

**Available Tools:**

1. **query_database** - Natural language queries
   ```json
   {
     "question": "Show all active subscriptions",
     "return_format": "table"
   }
   ```

2. **execute_sql** - Direct SQL execution
   ```json
   {
     "sql": "SELECT * FROM olap_schema.userheropass LIMIT 10",
     "return_format": "excel"
   }
   ```

3. **get_schema_info** - Schema documentation
   ```json
   {
     "table_name": "booking"
   }
   ```

## Configuration

### Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | OpenAI model | gpt-4o |
| `SLACK_BOT_TOKEN` | Slack bot token | Required |
| `DB_HOST` | Database host | Required |
| `DB_NAME` | Database name | HJ_dwh |
| `FLASK_PORT` | Web server port | 3000 |
| `LOG_LEVEL` | Logging level | INFO |

See [.env.example](.env.example) for full configuration.

## Database Schema

The system uses YAML documentation for:
- **Tables**: 7 core tables (userheropass, booking, etc.)
- **Business Terms**: Program names, synonyms, mappings
- **Query Examples**: Pre-built examples for AI training
- **Relationships**: Table joins and foreign keys

### Available Tables

- `olap_schema.userheropass` - User subscriptions
- `olap_schema.usermarathonevent` - Marathon participation
- `olap_schema.booking` - Training bookings
- `olap_schema.usercheckin` - Check-ins
- `olap_schema.userpayment` - Payments
- `olap_schema.notifications` - Notifications
- `olap_schema.event` - Events

## Development

### Code Quality

**Type Hints:**
```python
def generate_query(user_prompt: str) -> str:
    """Generate SQL query from natural language."""
```

**Logging:**
```python
from utils.logger import setup_logger
logger = setup_logger(__name__)
logger.info("Processing query...")
```

**Error Handling:**
```python
try:
    result = db_manager.execute_query(sql)
except Exception as e:
    logger.error("Query failed: %s", str(e))
```

### Testing

```bash
# Test database connection
python -c "from core import DatabaseManager; from config import Config; \
    db = DatabaseManager(Config.DB_HOST, Config.DB_NAME, Config.DB_USER, Config.DB_PASSWORD); \
    print('Success' if db.test_connection() else 'Failed')"

# Test schema loading
python -c "from core import SchemaLoader; from config import Config; \
    schema = SchemaLoader(Config.DOCS_DIR).load_all(); \
    print(f'Loaded {len(schema[\"tables\"])} tables')"
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed production deployment guide.

### Quick Deploy with Docker

```bash
cd deployment
docker-compose up -d
docker-compose logs -f
```

### Production Checklist

- [ ] Set all environment variables in `.env`
- [ ] Test database connection
- [ ] Configure Slack webhook URL
- [ ] Set `FLASK_DEBUG=False`
- [ ] Set `LOG_LEVEL=INFO` or `WARNING`
- [ ] Enable HTTPS/SSL
- [ ] Configure firewall rules
- [ ] Setup monitoring/alerts
- [ ] Test health check endpoint
- [ ] Backup database credentials securely

## Monitoring

### Health Check
```bash
curl http://localhost:3000/health
```

### Logs

**Docker:**
```bash
docker-compose logs -f slack-bot
```

**Systemd:**
```bash
sudo journalctl -u herojourney-slack-bot -f
```

### Metrics to Monitor

- Response time
- Error rate
- Database connection status
- OpenAI API usage
- Slack message volume

## Troubleshooting

### Common Issues

**1. Database Connection Failed**
- Verify credentials in `.env`
- Check database is accessible
- Test with `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`

**2. Slack Bot Not Responding**
- Check `/health` endpoint
- Verify Slack event URL is configured
- Check bot permissions in Slack
- Review logs for errors

**3. OpenAI API Errors**
- Verify API key is valid
- Check quota limits
- Ensure model access (gpt-4o)

**4. Schema Not Loading**
- Verify `docs/` folder exists
- Check YAML syntax
- Review file permissions

## Security

### Best Practices

1. **Never commit `.env` files**
2. **Use strong database passwords**
3. **Rotate API keys regularly**
4. **Run as non-root user**
5. **Enable HTTPS in production**
6. **Implement rate limiting**
7. **Monitor for suspicious queries**
8. **Keep dependencies updated**

## Performance

### Optimization Tips

- Use database indexes on frequently queried columns
- Implement query caching for common requests
- Monitor OpenAI API response times
- Use connection pooling for database
- Scale horizontally with multiple bot instances

## Contributing

### Code Style

- Follow PEP 8
- Use type hints
- Add docstrings to functions
- Write descriptive commit messages
- Test before committing

### Adding New Features

1. Create feature branch
2. Implement with tests
3. Update documentation
4. Submit pull request

## License

Proprietary - Hero's Journey Internal Use

## Support

For issues, questions, or feature requests:
- Check logs first
- Review [DEPLOYMENT.md](DEPLOYMENT.md)
- Contact development team

---

**Version:** 1.0.0
**Last Updated:** 2025
**Python:** 3.11+
**Dependencies:** See [requirements.txt](requirements.txt)
