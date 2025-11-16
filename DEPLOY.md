# 🚀 Деплой Hero's Journey Slack Bot

## ⚠️ ВАЖНО: Проблема с VPN

**PostgreSQL требует VPN для подключения!**

У вас есть 3 варианта:

### Вариант 1: Whitelist IP (РЕКОМЕНДУЮ)
1. Свяжитесь с DBA
2. Попросите добавить IP Render сервера в whitelist PostgreSQL
3. Это позволит подключаться без VPN

### Вариант 2: Публичная реплика БД
1. Создать read-only реплику без VPN
2. Использовать её для Slack бота
3. Основная БД остается защищенной

### Вариант 3: VPS с VPN (ЕСЛИ WHITELIST НЕВОЗМОЖЕН)
Используйте DigitalOcean/Hetzner вместо Render (инструкции ниже)

---

## 📦 Вариант A: Деплой на Render (если БД доступна)

### Шаг 1: Подготовка GitHub репозитория

```bash
# 1. Убедитесь что все изменения закоммичены
git status

# 2. Добавьте файлы для деплоя
git add Procfile render.yaml requirements.txt
git commit -m "Add Render deployment files"
git push origin main
```

### Шаг 2: Создание проекта на Render

1. Зайдите на https://render.com
2. Нажмите **"New +"** → **"Web Service"**
3. Подключите свой GitHub репозиторий
4. Render автоматически найдет `render.yaml`

### Шаг 3: Настройка Environment Variables

В Render Dashboard добавьте переменные окружения:

```
OPENAI_API_KEY=sk-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
DB_HOST=your-db-host.com
DB_PORT=5432
DB_NAME=HJ_dwh
DB_USER=your-user
DB_PASSWORD=your-password
AI_PROVIDER=openai
AI_MODEL=gpt-4o
```

### Шаг 4: Деплой

- Render автоматически задеплоит при push в `main`
- Или нажмите **"Manual Deploy"** в Dashboard

### Шаг 5: Обновите Slack Event URL

```
https://your-app-name.onrender.com/slack/events
```

---

## 🖥️ Вариант B: Деплой на VPS с VPN

### Рекомендуемые провайдеры:
- **DigitalOcean** ($6/mo) - самый простой
- **Hetzner** ($4/mo) - дешевле
- **AWS EC2** (от $3.5/mo) - для энтерпрайза

### Шаг 1: Создание VPS

```bash
# 1. Создайте Droplet на DigitalOcean
# OS: Ubuntu 22.04 LTS
# Plan: Basic - $6/mo

# 2. SSH в сервер
ssh root@your-server-ip
```

### Шаг 2: Установка зависимостей

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Python 3.11
apt install python3.11 python3.11-venv python3-pip -y

# Установка Nginx
apt install nginx -y

# Установка VPN клиента (например, OpenVPN)
apt install openvpn -y

# Загрузите ваш .ovpn файл
scp your-vpn-config.ovpn root@your-server-ip:/etc/openvpn/client.conf

# Запустите VPN
systemctl start openvpn@client
systemctl enable openvpn@client
```

### Шаг 3: Клонирование репозитория

```bash
# Создайте пользователя для приложения
adduser slackbot
usermod -aG sudo slackbot
su - slackbot

# Клонируйте репозиторий
git clone https://github.com/your-username/select_bot_service.git
cd select_bot_service

# Создайте виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt
```

### Шаг 4: Настройка .env

```bash
nano .env
```

Добавьте:
```env
OPENAI_API_KEY=sk-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
DB_HOST=localhost  # через VPN
DB_PORT=5432
DB_NAME=HJ_dwh
DB_USER=your-user
DB_PASSWORD=your-password
AI_PROVIDER=openai
AI_MODEL=gpt-4o
```

### Шаг 5: Создание systemd service

```bash
sudo nano /etc/systemd/system/slackbot.service
```

```ini
[Unit]
Description=Hero's Journey Slack Bot
After=network.target openvpn@client.service
Requires=openvpn@client.service

[Service]
Type=notify
User=slackbot
WorkingDirectory=/home/slackbot/select_bot_service
Environment="PATH=/home/slackbot/select_bot_service/venv/bin"
ExecStart=/home/slackbot/select_bot_service/venv/bin/gunicorn app:app --bind 0.0.0.0:3000 --workers 2 --timeout 120
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Запустите сервис
sudo systemctl daemon-reload
sudo systemctl start slackbot
sudo systemctl enable slackbot

# Проверьте статус
sudo systemctl status slackbot
```

### Шаг 6: Настройка Nginx

```bash
sudo nano /etc/nginx/sites-available/slackbot
```

```nginx
server {
    listen 80;
    server_name your-domain.com;  # или IP адрес

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Активируйте конфигурацию
sudo ln -s /etc/nginx/sites-available/slackbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Шаг 7: SSL с Let's Encrypt (опционально)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### Шаг 8: Автоматический деплой через GitHub Actions

Создайте `.github/workflows/deploy.yml`:

```yaml
name: Deploy to VPS

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.VPS_HOST }}
          username: slackbot
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ~/select_bot_service
            git pull origin main
            source venv/bin/activate
            pip install -r requirements.txt
            sudo systemctl restart slackbot
```

Добавьте секреты в GitHub:
- `VPS_HOST` - IP вашего сервера
- `VPS_SSH_KEY` - приватный SSH ключ

---

## 🔄 Автоматическое обновление

### Render:
✅ Автоматически деплоится при `git push`

### VPS:
✅ GitHub Actions автоматически обновляет при `git push`

---

## 🧪 Тестирование деплоя

```bash
# Проверьте health endpoint
curl https://your-url.com/health

# Должен вернуть:
# {"status": "healthy", ...}
```

---

## 📊 Мониторинг

### Render:
- Встроенные логи в Dashboard
- Метрики CPU/RAM

### VPS:
```bash
# Логи приложения
sudo journalctl -u slackbot -f

# Статус сервиса
sudo systemctl status slackbot
```

---

## 💰 Стоимость

| Провайдер | План | Цена | VPN |
|-----------|------|------|-----|
| **Render** | Free | $0/mo | ❌ Нет |
| **Render** | Starter | $7/mo | ❌ Нет |
| **DigitalOcean** | Basic | $6/mo | ✅ Да |
| **Hetzner** | CX11 | €4/mo | ✅ Да |

---

## ❓ FAQ

**Q: Render не подключается к БД через VPN**
A: Свяжитесь с DBA для whitelist IP или используйте VPS

**Q: Как обновить код в продакшене?**
A: Просто `git push` - автодеплой настроен

**Q: Как посмотреть логи?**
A: Render Dashboard → Logs или `journalctl -u slackbot -f` на VPS

**Q: Как откатить деплой?**
A: Render Dashboard → Rollback или `git revert` + push
