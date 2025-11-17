# 🌊 DigitalOcean VPS Setup для Hero's Journey Slack Bot

## 📋 Что нужно перед началом:

- [ ] Аккаунт на DigitalOcean
- [ ] VPN конфигурация (.ovpn файл) для доступа к PostgreSQL
- [ ] GitHub репозиторий с этим проектом
- [ ] API ключи (OpenAI, Slack)

---

## 🚀 Часть 1: Создание VPS на DigitalOcean

### Шаг 1: Создать Droplet

1. Зайди на https://cloud.digitalocean.com
2. Нажми **"Create"** → **"Droplets"**
3. Выбери параметры:

```
Choose Region: Frankfurt или Amsterdam (ближе к Казахстану)
Choose an image: Ubuntu 22.04 LTS x64
Choose Size: Basic - $6/mo (1GB RAM, 1 CPU, 25GB SSD)
Choose Authentication: SSH keys (рекомендую) или Password
Hostname: hj-slack-bot
```

4. Нажми **"Create Droplet"**
5. Запиши IP адрес (например: `143.198.123.45`)

### Шаг 2: Первое подключение

```bash
# Подключись к серверу
ssh root@143.198.123.45

# Обнови систему
apt update && apt upgrade -y
```

---

## 🔐 Часть 2: Настройка сервера

### Шаг 3: Создание пользователя

```bash
# Создай пользователя для приложения
adduser slackbot
# Введи пароль (запомни его!)

# Добавь в sudo группу
usermod -aG sudo slackbot

# Переключись на нового пользователя
su - slackbot
```

### Шаг 4: Установка зависимостей

```bash
# Python 3.11 и pip
sudo apt install python3.11 python3.11-venv python3-pip git -y

# Nginx (веб-сервер)
sudo apt install nginx -y

# OpenVPN (для подключения к БД)
sudo apt install openvpn -y
```

### Шаг 5: Настройка VPN

```bash
# Загрузи VPN конфигурацию на сервер
# На твоем компьютере:
scp your-vpn-config.ovpn slackbot@143.198.123.45:~/vpn.conf

# На сервере:
sudo mv ~/vpn.conf /etc/openvpn/client.conf

# Запусти VPN
sudo systemctl start openvpn@client
sudo systemctl enable openvpn@client

# Проверь что VPN работает
sudo systemctl status openvpn@client

# Проверь подключение к БД
ping your-database-host.com
```

---

## 📦 Часть 3: Деплой приложения

### Шаг 6: Клонирование репозитория

```bash
cd ~
git clone https://github.com/YOUR-USERNAME/select_bot_service.git
cd select_bot_service
```

### Шаг 7: Настройка Python окружения

```bash
# Создай виртуальное окружение
python3.11 -m venv venv

# Активируй его
source venv/bin/activate

# Установи зависимости
pip install -r requirements.txt
```

### Шаг 8: Создание .env файла

```bash
nano .env
```

Добавь следующие переменные:

```env
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Slack
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...

# Database (через VPN)
DB_HOST=your-db-host.com
DB_PORT=5432
DB_NAME=HJ_dwh
DB_USER=your-user
DB_PASSWORD=your-password

# AI Settings
AI_PROVIDER=openai
AI_MODEL=gpt-4o
```

Сохрани: `Ctrl+X` → `Y` → `Enter`

### Шаг 9: Тестовый запуск

```bash
# Запусти бота для проверки
python app.py

# Если все OK, увидишь:
# * Running on http://127.0.0.1:3000
# Schema loaded successfully: 8 tables

# Останови: Ctrl+C
```

---

## ⚙️ Часть 4: Автозапуск через systemd

### Шаг 10: Создание systemd service

```bash

```

Вставь:

```ini
[Unit]
Description=Hero's Journey Slack Bot
After=network.target openvpn@client.service
Requires=openvpn@client.service

[Service]
Type=notify
User=slackbot
WorkingDirectory=/home/slackbot/hj-mcp-server
Environment="PATH=/home/slackbot/hj-mcp-server/venv/bin"
ExecStart=/home/slackbot/hj-mcp-server/venv/bin/gunicorn app:app --bind 0.0.0.0:3000 --workers 2 --timeout 120
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохрани и запусти:

```bash
# Перезагрузи systemd
sudo systemctl daemon-reload

# Запусти сервис
sudo systemctl start slackbot

# Включи автозапуск при перезагрузке
sudo systemctl enable slackbot

