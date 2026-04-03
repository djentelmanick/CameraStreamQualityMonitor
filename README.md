# 📹 Camera Stream Quality Monitor — PoC

Proof of Concept для мониторинга качества видеопотоков IP-камер с использованием Prometheus Blackbox Exporter, кастомного RTSP-экспортёра, VictoriaMetrics и Grafana.

---

## 🏗 Архитектура

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Docker Network                              │
│                                                                      │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
│   │ mock-camera │    │ mock-camera │    │ mock-camera │              │
│   │      1      │    │      2      │    │      3      │              │
│   │  :8554 RTSP │    │  :8554 RTSP │    │  :8554 RTSP │              │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘              │
│          │                  │                  │                     │
│          └──────────────────┼──────────────────┘                     │
│                             │                                        │
│              ┌──────────────┴──────────────┐                         │
│              │                             │                         │
│    ┌─────────▼──────────┐   ┌─────────────▼──────────┐               │
│    │   rtsp-exporter    │   │   blackbox-exporter    │               │
│    │ Кастомный Python   │   │ Prometheus Blackbox    │               │
│    │ RTSP OPTIONS probe │   │ ICMP + TCP проверки    │               │
│    │       :9115        │   │       :9116 (→9115)    │               │
│    └─────────┬──────────┘   └─────────────┬──────────┘               │
│              │                             │                         │
│              └──────────────┬──────────────┘                         │
│                             │                                        │
│                  ┌──────────▼──────────┐                             │
│                  │  VictoriaMetrics    │                             │
│                  │   Сбор метрик       │                             │
│                  │  :9090 (→8428)      │                             │
│                  └──────────┬──────────┘                             │
│                             │                                        │
│                  ┌──────────▼──────────┐                             │
│                  │       Grafana       │                             │
│                  │    Визуализация     │                             │
│                  │       :3000         │                             │
│                  └─────────────────────┘                             │
└──────────────────────────────────────────────────────────────────────┘
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
- Свободные порты: `3000`, `8554–8556`, `9090`, `9115`, `9116`

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
├── exporter_config.yml         # Список камер для мониторинга
├── requirements.txt            # Python-зависимости (устанавливаются при сборке Docker-образа)
│
├── blackbox.yml                # Конфигурация Blackbox Exporter (ICMP, TCP, HTTP, ONVIF)
├── prometheus.yml              # Конфигурация scrape для VictoriaMetrics
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

Откройте [`exporter_config.yml`](exporter_config.yml) и добавьте запись:

```yaml
cameras:
  - name: "my-camera"
    host: "192.168.1.100"    # IP-адрес камеры
    port: 554                 # RTSP-порт (обычно 554)
    path: "/stream1"          # RTSP-путь потока
    labels:
      location: "office"
      building: "main"
```

Экспортёр автоматически подхватит изменения при следующем цикле опроса (каждые 15 сек).

### Модули Blackbox Exporter

| Модуль | Протокол | Таймаут | Назначение |
|---|---|---|---|
| `icmp_check` | ICMP | 5 с | Ping-доступность камеры |
| `tcp_rtsp` | TCP | 5 с | Проверка RTSP-порта (554 / 8554) |
| `tcp_onvif` | TCP | 5 с | Проверка ONVIF-порта (80 / 8080) |
| `http_2xx` | HTTP/HTTPS | 10 с | Проверка веб-интерфейса камеры / NVR |

---

## 🛑 Остановка

```bash
docker compose down           # остановить (данные сохранятся)
docker compose down -v        # остановить и удалить тома (данные VictoriaMetrics/Grafana)
```

---

## 🔭 Как работает RTSP-экспортёр

1. Читает список камер из [`exporter_config.yml`](exporter_config.yml)
2. Каждые 15 секунд параллельно опрашивает все камеры в отдельных потоках
3. Отправляет `RTSP OPTIONS` запрос на TCP-порт камеры
4. Измеряет RTT (round-trip time) как `camera_rtsp_latency_ms`
5. Парсит дополнительные заголовки `X-RTP-PacketLoss`, `X-RTP-Jitter`, `X-RTP-Bitrate` из ответа mock-сервера
6. Экспонирует метрики в формате Prometheus на `:9115/metrics`

При сборке Docker-образа [`Dockerfile.exporter`](Dockerfile.exporter) устанавливает зависимости из [`requirements.txt`](requirements.txt) командой `pip install -r requirements.txt`.

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
| Python (экспортёр) | `3.12-slim` |
| PyYAML | `≥ 6.0` |

---

## 📈 Перспективы развития

- Поддержка ONVIF для автообнаружения камер
- Анализ качества видео через FFmpeg (VMAF, PSNR)
- Интеграция с системами оповещения (Alertmanager → Telegram/Email)
- Экспорт метрик из реальных RTP-сессий через `ffprobe`
- Поддержка HTTPS/RTSPS для зашифрованных потоков

---

## 👥 Команда

- Плясов Николай
- Чашкин Федор

Учебный проект, МИЭМ НИУ ВШЭ, 2026.
