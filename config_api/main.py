#!/usr/bin/env python3
"""
config_api/main.py — FastAPI-сервис для управления конфигурацией камер.

Предоставляет REST API для чтения и изменения exporter_config.yml,
который используется кастомным RTSP-экспортёром.
"""

import os
import threading
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/exporter_config.yml")

app = FastAPI(
    title="Camera Config API",
    description="REST API для управления списком камер RTSP-экспортёра",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.Lock()


# ─── Модели ──────────────────────────────────────────────────────────────────

class CameraLabels(BaseModel):
    location: Optional[str] = ""
    building: Optional[str] = ""

    class Config:
        extra = "allow"  # разрешаем произвольные лейблы


class Camera(BaseModel):
    name: str = Field(..., description="Уникальное имя камеры")
    host: str = Field(..., description="IP-адрес или hostname камеры")
    port: int = Field(554, description="RTSP-порт (обычно 554)")
    path: str = Field("/", description="RTSP-путь потока")
    labels: CameraLabels = Field(default_factory=CameraLabels)


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _read_config() -> List[dict]:
    """Читает список камер из YAML-файла."""
    try:
        with open(CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("cameras", [])
    except FileNotFoundError:
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения конфига: {e}")


def _write_config(cameras: List[dict]) -> None:
    """Записывает список камер в YAML-файл."""
    try:
        with open(CONFIG_PATH, "w") as f:
            yaml.dump({"cameras": cameras}, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка записи конфига: {e}")


def _camera_to_dict(camera: Camera) -> dict:
    return {
        "name": camera.name,
        "host": camera.host,
        "port": camera.port,
        "path": camera.path,
        "labels": camera.labels.model_dump(),
    }


# ─── Эндпоинты ───────────────────────────────────────────────────────────────

@app.get("/cameras", response_model=List[dict], summary="Получить список всех камер")
def list_cameras():
    with _lock:
        return _read_config()


@app.get("/cameras/{name}", response_model=dict, summary="Получить камеру по имени")
def get_camera(name: str):
    with _lock:
        cameras = _read_config()
    for cam in cameras:
        if cam["name"] == name:
            return cam
    raise HTTPException(status_code=404, detail=f"Камера '{name}' не найдена")


@app.post("/cameras", response_model=dict, status_code=201, summary="Добавить новую камеру")
def create_camera(camera: Camera):
    with _lock:
        cameras = _read_config()
        if any(c["name"] == camera.name for c in cameras):
            raise HTTPException(status_code=409, detail=f"Камера '{camera.name}' уже существует")
        cameras.append(_camera_to_dict(camera))
        _write_config(cameras)
    return _camera_to_dict(camera)


@app.put("/cameras/{name}", response_model=dict, summary="Обновить камеру по имени")
def update_camera(name: str, camera: Camera):
    with _lock:
        cameras = _read_config()
        for i, cam in enumerate(cameras):
            if cam["name"] == name:
                cameras[i] = _camera_to_dict(camera)
                _write_config(cameras)
                return cameras[i]
    raise HTTPException(status_code=404, detail=f"Камера '{name}' не найдена")


@app.delete("/cameras/{name}", status_code=204, summary="Удалить камеру по имени")
def delete_camera(name: str):
    with _lock:
        cameras = _read_config()
        new_cameras = [c for c in cameras if c["name"] != name]
        if len(new_cameras) == len(cameras):
            raise HTTPException(status_code=404, detail=f"Камера '{name}' не найдена")
        _write_config(new_cameras)


@app.get("/health", summary="Проверка работоспособности сервиса")
def health():
    return {"status": "ok", "config_path": CONFIG_PATH}
