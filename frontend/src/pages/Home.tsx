import { useEffect, useRef, useState } from 'react'

// Иллюстрация лендинга: комната 340 × 460, мебель «сейчас» и после перестановки (x, y, w, d в см).
const ROOM = { w: 340, d: 460 }
const FURNITURE: { label: string; from: number[]; to: number[] }[] = [
  { label: 'Кровать', from: [0, 160, 200, 160], to: [0, 200, 160, 200] },
  { label: 'Шкаф', from: [280, 0, 60, 100], to: [280, 120, 60, 120] },
  { label: 'Стол', from: [280, 150, 60, 120], to: [110, 0, 120, 60] },
  { label: 'Стул', from: [225, 190, 50, 45], to: [145, 65, 50, 45] },
  { label: 'Комод', from: [20, 415, 80, 45], to: [295, 260, 45, 80] },
  { label: 'Тумба', from: [0, 115, 40, 45], to: [165, 200, 40, 45] },
  { label: 'Кресло', from: [140, 380, 80, 80], to: [0, 20, 80, 80] },
]
const FRAMES = [
  { kicker: 'AI Redesign', title: 'Переставьте мебель так, чтобы всё поместилось', text: 'Сфотографируйте комнату — получите проверенные варианты перестановки.' },
  { kicker: 'Шаг 1', title: 'Снимки превращаются в план с реальными размерами', text: 'Языковая модель распознаёт стены, окна, двери и вашу мебель.' },
  { kicker: 'Шаг 2', title: 'Скажите, что важно. Решатель проверит каждый сантиметр', text: 'Пожелания становятся формальными ограничениями, а CP-SAT гарантирует, что всё физически встанет.' },
  { kicker: 'Шаг 3', title: '3–5 вариантов. Каждый гарантированно выполним', text: 'Дверцы открываются, проход не уже 60 см, порядок перестановки — по шагам.' },
]

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const clamp = (v: number) => Math.min(1, Math.max(0, v))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t

function useScrollProgress(ref: React.RefObject<HTMLElement | null>) {
  const [p, setP] = useState(0)
  useEffect(() => {
    let frame = 0
    const on = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const el = ref.current
        if (!el) return
        const r = el.getBoundingClientRect()
        setP(clamp(-r.top / (r.height - innerHeight)))
      })
    }
    on()
    addEventListener('scroll', on, { passive: true })
    addEventListener('resize', on)
    return () => {
      removeEventListener('scroll', on)
      removeEventListener('resize', on)
      cancelAnimationFrame(frame)
    }
  }, [ref])
  return p
}

function HeroRoom({ p }: { p: number }) {
  const move = ease(clamp((p - 0.55) / 0.35))
  const pass = clamp((p - 0.85) / 0.1)
  return (
    <svg viewBox="-40 -40 420 540" className="hero-room" aria-hidden="true">
      <defs>
        <pattern id="hero-grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M20 0H0V20" fill="none" stroke="rgb(255 255 255 / 5%)" strokeWidth="1" />
        </pattern>
        <linearGradient id="hero-floor" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1d232a" />
          <stop offset="1" stopColor="#12161a" />
        </linearGradient>
        <filter id="hero-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
      </defs>
      <rect width={ROOM.w} height={ROOM.d} fill="url(#hero-floor)" />
      <rect width={ROOM.w} height={ROOM.d} fill="url(#hero-grid)" />
      <rect x="95" y="-6" width="150" height="10" fill="#5fc4b4" filter="url(#hero-glow)" opacity="0.8" />
      <rect x="95" y="-4" width="150" height="6" fill="#9fe3d7" />
      <path d="M250 460 A80 80 0 0 1 330 380" fill="none" stroke="rgb(236 235 230 / 35%)" strokeDasharray="4 4" />
      <rect x="-6" y="-6" width={ROOM.w + 12} height={ROOM.d + 12} fill="none" stroke="#d9dde2" strokeWidth="8" />
      <rect x="250" y="456" width="80" height="12" fill="#0c0f12" />
      <path
        d="M290 450 C 290 380, 235 360, 235 300 S 225 160, 175 118"
        fill="none" stroke="#e2b977" strokeWidth="6" strokeLinecap="round"
        strokeDasharray="600" strokeDashoffset={600 * (1 - pass)} opacity={pass} filter="url(#hero-glow)"
      />
      <path
        d="M290 450 C 290 380, 235 360, 235 300 S 225 160, 175 118"
        fill="none" stroke="#f0cb8e" strokeWidth="2" strokeLinecap="round"
        strokeDasharray="600" strokeDashoffset={600 * (1 - pass)} opacity={pass}
      />
      {FURNITURE.map((f, i) => {
        const [x, y, w, d] = f.from.map((v, k) => lerp(v, f.to[k], move))
        return (
          <g key={f.label} style={{ opacity: clamp((p - 0.12 - i * 0.03) / 0.12) }}>
            <rect x={x + 3} y={y + 3} width={w - 6} height={d - 6} rx="6"
              fill="rgb(226 185 119 / 10%)" stroke="#e2b977" strokeOpacity="0.8" strokeWidth="1.5" />
            <text x={x + w / 2} y={y + d / 2 + 4} textAnchor="middle" fontSize="11" fill="#ecebe6" opacity="0.85">
              {f.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

export default function Home() {
  const hero = useRef<HTMLElement>(null)
  const p = useScrollProgress(hero)
  const frame = Math.min(FRAMES.length - 1, Math.floor(p * FRAMES.length * 0.999))
  // Камера: от перспективы к плану сверху и наезд.
  const tilt = lerp(58, 0, ease(clamp(p / 0.5)))
  const turn = lerp(-32, 0, ease(clamp(p / 0.5)))
  const zoom = lerp(0.8, 1, ease(clamp(p / 0.6)))

  return (
    <>
      <section ref={hero} className="hero" style={{ height: `${FRAMES.length * 100}vh` }}>
        <div className="hero-sticky">
          <div className="hero-stage" style={{ transform: `perspective(1400px) rotateX(${tilt}deg) rotateZ(${turn}deg) scale(${zoom})` }}>
            <HeroRoom p={p} />
          </div>
          <div className="hero-shade" />
          {FRAMES.map((f, i) => (
            <div key={i} className={`hero-copy${i === frame ? ' on' : ''}`} aria-hidden={i !== frame}>
              <span className="hero-kicker">{f.kicker}</span>
              <h1>{f.title}</h1>
              <p>{f.text}</p>
            </div>
          ))}
          <div className="hero-dots" aria-hidden="true">
            {FRAMES.map((_, i) => <i key={i} className={i === frame ? 'on' : ''} />)}
          </div>
          {p < 0.05 && <div className="hero-scroll">Листайте вниз</div>}
        </div>
      </section>
    </>
  )
}
