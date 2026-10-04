import type { ReactElement } from 'react'
import { navigate, usePath } from './router'
import Home from './pages/Home'

// Маршруты: шаблон, номер шага (0 — вне пути), заголовок, страница.
type Route = [RegExp, number, string, (m: string[]) => ReactElement]
const ROUTES: Route[] = [
  [/^\/$/, 0, '', () => <Home />],
]

function Header({ step, title, over }: { step: number; title: string; over: boolean }) {
  return (
    <header className={`header${over ? ' over' : ''}`}>
      <a className="brand" href="/" onClick={(e) => { e.preventDefault(); navigate('/') }}>
        <span className="brand-mark" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 14 14"><path d="M1 13V5l6-4 6 4v8H9V8H5v5z" fill="currentColor" /></svg>
        </span>
        AI Redesign
      </a>
      {step > 0 && (
        <div className="steps">
          <span className="steps-label">Шаг {step} из 8 · {title}</span>
          <div className="steps-bar" aria-hidden="true">
            {Array.from({ length: 8 }, (_, i) => <i key={i} className={i + 1 < step ? 'done' : i + 1 === step ? 'now' : ''} />)}
          </div>
        </div>
      )}
    </header>
  )
}

export default function App() {
  const path = usePath()
  for (const [re, step, title, page] of ROUTES) {
    const m = path.match(re)
    if (m) {
      return (
        <div className="app">
          <Header step={step} title={title} over={path === '/'} />
          {page(m)}
        </div>
      )
    }
  }
  return (
    <div className="app">
      <Header step={0} title="" over={false} />
      <main className="page"><h1>Страница не найдена</h1><a href="/">На главную</a></main>
    </div>
  )
}
