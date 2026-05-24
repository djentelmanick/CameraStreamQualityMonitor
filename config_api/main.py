#!/usr/bin/env python3

import os
import logging
import threading
import urllib.request
import urllib.error
from typing import List, Literal, Optional

log = logging.getLogger(__name__)

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/exporter_config.yml")
EXPORTER_URL = os.environ.get("EXPORTER_URL", "http://rtsp-exporter:9115")

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


def _notify_exporter() -> None:
    url = f"{EXPORTER_URL}/reload"
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=2):
            pass
    except urllib.error.URLError as e:
        log.warning(f"Could not notify exporter: {e}")


class CameraLabels(BaseModel):
    location: Optional[str] = ""
    building: Optional[str] = ""

    class Config:
        extra = "allow"


class Camera(BaseModel):
    name: str
    host: str
    port: Optional[int] = None
    path: str = "/"
    vendor: Literal["", "mock", "hikvision", "generic"] = ""
    channel: int = Field(101, ge=101, le=302)
    username: str = ""
    password: str = ""
    labels: CameraLabels = Field(default_factory=CameraLabels)

    @field_validator("vendor", mode="before")
    @classmethod
    def normalize_vendor(cls, v):
        if v is None:
            return ""
        return str(v).strip().lower()


def _read_config() -> List[dict]:
    try:
        with open(CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("cameras", [])
    except FileNotFoundError:
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения конфига: {e}")


def _write_config(cameras: List[dict]) -> None:
    try:
        with open(CONFIG_PATH, "w") as f:
            yaml.dump({"cameras": cameras}, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка записи конфига: {e}")


def _camera_to_dict(camera: Camera) -> dict:
    data = {
        "name": camera.name,
        "host": camera.host,
        "path": camera.path,
        "labels": camera.labels.model_dump(),
    }
    if camera.port is not None:
        data["port"] = camera.port
    if camera.vendor:
        data["vendor"] = camera.vendor
    if camera.vendor == "hikvision":
        data["channel"] = camera.channel
    if camera.username:
        data["username"] = camera.username
    if camera.password:
        data["password"] = camera.password
    return data


@app.get("/cameras", response_model=List[dict])
def list_cameras():
    with _lock:
        return _read_config()


@app.get("/cameras/{name}", response_model=dict)
def get_camera(name: str):
    with _lock:
        cameras = _read_config()
    for cam in cameras:
        if cam["name"] == name:
            return cam
    raise HTTPException(status_code=404, detail=f"Камера '{name}' не найдена")


@app.post("/cameras", response_model=dict, status_code=201)
def create_camera(camera: Camera):
    with _lock:
        cameras = _read_config()
        if any(c["name"] == camera.name for c in cameras):
            raise HTTPException(status_code=409, detail=f"Камера '{camera.name}' уже существует")
        cameras.append(_camera_to_dict(camera))
        _write_config(cameras)
    _notify_exporter()
    return _camera_to_dict(camera)


@app.put("/cameras/{name}", response_model=dict)
def update_camera(name: str, camera: Camera):
    with _lock:
        cameras = _read_config()
        for i, cam in enumerate(cameras):
            if cam["name"] == name:
                updated = _camera_to_dict(camera)
                if not camera.password and cam.get("password"):
                    updated["password"] = cam["password"]
                cameras[i] = updated
                _write_config(cameras)
                _notify_exporter()
                return cameras[i]
    raise HTTPException(status_code=404, detail=f"Камера '{name}' не найдена")


@app.delete("/cameras/{name}", status_code=204)
def delete_camera(name: str):
    with _lock:
        cameras = _read_config()
        new_cameras = [c for c in cameras if c["name"] != name]
        if len(new_cameras) == len(cameras):
            raise HTTPException(status_code=404, detail=f"Камера '{name}' не найдена")
        _write_config(new_cameras)
    _notify_exporter()


@app.get("/health")
def health():
    return {"status": "ok", "config_path": CONFIG_PATH}
