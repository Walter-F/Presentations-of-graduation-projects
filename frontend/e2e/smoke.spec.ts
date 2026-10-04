import { test, expect } from './fixtures'

test('страница открывается, сервер работает', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Сервер работает')).toBeVisible()
})
