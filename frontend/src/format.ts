// Числа по-русски: десятичная запятая, неразрывный пробел перед единицей.
const NB = ' '

export const num = (v: number, digits = 1) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits }).format(v)
export const cm = (v: number) => `${num(Math.round(v), 0)}${NB}см`
export const m = (centimetres: number) => `${num(centimetres / 100)}${NB}м`
export const m2 = (v: number) => `${num(v)}${NB}м²`
export const pct = (v: number) => `${num(v, 0)}${NB}%`
export const size = (w: number, d: number) => `${num(w / 100)} × ${num(d / 100)}${NB}м`

export function plural(n: number, one: string, few: string, many: string) {
  const r = new Intl.PluralRules('ru').select(n)
  return r === 'one' ? one : r === 'few' ? few : many
}
