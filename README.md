# 📹 Camera Stream Quality Monitor — PoC

Proof of Concept для мониторинга качества видеопотоков IP-камер с использованием Prometheus Blackbox Exporter, кастомного RTSP-экспортёра, VictoriaMetrics и Grafana.

---

## 🏗 Архитектура

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            Docker Network                                │
│                                                                          │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│   │ mock-camera │    │ mock-camera │    │ mock-camera │                  │
│   │      1      │    │      2      │    │      3      │                  │
│   │  :8554 RTSP │    │  :8554 RTSP │    │  :8554 RTSP │                  │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                  │
│          │                  │                  │                         │
│          └──────────────────┼──────────────────┘                         │
│                             │                                            │
│              ┌──────────────┴──────────────┐                             │
│              │                             │                             │
│    ┌─────────▼──────────┐   ┌─────────────▼──────────┐                   │
│    │   rtsp-exporter    │   │   blackbox-exporter    │                   │
│    │ Кастомный Python   │   │ Prometheus Blackbox    │                   │
│    │ RTSP OPTIONS probe │   │ ICMP + TCP проверки    │                   │
│    │       :9115        │   │       :9116 (→9115)    │                   │
│    └─────────┬──────────┘   └─────────────┬──────────┘                   │
│              │                             │                             │
│              └──────────────┬──────────────┘                             │
│                             │                                            │
│                  ┌──────────▼──────────┐                                 │
│                  │  VictoriaMetrics    │                                 │
│                  │   Сбор метрик       │                                 │
│                  │  :9090 (→8428)      │                                 │
│                  └──────────┬──────────┘                                 │
│                             │                                            │
│                  ┌──────────▼──────────┐                                 │
│                  │       Grafana       │                                 │
│                  │    Визуализация     │                                 │
│                  │       :3000         │                                 │
│                  └─────────────────────┘                                 │
│                                                                          │
│   ┌──────────────────────┐   ┌──────────────────────┐                    │
│   │     config-api       │   │      config-ui       │                    │
│   │  FastAPI CRUD API    │◄──│  React + Nginx SPA   │                    │
│   │       :8000          │   │       :8080          │                    │
│   └──────────┬───────────┘   └──────────────────────┘                    │
│              │ exporter_config.yml (bind mount)                          │
│              ▼                                                           │
│        rtsp-exporter                                                     │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🔢 Собираемые метрики

### Кастомный RTSP-экспортёр

| Метрика | Тип | Описание |
|---|---|---|
| `camera_up` | gauge | Доступность камеры: 1 = онлайн, 0 = офлайн |
| `camera_rtsp_latency_ms` | gauge | Задержка RTSP-подключения (мс) |
| `camera_rtp_packet_loss_ratio` | gauge | Доля потерянных RTP-пакетов (0..1) |
| `camera_rtp_jitter_ms` | gauge | Джиттер RTP (мс) |
| `camera_stream_bitrate_kbps` | gauge | Битрейт видеопотока (кбит/с) |
| `camera_last_scrape_timestamp` | gauge | Unix-время последнего опроса |

### Blackbox Exporter

| Метрика | Тип | Описание |
|---|---|---|
| `probe_success` | gauge | TCP/ICMP доступность (1 = успех) |
| `probe_duration_seconds` | gauge | Время выполнения пробы |

Все метрики RTSP-экспортёра содержат лейблы: `camera`, `host`, `port`, `location`, `building`.

---

## 🚀 Быстрый старт

### Предварительные требования

- Docker Engine ≥ 20.10
- Docker Compose ≥ 2.0
- Свободные порты: `3000`, `8000`, `8080`, `8554–8556`, `9090`, `9115`, `9116`

### Запуск

```bash
# 1. Клонировать репозиторий
git clone https://git.miem.hse.ru/nvpliasov/1-3-blackbox-exporter.git
cd 1-3-blackbox-exporter

# 2. Запустить весь стек
docker compose up --build -d

# 3. Проверить статус контейнеров
docker compose ps
```

### Доступ к сервисам

| Сервис | URL | Логин / Пароль |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| VictoriaMetrics | http://localhost:9090 | — |
| RTSP Exporter | http://localhost:9115/metrics | — |
| Blackbox Exporter | http://localhost:9116/metrics | — |
| Config UI | http://localhost:8080 | — |
| Config API | http://localhost:8000/docs | — |

### Проверка метрик вручную

```bash
# Посмотреть метрики RTSP-экспортёра
curl http://localhost:9115/metrics

# Проверить TCP-доступность камеры через Blackbox
curl "http://localhost:9116/probe?module=tcp_rtsp&target=localhost:8554"

# ICMP-проверка через Blackbox
curl "http://localhost:9116/probe?module=icmp_check&target=localhost"

# Запросить метрики через VictoriaMetrics API (совместим с Prometheus API)
curl "http://localhost:9090/api/v1/query?query=camera_up"

# Получить список камер через Config API
curl http://localhost:8000/cameras
```

