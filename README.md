# 📹 Camera Stream Quality Monitor — PoC

Proof of Concept для мониторинга качества видеопотоков IP-камер с использованием Prometheus Blackbox Exporter, кастомного RTSP-экспортёра и Grafana.

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
│    │       :9115        │   │       :9115 (9116)     │               │
│    └─────────┬──────────┘   └─────────────┬──────────┘               │
│              │                             │                         │
│              └──────────────┬──────────────┘                         │
│                             │                                        │
│                  ┌──────────▼──────────┐                             │
│                  │      Prometheus     │                             │
│                  │    Сбор метрик      │                             │
│                  │       :9090         │                             │
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

| Метрика | Тип | Описание |
|---|---|---|
| `camera_up` | gauge | Доступность камеры: 1 = онлайн, 0 = офлайн |
| `camera_rtsp_latency_ms` | gauge | Задержка RTSP-подключения (мс) |
| `camera_rtp_packet_loss_ratio` | gauge | Доля потерянных RTP-пакетов (0..1) |
| `camera_rtp_jitter_ms` | gauge | Джиттер RTP (мс) |
| `camera_stream_bitrate_kbps` | gauge | Битрейт видеопотока (кбит/с) |
| `camera_last_scrape_timestamp` | gauge | Unix-время последнего опроса |
| `probe_success` (Blackbox) | gauge | TCP/ICMP доступность |
| `probe_duration_seconds` (Blackbox) | gauge | Время ответа TCP/ICMP |

Все метрики содержат лейблы: `camera`, `host`, `port`, `location`, `building`.

---

## 🚀 Быстрый старт

### Предварительные требования

- Docker Engine ≥ 20.10
- Docker Compose ≥ 2.0
- Свободные порты: 3000, 8554–8556, 9090, 9115, 9116

### Запуск

```bash
# 1. Клонировать репозиторий
git clone https://git.miem.hse.ru/nvpliasov/1-3-blackbox-exporter.git
cd camera-monitoring

# 2. Запустить весь стек
docker compose up --build -d

# 3. Проверить статус
docker compose ps
```

### Доступ к сервисам

| Сервис | URL | Логин / Пароль |
|---|---|---|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |
| RTSP Exporter | http://localhost:9115/metrics | — |
| Blackbox Exporter | http://localhost:9116/metrics | — |

### Проверка метрик вручную

```bash
# Посмотреть метрики RTSP-экспортёра
curl http://localhost:9115/metrics

# Проверить доступность камеры через Blackbox (TCP)
curl "http://localhost:9116/probe?module=tcp_rtsp&target=localhost:8554"

# Посмотреть метрики в Prometheus
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
│
├── blackbox.yml                # Конфигурация Blackbox Exporter (ICMP, TCP, HTTP)
├── prometheus.yml              # Конфигурация Prometheus (scrape jobs)
│
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yml  # Автоматическое подключение Prometheus
    │   └── dashboards/
    │       └── dashboards.yml  # Автозагрузка дашбордов
    └── dashboards/
        └── camera_monitoring.json  # Основной дашборд Grafana
```

---

## ⚙️ Конфигурация

### Добавить реальную камеру

Откройте `exporter_config.yml` и добавьте запись:

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

Экспортёр автоматически подхватит изменения при следующем цикле опроса (15 сек).

### Изменить параметры mock-камеры

В `docker-compose.yml` задайте переменные окружения:

```yaml
environment:
  LATENCY_MS: "200"      # задержка ответа в мс
  PACKET_LOSS: "0.10"    # 10% потерь пакетов
  BITRATE_KBPS: "4096"   # битрейт 4 Мбит/с
```

---

## 🛑 Остановка

```bash
docker compose down           # остановить (данные сохранятся)
docker compose down -v        # остановить и удалить тома (данные Prometheus/Grafana)
```

---

## 🔭 Как работает RTSP-экспортёр

1. Читает список камер из `exporter_config.yml`
2. Каждые 15 секунд параллельно опрашивает все камеры
3. Отправляет `RTSP OPTIONS` запрос на TCP-порт камеры
4. Измеряет RTT (round-trip time) как `latency_ms`
5. Парсит дополнительные заголовки `X-RTP-*` (если камера/mock их поддерживает)
6. Экспонирует метрики в формате Prometheus на `:9115/metrics`

---

## 📊 Описание дашборда Grafana

Дашборд **Camera Monitoring — PoC** содержит:

- **Stat-панели**: количество камер онлайн/офлайн, средняя задержка, макс. потери
- **Таблица**: сводное состояние всех камер
- **Графики**: задержка, потери пакетов, джиттер, битрейт — в динамике
- **Blackbox-панели**: TCP-доступность и время ответа RTSP-порта

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
