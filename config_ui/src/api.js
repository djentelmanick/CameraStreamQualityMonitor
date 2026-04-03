const BASE = import.meta.env.VITE_API_URL || ''

export async function fetchCameras() {
  const res = await fetch(`${BASE}/cameras`)
  if (!res.ok) throw new Error('Ошибка загрузки камер')
  return res.json()
}

export async function createCamera(camera) {
  const res = await fetch(`${BASE}/cameras`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(camera),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Ошибка создания камеры')
  }
  return res.json()
}

export async function updateCamera(name, camera) {
  const res = await fetch(`${BASE}/cameras/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(camera),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Ошибка обновления камеры')
  }
  return res.json()
}

export async function deleteCamera(name) {
  const res = await fetch(`${BASE}/cameras/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Ошибка удаления камеры')
  }
}