---

## 📁 Структура проекта

```
.
├── docker-compose.yml          # Оркестрация всего стека
├── Dockerfile.exporter         # Образ кастомного RTSP-экспортёра
├── Dockerfile.mock             # Образ mock-камеры
│
├── rtsp_exporter.py            # Кастомный Prometheus-экспортёр (RTSP OPTIONS probe)
├── mock_rtsp_server.py         # Mock RTSP-сервер (имитирует IP-камеры)
├── exporter_config.yml         # Список камер для мониторинга (редактируется через Config UI)
├── requirements.txt            # Python-зависимости экспортёра (устанавливаются при сборке)
│
├── blackbox.yml                # Конфигурация Blackbox Exporter (ICMP, TCP, HTTP, ONVIF)
├── prometheus.yml              # Конфигурация scrape для VictoriaMetrics
│
├── config_api/                 # FastAPI бэкенд для управления камерами
│   ├── main.py                 # CRUD API: GET/POST/PUT/DELETE /cameras
│   ├── requirements.txt        # Зависимости: fastapi, uvicorn, pyyaml, pydantic
│   └── Dockerfile              # python:3.12-slim образ
│
├── config_ui/                  # React + Vite фронтенд
│   ├── src/
│   │   ├── App.jsx             # Главный компонент (список + форма)
│   │   ├── api.js              # HTTP-клиент для Config API
│   │   └── components/
│   │       ├── CameraTable.jsx # Таблица камер с кнопками редактирования/удаления
│   │       └── CameraForm.jsx  # Форма добавления/редактирования камеры
│   ├── nginx.conf              # Nginx: раздача SPA + проксирование /cameras → config-api
│   └── Dockerfile              # Многоэтапная сборка: node:20 → nginx:1.27
│
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yml  # Автоматическое подключение VictoriaMetrics
    │   └── dashboards/
    │       └── dashboards.yml  # Автозагрузка дашбордов
    └── dashboards/
        └── camera_monitoring.json  # Основной дашборд Grafana
```

---

## ⚙️ Конфигурация

### Mock-камеры (параметры по умолчанию)

| Камера | Порт (хост) | Задержка | Потери пакетов | Битрейт |
|---|---|---|---|---|
| camera-1 | 8554 | 45 мс | 2% | 2048 кбит/с |
| camera-2 | 8555 | 120 мс | 8% | 2048 кбит/с |
| camera-3 | 8556 | 20 мс | 0% | 2048 кбит/с |

Параметры задаются через переменные окружения в [`docker-compose.yml`](docker-compose.yml):

```yaml
environment:
  CAMERA_ID: "camera-1"
  LATENCY_MS: "200"      # задержка ответа в мс
  PACKET_LOSS: "0.10"    # 10% потерь пакетов
  BITRATE_KBPS: "4096"   # битрейт 4 Мбит/с
  PORT: "8554"           # порт прослушивания внутри контейнера
```

### Добавить реальную камеру

Через веб-интерфейс: откройте http://localhost:8080 и нажмите **«+ Добавить камеру»**.

Или напрямую через API:

```bash
curl -X POST http://localhost:8000/cameras \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-camera",
    "host": "192.168.1.100",
    "port": 554,
    "path": "/stream1",
    "labels": {"location": "office", "building": "main"}
  }'
```

После сохранения config-api сразу шлёт экспортёру `POST /reload` — поллер просыпается и перечитывает конфиг без ожидания. Цикл опроса камер — раз в **1 сек** (`SCRAPE_INTERVAL`). Если править `exporter_config.yml` вручную, вызовите `curl -X POST http://localhost:9115/reload` или дождитесь следующего цикла (~1 сек).

### Config API — эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| `GET` | `/cameras` | Список всех камер |
| `GET` | `/cameras/{name}` | Получить камеру по имени |
| `POST` | `/cameras` | Добавить новую камеру |
| `PUT` | `/cameras/{name}` | Обновить камеру |
| `DELETE` | `/cameras/{name}` | Удалить камеру |
| `GET` | `/health` | Проверка работоспособности |
| `GET` | `/docs` | Swagger UI |

### Модули Blackbox Exporter

| Модуль | Протокол | Таймаут | Назначение |
|---|---|---|---|
| `icmp_check` | ICMP | 5 с | Ping-доступность камеры |
| `tcp_rtsp` | TCP | 5 с | Проверка RTSP-порта (554 / 8554) |
| `tcp_onvif` | TCP | 5 с | Проверка ONVIF-порта (80 / 8080) |
| `http_2xx` | HTTP/HTTPS | 10 с | Проверка веб-интерфейса камеры / NVR |

