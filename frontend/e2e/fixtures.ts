import { test as base, expect, type Page } from '@playwright/test'

// Каждый тест падает, если в браузере была ошибка консоли, исключение или ответ 4xx/5xx.
export const test = base.extend<{ consoleGuard: void }>({
  consoleGuard: [
    async ({ context }, use) => {
      const problems: string[] = []
      const watch = (page: Page) => {
        page.on('console', (m) => m.type() === 'error' && problems.push(`console: ${m.text()}`))
        page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`))
        page.on('response', (r) => r.status() >= 400 && problems.push(`${r.status()} ${r.url()}`))
        page.on('requestfailed', (r) => {
          if (!r.failure()?.errorText.includes('ERR_ABORTED')) problems.push(`failed: ${r.url()}`)
        })
      }
      context.pages().forEach(watch)
      context.on('page', watch)
      await use()
      expect(problems).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
