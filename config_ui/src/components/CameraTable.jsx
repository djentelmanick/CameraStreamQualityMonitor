import React from 'react'
import styles from './CameraTable.module.css'

export default function CameraTable({ cameras, onEdit, onDelete }) {
  if (cameras.length === 0) {
    return <p className={styles.empty}>Камеры не найдены. Добавьте первую камеру.</p>
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Имя</th>
            <th>Тип</th>
            <th>Host</th>
            <th>Порт</th>
            <th>Путь</th>
            <th>Локация</th>
            <th>Здание</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>
          {cameras.map(cam => (
            <tr key={cam.name}>
              <td><code>{cam.name}</code></td>
              <td>{cam.vendor || '—'}</td>
              <td>{cam.host}</td>
              <td>{cam.port}</td>
              <td><code>{cam.path}</code></td>
              <td>{cam.labels?.location || '—'}</td>
              <td>{cam.labels?.building || '—'}</td>
              <td className={styles.actions}>
                <button className={styles.edit} onClick={() => onEdit(cam)}>
                  ✏️ Изменить
                </button>
                <button className={styles.del} onClick={() => onDelete(cam.name)}>
                  🗑 Удалить
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
