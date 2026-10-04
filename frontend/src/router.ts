import { useEffect, useState } from 'react'

export function navigate(to: string) {
  history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function usePath() {
  const [path, setPath] = useState(location.pathname)
  useEffect(() => {
    const on = () => {
      setPath(location.pathname)
      window.scrollTo(0, 0)
    }
    window.addEventListener('popstate', on)
    return () => window.removeEventListener('popstate', on)
  }, [])
  return path
}
