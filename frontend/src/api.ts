import { useCallback, useEffect, useRef, useState } from 'react'

export async function api<T = any>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData
  let r: Response
  try {
    r = await fetch(path, {
      method,
      headers: body === undefined || isForm ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
    })
  } catch {
    throw new Error('Сервер не отвечает')
  }
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Ошибка сервера (${r.status})`)
  return data
}

// Загрузка данных страницы; pollMs — опрос без наложения запросов.
export function useLoad<T = any>(path: string | null, pollMs?: number) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const alive = useRef(true)

  const reload = useCallback(async () => {
    if (!path) return
    try {
      const d = await api<T>('GET', path)
      if (alive.current) {
        setData(d)
        setError(null)
      }
    } catch (e) {
      if (alive.current) setError((e as Error).message)
    }
  }, [path])

  useEffect(() => {
    alive.current = true
    let timer: number | undefined
    const tick = async () => {
      await reload()
      if (alive.current && pollMs) timer = window.setTimeout(tick, pollMs)
    }
    tick()
    return () => {
      alive.current = false
      window.clearTimeout(timer)
    }
  }, [reload, pollMs])

  return { data, error, reload, setData }
}
