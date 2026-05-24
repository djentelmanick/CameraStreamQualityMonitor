import React, { useState, useEffect } from 'react'
import styles from './CameraForm.module.css'

const EMPTY = {
  name: '',
  host: '',
  port: 8554,
  path: '/',
  vendor: 'mock',
  channel: 101,
  username: '',
  password: '',
  labels: { location: '', building: '' },
}

function defaultsForVendor(vendor) {
  if (vendor === 'hikvision') {
    return { port: 554, path: '/', channel: 101 }
  }
  if (vendor === 'mock') {
    return { port: 8554, path: '/' }
  }
  return { port: 554, path: '/' }
}

export default function CameraForm({ initial, onSubmit, onCancel, loading }) {
  const [form, setForm] = useState(initial || EMPTY)

  useEffect(() => {
    if (!initial) {
      setForm(EMPTY)
      return
    }
    const vendor = initial.vendor || (initial.port === 8554 ? 'mock' : 'generic')
    setForm({
      ...EMPTY,
      ...initial,
      vendor,
      channel: initial.channel ?? 101,
      username: initial.username || '',
      password: '',
    })
  }, [initial])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function setVendor(value) {
    setForm(f => ({ ...f, vendor: value, ...defaultsForVendor(value) }))
  }

  function setLabel(key, value) {
    setForm(f => ({ ...f, labels: { ...f.labels, [key]: value } }))
  }

  function hikvisionPath() {
    return `/Streaming/Channels/${form.channel}`
  }

  function handleSubmit(e) {
    e.preventDefault()
    const payload = {
      ...form,
      port: Number(form.port),
      channel: Number(form.channel),
    }
    if (payload.vendor === 'hikvision' && (payload.path === '/' || !payload.path)) {
      payload.path = hikvisionPath()
    }
    if (!payload.vendor) {
      delete payload.vendor
    }
    if (payload.vendor !== 'hikvision') {
      delete payload.channel
    }
    if (!payload.username) delete payload.username
    if (!payload.password) delete payload.password
    onSubmit(payload)
  }

  const isHikvision = form.vendor === 'hikvision'

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div className={styles.grid}>
        <div className={styles.field}>
          <label>Имя камеры *</label>
          <input
            required
            value={form.name}
            onChange={e => set('name', e.target.value)}
            placeholder="camera-1"
            disabled={!!initial}
          />
        </div>

        <div className={styles.field}>
          <label>Тип</label>
          <select value={form.vendor} onChange={e => setVendor(e.target.value)}>
            <option value="mock">Mock (учебный стенд)</option>
            <option value="hikvision">Hikvision</option>
            <option value="generic">Другая</option>
          </select>
        </div>

        <div className={styles.field}>
          <label>Host / IP *</label>
          <input
            required
            value={form.host}
            onChange={e => set('host', e.target.value)}
            placeholder={isHikvision ? '192.168.1.64' : '192.168.1.100'}
          />
        </div>

        <div className={styles.field}>
          <label>Порт</label>
          <input
            type="number"
            min={1}
            max={65535}
            value={form.port}
            onChange={e => set('port', e.target.value)}
          />
        </div>

        {isHikvision ? (
          <div className={styles.field}>
            <label>Поток</label>
            <select
              value={form.channel}
              onChange={e => set('channel', Number(e.target.value))}
            >
              <option value={101}>Основной (101)</option>
              <option value={102}>Субпоток (102)</option>
            </select>
          </div>
        ) : (
          <div className={styles.field}>
            <label>RTSP-путь</label>
            <input
              value={form.path}
              onChange={e => set('path', e.target.value)}
              placeholder="/"
            />
          </div>
        )}

        {isHikvision && (
          <>
            <div className={styles.field}>
              <label>Логин</label>
              <input
                value={form.username}
                onChange={e => set('username', e.target.value)}
                placeholder="admin"
                autoComplete="username"
              />
            </div>
            <div className={styles.field}>
              <label>Пароль</label>
              <input
                type="password"
                value={form.password}
                onChange={e => set('password', e.target.value)}
                placeholder={initial ? 'оставьте пустым, чтобы не менять' : ''}
                autoComplete="current-password"
              />
            </div>
          </>
        )}

        <div className={styles.field}>
          <label>Локация</label>
          <input
            value={form.labels.location}
            onChange={e => setLabel('location', e.target.value)}
            placeholder="entrance"
          />
        </div>

        <div className={styles.field}>
          <label>Здание</label>
          <input
            value={form.labels.building}
            onChange={e => setLabel('building', e.target.value)}
            placeholder="A"
          />
        </div>
      </div>

      {isHikvision && (
        <p className={styles.hint}>
          RTSP: <code>rtsp://{form.username || 'user'}:***@{form.host || '…'}:{form.port}{hikvisionPath()}</code>
        </p>
      )}

      <div className={styles.actions}>
        <button type="button" className={styles.cancel} onClick={onCancel}>
          Отмена
        </button>
        <button type="submit" className={styles.submit} disabled={loading}>
          {loading ? 'Сохранение…' : initial ? 'Сохранить' : 'Добавить'}
        </button>
      </div>
    </form>
  )
}
