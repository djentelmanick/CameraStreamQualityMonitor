import React, { useState, useEffect, useCallback } from 'react'
import CameraTable from './components/CameraTable'
import CameraForm from './components/CameraForm'
import { fetchCameras, createCamera, updateCamera, deleteCamera } from './api'
import styles from './App.module.css'

export default function App() {
  const [cameras, setCameras] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editTarget, setEditTarget] = useState(null) // null = добавление, object = редактирование

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchCameras()
      setCameras(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openAdd() {
    setEditTarget(null)
    setShowForm(true)
  }

  function openEdit(cam) {
    setEditTarget(cam)
    setShowForm(true)
  }

  function closeForm() {
    setShowForm(false)
    setEditTarget(null)
  }

  async function handleSubmit(data) {
    setSaving(true)
    setError(null)
    try {
      if (editTarget) {
        await updateCamera(editTarget.name, data)
      } else {
        await createCamera(data)
      }
      closeForm()
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(name) {
    if (!confirm(`Удалить камеру «${name}»?`)) return
    setError(null)
    try {
      await deleteCamera(name)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.title}>
            <span className={styles.icon}>📹</span>
            <div>
              <h1>Camera Config</h1>
              <p>Управление списком камер RTSP-экспортёра</p>
            </div>
          </div>
          <button className={styles.addBtn} onClick={openAdd}>
            + Добавить камеру
          </button>
        </div>
      </header>

      <main className={styles.main}>
        {error && (
          <div className={styles.error}>
            ⚠️ {error}
            <button onClick={() => setError(null)}>✕</button>
          </div>
        )}

        {showForm && (
          <CameraForm
            initial={editTarget}
            onSubmit={handleSubmit}
            onCancel={closeForm}
            loading={saving}
          />
        )}

        {loading ? (
          <div className={styles.loader}>Загрузка…</div>
        ) : (
          <>
            <div className={styles.stats}>
              <span className={styles.badge}>{cameras.length} камер</span>
            </div>
            <CameraTable
              cameras={cameras}
              onEdit={openEdit}
              onDelete={handleDelete}
            />
          </>
        )}
      </main>
    </div>
  )
}