# Проверь статус
sudo systemctl status slackbot
```

---

## 🌐 Часть 5: Настройка Nginx

### Шаг 11: Конфигурация Nginx

```bash
sudo nano /etc/nginx/sites-available/slackbot
```

Вставь:

```nginx
server {
    listen 80;
    server_name 207.154.243.144;  # Замени на свой IP или домен

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

Активируй конфигурацию:

```bash
# Создай симлинк
sudo ln -s /etc/nginx/sites-available/slackbot /etc/nginx/sites-enabled/

# Удали дефолтный конфиг
sudo rm /etc/nginx/sites-enabled/default

# Проверь конфигурацию
sudo nginx -t

# Перезапусти Nginx
sudo systemctl restart nginx
```

---

## 🔐 Часть 6: SSL сертификат (опционально, но рекомендую)

### Шаг 12: Установка Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx -y

# Если у тебя есть домен:
sudo certbot --nginx -d your-domain.com

# Следуй инструкциям
# Certbot автоматически настроит HTTPS
```

---

## 🤖 Часть 7: Автодеплой через GitHub Actions

### Шаг 13: Настройка SSH ключа

На сервере:

```bash
# Создай SSH ключ для деплоя
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_deploy

# Добавь публичный ключ в authorized_keys
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys

# Выведи приватный ключ (скопируй его)
cat ~/.ssh/github_deploy
```

### Шаг 14: Добавление секретов в GitHub

1. Перейди в свой репозиторий на GitHub
2. **Settings** → **Secrets and variables** → **Actions**
3. Нажми **"New repository secret"**
4. Добавь 3 секрета:

```
Название: VPS_HOST
Значение: 143.198.123.45  (твой IP)

Название: VPS_USER
Значение: slackbot

Название: VPS_SSH_KEY
Значение: (вставь содержимое ~/.ssh/github_deploy - приватный ключ)
```

### Шаг 15: Проверка автодеплоя

```bash
# На своем компьютере:
git add .
git commit -m "test auto-deploy"
git push origin main

# Зайди на GitHub → Actions
# Увидишь процесс деплоя
# Через ~1 минуту изменения будут на сервере!
```

---

## 🧪 Часть 8: Тестирование

### Шаг 16: Проверь что все работает

```bash
# Health check
curl http://143.198.123.45/health

# Должен вернуть:
# {"status":"healthy",...}

# Проверь логи
sudo journalctl -u slackbot -f
```

### Шаг 17: Обнови Slack Event URL

В Slack App Settings:

```
Event Subscriptions → Request URL:
http://143.198.123.45/slack/events

(или https://your-domain.com/slack/events если настроил SSL)
```

---

## 📊 Мониторинг и управление

### Полезные команды:

```bash
# Посмотреть логи
sudo journalctl -u slackbot -f

# Перезапустить бота
sudo systemctl restart slackbot

# Статус бота
sudo systemctl status slackbot

# Статус VPN
sudo systemctl status openvpn@client

# Статус Nginx
sudo systemctl status nginx

# Обновить код вручную
cd ~/select_bot_service
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart slackbot
```

---

## 🔥 Firewall (опционально, но рекомендую)

```bash
# Включи UFW
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Проверь статус
sudo ufw status
```

---

## 💰 Стоимость

| Компонент | Цена |
|-----------|------|
| DigitalOcean Droplet (1GB) | $6/mo |
| SSL сертификат | Бесплатно (Let's Encrypt) |
| **Итого** | **$6/mo** |

---

## ✅ Чеклист готовности к продакшену

- [ ] VPS создан на DigitalOcean
- [ ] VPN настроен и работает
- [ ] Приложение запущено через systemd
- [ ] Nginx настроен
- [ ] SSL сертификат установлен (опционально)
- [ ] GitHub Actions автодеплой работает
- [ ] Slack Event URL обновлен
- [ ] Health check возвращает OK
- [ ] Логи показывают успешную работу

---

## 🆘 Troubleshooting

**Проблема:** Бот не подключается к БД
```bash
# Проверь VPN
sudo systemctl status openvpn@client
ping your-database-host.com
```

**Проблема:** Приложение не запускается
```bash
# Проверь логи
sudo journalctl -u slackbot -n 50 --no-pager
```

**Проблема:** Slack не получает события
```bash
# Проверь Nginx
sudo nginx -t
sudo systemctl status nginx

# Проверь firewall
sudo ufw status
```

**Проблема:** Автодеплой не работает
```bash
# Проверь SSH ключ на сервере
cat ~/.ssh/authorized_keys | grep github

# Проверь что slackbot может делать sudo без пароля:
sudo visudo
# Добавь: slackbot ALL=(ALL) NOPASSWD: /bin/systemctl restart slackbot
```

---

## 🎉 Готово!

Теперь при каждом `git push` изменения автоматически деплоятся на сервер!

**Проверь:**
1. Измени что-то в коде
2. `git commit -m "test"`
3. `git push origin main`
4. Через минуту изменения будут на продакшене!
