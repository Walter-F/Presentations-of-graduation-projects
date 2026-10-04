import { useEffect, useState } from 'react'

export default function App() {
  const [status, setStatus] = useState('Проверяем сервер…')

  useEffect(() => {
    fetch('/health')
      .then((r) => r.json())
      .then((h) => setStatus(h.db ? 'Сервер работает' : 'Сервер работает, база недоступна'))
      .catch(() => setStatus('Сервер не отвечает'))
  }, [])

  return (
    <main>
      <h1>AI Redesign</h1>
      <p>{status}</p>
    </main>
  )
}
