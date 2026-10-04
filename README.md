# ReleaseRadar

ReleaseRadar — это проект для отслеживания обновлений заданного ПО и отправки уведомлений об обнаруженных обновлениях

Поддерживаемые провайдеры:

- GitHub
- GitLab

Поддерживаемые источники уведомлений:

- Telegram (через бота)

# Установка

>[!warn] Важно! 
> Для установки потребуется сервер на Linux (требуется установленный Python (обычно уже установлен))

## Скачивание и подготовка

Для начала скачать репозиторий командой:

```Bash
git clone git@github.com:[ваш_путь]
```

После чего создать (если ещё нету) конфиг `config.yaml` и файл для секретов `.env`
В `config.yaml` должна быть такая структура:

```YAML
check_interval_seconds: 3600
software:
  - id: xray
    name: Xray-core
    provider: github
    repository: XTLS/Xray-core
    channel: prerelease
    current_version: test-version
    enabled: true
```

В файл `.env` необходимо вписать переменные `TELEGRAM_BOT_TOKEN` И `TELEGRAM_CHAT_ID`, где:

- `TELEGRAM_BOT_TOKEN` — токен бота Telegram
- `TELEGRAM_CHAT_ID` — ваш ID аккаунта (узнать можно с помощью бота `@userinfobot`)

И обязательно всё слитно через `=`!
Пример:

```Python
TELEGRAM_BOT_TOKEN=123456:abcd # Заменить на ваш токен правую часть
TELEGRAM_CHAT_ID=123456 # Заменить на ваш ID аккаунта
```

После чего в папке с скриптом выполнить команды:

```Bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install pip --upgrade
python3 -m pip install -r requirements.txt
```

## Создание сервиса

Выполнить команду:

```Bash
sudo nano /etc/systemd/system/releaseradar.service
```

Пример юнита:

```INI
[Unit]
Description=ReleaseRadar
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<user>
WorkingDirectory=/opt/releaseradar
ExecStart=/opt/releaseradar/.venv/bin/python /opt/releaseradar/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`WorkingDirectory` и `ExecStart` заменить на ваши пути!

Сохранить и выполнить команды:
```Bash
sudo systemctl daemon-reload
sudo systemctl enable --now releaseradar.service
```

Проверить заработал ли скрипт:

```Bash
systemctl status releaseradar.service
```

Смотреть логи так:

```Bash
journalctl -u releaseradar.service -f
```