---

## 💻 Локальная разработка (без Docker)

Удобно для разработки и отладки `config-api` и `config-ui`.

### Предварительные требования

- Python ≥ 3.9
- Node.js ≥ 20 (`brew install node`)

### Бэкенд (FastAPI)

```bash
# Создать виртуальное окружение и установить зависимости
cd config_api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Запустить с указанием пути к конфигу камер
CONFIG_PATH="../exporter_config.yml" .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API будет доступен на http://localhost:8000, Swagger UI — на http://localhost:8000/docs.

### Фронтенд (React + Vite)

```bash
# В отдельном терминале
cd config_ui
npm install
npm run dev:local
```

UI будет доступен на http://localhost:5173. Vite автоматически проксирует запросы `/cameras` на `http://localhost:8000` (используется [`vite.config.local.js`](config_ui/vite.config.local.js)).

---

## 🛑 Остановка

```bash
docker compose down           # остановить (данные сохранятся)
docker compose down -v        # остановить и удалить тома (данные VictoriaMetrics/Grafana)
```

---

## 🔭 Как работает RTSP-экспортёр

1. Читает список камер из [`exporter_config.yml`](exporter_config.yml)
2. Параллельно опрашивает все камеры в отдельных потоках
3. **Mock-камеры** (`vendor: mock`): `RTSP OPTIONS` без авторизации
4. **Hikvision** (`vendor: hikvision`): `RTSP DESCRIBE` на `/Streaming/Channels/101` (или `102` для субпотока) с **Digest-авторизацией**
5. Измеряет RTT как `camera_rtsp_latency_ms`
6. **Hikvision**: `bitrate` — из ISAPI (`constantBitRate`) или SDP (`b=AS`); `loss`/`jitter` — только у mock (реальная камера их по RTSP не отдаёт)
7. Экспонирует метрики на `:9115/metrics`

### Подключение Hikvision

Пример конфига: [`exporter_config.hikvision.example.yml`](exporter_config.hikvision.example.yml)

```yaml
cameras:
  - name: hikvision-1
    vendor: hikvision
    host: 192.168.1.64
    port: 554
    channel: 101          # основной поток; 102 — субпоток
    username: admin
    password: secret
```

Через Config UI выберите тип **Hikvision**, укажите IP, логин и пароль. Путь `/Streaming/Channels/101` подставится автоматически.

При сборке Docker-образа [`Dockerfile.exporter`](Dockerfile.exporter) устанавливает зависимости из [`requirements.txt`](requirements.txt) командой `pip install -r requirements.txt`.

---

## 🖥 Config UI — веб-интерфейс управления камерами

Доступен по адресу http://localhost:8080.

Возможности:
- **Просмотр** списка всех камер с лейблами
- **Добавление** новой камеры через форму
- **Редактирование** параметров существующей камеры
- **Удаление** камеры из конфигурации

Изменения сохраняются в [`exporter_config.yml`](exporter_config.yml) через [`config-api`](config_api/main.py); экспортёр подхватывает их сразу через `POST /reload`.

Swagger UI для прямой работы с API: http://localhost:8000/docs

---

## 📊 Описание дашборда Grafana

Дашборд **Camera Monitoring — PoC** содержит:

- **Stat-панели**: количество камер онлайн/офлайн, средняя задержка, макс. потери
- **Таблица**: сводное состояние всех камер с лейблами `location` и `building`
- **Графики**: задержка, потери пакетов, джиттер, битрейт — в динамике
- **Blackbox-панели**: TCP-доступность и время ответа RTSP-порта

---

## 🧩 Версии компонентов

| Компонент | Версия |
|---|---|
| VictoriaMetrics | `v1.101.0` |
| Grafana | `10.4.0` |
| Blackbox Exporter | `v0.25.0` |
| Python (экспортёр / API) | `3.12-slim` |
| Node.js (сборка UI) | `20-alpine` |
| Nginx (раздача UI) | `1.27-alpine` |
| PyYAML | `≥ 6.0` |
| FastAPI | `≥ 0.111.0` |
| React | `18.3.x` |
| Vite | `5.4.x` |

---

## 📈 Перспективы развития

- Поддержка ONVIF для автообнаружения камер
- Анализ качества видео через FFmpeg (VMAF, PSNR)
- Интеграция с системами оповещения (Alertmanager → Telegram/Email)
- Экспорт метрик из реальных RTP-сессий через `ffprobe`
- Поддержка HTTPS/RTSPS для зашифрованных потоков
- Авторизация в Config UI
- Деплой в Kubernetes

---

## 👥 Команда

- Плясов Николай
- Чашкин Федор

Учебный проект, МИЭМ НИУ ВШЭ, 2026.
