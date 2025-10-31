# Production Deployment Guide

This guide covers deploying Hero's Journey SQL Assistant to production.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Environment Setup](#environment-setup)
- [Deployment Options](#deployment-options)
  - [Docker Deployment](#docker-deployment)
  - [Systemd Deployment](#systemd-deployment)
  - [Manual Deployment](#manual-deployment)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- Python 3.11 or higher
- PostgreSQL 12+ (for database)
- 2GB RAM minimum (4GB recommended)
- 10GB disk space

### Required Services
- OpenAI API access (for SQL generation)
- Slack workspace with bot configured
- PostgreSQL database with Hero's Journey data

---

## Environment Setup

### 1. Create Environment File

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```bash
# OpenAI
OPENAI_API_KEY=sk-proj-your-actual-key-here
OPENAI_MODEL=gpt-4o

# Slack
SLACK_BOT_TOKEN=xoxb-your-actual-token
SLACK_SIGNING_SECRET=your-actual-secret

# Database
DB_HOST=your-database-host.rds.amazonaws.com
DB_NAME=HJ_dwh
DB_USER=project_manager_role
DB_PASSWORD=your-actual-password
DB_PORT=5432

# Application
FLASK_PORT=3000
FLASK_DEBUG=False
LOG_LEVEL=INFO
```

### 2. Security Checklist

- ✅ Never commit `.env` file to git
- ✅ Use strong database passwords
- ✅ Rotate API keys regularly
- ✅ Enable HTTPS for production
- ✅ Use firewall rules to restrict database access

---

## Deployment Options

### Docker Deployment (Recommended)

Docker provides the easiest and most consistent deployment.

#### Build and Run

```bash
cd deployment
docker-compose up -d
```

#### View Logs

```bash
docker-compose logs -f slack-bot
```

#### Stop Services

```bash
docker-compose down
```

#### Update and Restart

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

### Systemd Deployment (Linux Servers)

For running directly on Linux servers without Docker.

#### 1. Setup Application

```bash
# Create application directory
sudo mkdir -p /opt/select_bot_service
sudo cp -r . /opt/select_bot_service/
cd /opt/select_bot_service

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your values

# Set permissions
sudo chown -R www-data:www-data /opt/select_bot_service
sudo chmod 755 /opt/select_bot_service
```

#### 2. Install Systemd Services

```bash
# Copy service files
sudo cp deployment/systemd/*.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable herojourney-slack-bot
sudo systemctl enable herojourney-mcp-server

# Start services
sudo systemctl start herojourney-slack-bot
sudo systemctl start herojourney-mcp-server
```

#### 3. Manage Services

```bash
# Check status
sudo systemctl status herojourney-slack-bot

# View logs
sudo journalctl -u herojourney-slack-bot -f

# Restart
sudo systemctl restart herojourney-slack-bot

# Stop
sudo systemctl stop herojourney-slack-bot
```

---

### Manual Deployment

For development or testing environments.

#### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values
```

#### 3. Run Services

**Slack Bot:**
```bash
python app.py
```

**MCP Server:**
```bash
python mcp_server.py
```

---

## Configuration

### Slack Bot Setup

1. **Create Slack App**: https://api.slack.com/apps
2. **Enable Events**:
   - Subscribe to `message.channels` event
   - Set Request URL to `https://your-domain.com/slack/events`
3. **Set Permissions** (OAuth Scopes):
   - `chat:write`
   - `files:write`
   - `channels:history`
4. **Install to Workspace**

### MCP Server Setup

#### For Claude Desktop

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "herojourney-sql": {
      "command": "python",
      "args": ["/path/to/select_bot_service/mcp_server.py"],
      "env": {
        "OPENAI_API_KEY": "your-key",
        "DB_HOST": "your-host",
        "DB_NAME": "HJ_dwh",
        "DB_USER": "your-user",
        "DB_PASSWORD": "your-password"
      }
    }
  }
}
```

---

## Monitoring

### Health Check Endpoint

The Slack bot provides a health check endpoint:

```bash
curl http://localhost:3000/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": true,
  "schema_tables": 7
}
```

### Logging

#### Docker Logs
```bash
docker-compose logs -f slack-bot
```

#### Systemd Logs
```bash
sudo journalctl -u herojourney-slack-bot -f
```

#### Log Levels
Set via `LOG_LEVEL` environment variable:
- `DEBUG`: Detailed debugging information
- `INFO`: General information (default)
- `WARNING`: Warning messages
- `ERROR`: Error messages only

---

## Troubleshooting

### Database Connection Issues

**Symptom:** "Failed to connect to database"

**Solutions:**
1. Check database credentials in `.env`
2. Verify database host is accessible:
   ```bash
   psql -h $DB_HOST -U $DB_USER -d $DB_NAME
   ```
3. Check firewall rules
4. Verify PostgreSQL is running

### Slack Bot Not Responding

**Symptom:** Bot doesn't respond to messages

**Solutions:**
1. Check bot is running: `curl http://localhost:3000/health`
2. Verify Slack event subscription URL is correct
3. Check Slack bot has proper permissions
4. View logs for errors

### OpenAI API Errors

**Symptom:** "Error generating SQL"

**Solutions:**
1. Verify `OPENAI_API_KEY` is valid
2. Check API quota limits
3. Ensure model `gpt-4o` is available for your account

### Schema Loading Errors

**Symptom:** "Failed to load schema"

**Solutions:**
1. Verify `docs/` folder exists and contains YAML files
2. Check YAML syntax is valid
3. Ensure file permissions are correct

### MCP Server Issues

**Symptom:** MCP server not accessible

**Solutions:**
1. Check server is running
2. Verify environment variables are set
3. Check client configuration is correct
4. Review server logs for errors

---

## Performance Optimization

### Database
- Add indexes on frequently queried columns
- Use connection pooling for high traffic
- Monitor query performance

### Application
- Increase worker processes for higher load
- Use Redis for caching (future enhancement)
- Monitor memory usage

### Slack Integration
- Implement rate limiting
- Use message queues for high volume

---

## Security Best Practices

1. **Credentials**
   - Never commit `.env` files
   - Use secret management tools (AWS Secrets Manager, etc.)
   - Rotate credentials regularly

2. **Database**
   - Use read-only database user where possible
   - Implement SQL query validation
   - Monitor for suspicious queries

3. **Network**
   - Use HTTPS/TLS for all connections
   - Implement IP whitelisting
   - Use VPN for database access

4. **Application**
   - Keep dependencies updated
   - Run as non-root user
   - Implement request rate limiting

---

## Backup and Recovery

### Database Backups
```bash
pg_dump -h $DB_HOST -U $DB_USER $DB_NAME > backup.sql
```

### Application Backups
- Backup `.env` file securely
- Backup `docs/` schema documentation
- Keep configuration in version control

---

## Scaling

### Horizontal Scaling
- Run multiple Slack bot instances behind load balancer
- Use shared session storage (Redis)
- Implement message queue (RabbitMQ, SQS)

### Vertical Scaling
- Increase server resources (RAM, CPU)
- Optimize database queries
- Use caching strategies

---

## Support

For issues and questions:
- Check logs first
- Review this documentation
- Contact development team
