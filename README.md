# DataStore Monitor

Мониторинг систем хранения данных (СХД/DataStore) из Zabbix в NetBox.

## Описание

Сервис автоматически синхронизирует информацию о СХД из Zabbix в NetBox:
- Создаёт устройства в NetBox для новых СХД
- Обновляет информацию при изменениях
- Отслеживает пропавшие устройства
- Отправляет уведомления в Telegram

## Структура проекта

```
prods-z-n-datastore/
├── app/
│   ├── __init__.py
│   ├── config.py           # Конфигурация
│   ├── monitor.py          # Главная логика мониторинга
│   ├── zabbix_client.py    # Клиент Zabbix API
│   ├── netbox_client.py    # Клиент NetBox API
│   ├── netbox_sync.py      # Синхронизация с NetBox
│   ├── cache.py            # Redis кэш
│   ├── notifications.py    # Telegram уведомления
│   └── helpers.py          # Вспомогательные функции
├── check_services.py       # Проверка подключения к сервисам
├── init_netbox.py          # Инициализация NetBox (custom fields)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Быстрый старт

### 1. Настройка окружения

```bash
cp .env.example .env
# Отредактируйте .env, укажите реальные значения
```

### 2. Запуск с Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Проверка подключения к сервисам
docker exec datastore-monitor python check_services.py

# Инициализация NetBox (один раз)
docker exec datastore-monitor python init_netbox.py

# Запуск мониторинга вручную
docker exec datastore-monitor python -m app.monitor
```

### 3. Локальный запуск (для разработки)

```bash
# Установка зависимостей
pip install -r requirements.txt

# Проверка сервисов
python check_services.py

# Инициализация NetBox
python init_netbox.py

# Запуск мониторинга
python -m app.monitor
```

## Конфигурация

### Переменные окружения (.env)

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ZABBIX_URL` | URL Zabbix сервера | `https://zabbix-cloud.ttc.kz/` |
| `ZABBIX_USER` | Пользователь Zabbix | - |
| `ZABBIX_PASSWORD` | Пароль Zabbix | - |
| `ZABBIX_VERIFY_SSL` | Проверка SSL сертификата | `false` |
| `NETBOX_URL` | URL NetBox сервера | `https://web-netbox.t-cloud.kz/` |
| `NETBOX_TOKEN` | API токен NetBox | - |
| `REDIS_HOST` | Хост Redis | `redis` |
| `REDIS_PORT` | Порт Redis | `6380` |
| `REDIS_DB` | База данных Redis | `2` |
| `REDIS_TTL` | TTL записей Redis (секунды) | `604800` (7 дней) |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений | - |
| `DRY_RUN` | Режим без изменений | `false` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

### Группы хостов Zabbix

Мониторинг работает с группами:
- `DataStore/DataCenter/Almaty`
- `DataStore/DataCenter/Astana-Kabanbay`
- `DataStore/DataCenter/Astana-Konaeva`
- `DataStore/DataCenter/Atyrau`
- `DataStore/DataCenter/Karagandy`

### Маппинг DC → Site

| Zabbix DC | NetBox Site |
|-----------|-------------|
| Almaty | DC Almaty |
| Astana-Kabanbay | DC Kabanbay-Batyr28 |
| Astana-Konaeva | DC Konaeva10 |
| Atyrau | DC Atyrau |
| Karagandy | DC Karaganda |

## Custom Fields в NetBox

Создаются автоматически при запуске `init_netbox.py`:

| Поле | Описание |
|------|----------|
| `zabbix_hostid` | ID хоста в Zabbix (ключ связи) |
| `last_sync` | Время последней синхронизации |
| `os_version` | Версия прошивки СХД |
| `serial_a` | Серийный номер контроллера A |
| `serial_b` | Серийный номер контроллера B |
| `hardware_info` | Информация об оборудовании |

## Алгоритм работы

1. **Получение данных** - загрузка хостов из Zabbix групп DataStore/*
2. **Обработка каждого хоста:**
   - Если нет в NetBox → создание устройства
   - Если есть → сравнение полей по хэшу и обновление при изменениях
3. **Проверка пропавших** - хосты есть в Redis, но нет в Zabbix
4. **Уведомления** - отправка в Telegram о всех событиях

## Уведомления Telegram

- **Новый датастор** - создано устройство в NetBox
- **Изменения** - обновлены поля устройства
- **Не отвечает** - датастор пропал из Zabbix
- **Вернулся** - датастор снова появился
- **Дневной отчёт** - статистика за день

### Интервалы уведомлений о пропаже

- Сразу при обнаружении
- Через 1 час
- Через 6 часов
- Через 24 часа
- Далее каждые 24 часа

## Cron расписание

По умолчанию мониторинг запускается каждые 30 минут (настраивается в docker-compose.yml).

## Логирование

Логи записываются в:
- Консоль (stdout)
- Файл `logs/datastore_monitor.log`

## Разработка

### Режим DRY_RUN

Для тестирования без внесения изменений:

```bash
DRY_RUN=true python -m app.monitor
```

### Структура Redis

```
datastore:{hostid}:hash         # SHA256 состояния
datastore:{hostid}:last_seen    # ISO timestamp
datastore:{hostid}:missing_since # ISO timestamp (если пропал)
datastore:{hostid}:last_notified # ISO timestamp
datastore:{hostid}:netbox_id    # ID в NetBox
datastore:{hostid}:data         # JSON данных
```

## Важные правила

**Что делает:**
- Автоматически создаёт устройства в NetBox
- Автоматически создаёт manufacturer и device_type
- Обновляет поля существующих устройств
- Уведомляет в Telegram о всех событиях
- Отслеживает пропавшие устройства

**Что НЕ делает:**
- НЕ удаляет устройства из NetBox
- НЕ меняет статус на decommissioned/offline
- НЕ удаляет IP адреса
