import React, { useState, useEffect } from 'react'
import styles from './CameraForm.module.css'

const EMPTY = {
  name: '',
  host: '',
  port: 554,
  path: '/',
  labels: { location: '', building: '' },
}

export default function CameraForm({ initial, onSubmit, onCancel, loading }) {
  const [form, setForm] = useState(initial || EMPTY)

  useEffect(() => {
    setForm(initial || EMPTY)
  }, [initial])

  function set(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function setLabel(key, value) {
    setForm(f => ({ ...f, labels: { ...f.labels, [key]: value } }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    onSubmit({
      ...form,
      port: Number(form.port),
    })
  }

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
          <label>Host / IP *</label>
          <input
            required
            value={form.host}
            onChange={e => set('host', e.target.value)}
            placeholder="192.168.1.100"
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

        <div className={styles.field}>
          <label>RTSP-путь</label>
          <input
            value={form.path}
            onChange={e => set('path', e.target.value)}
            placeholder="/stream1"
          />
        </div>

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
