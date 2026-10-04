import { test, expect } from './fixtures'

test('лендинг открывается, сервер работает', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Переставьте мебель так, чтобы всё поместилось' })).toBeVisible()
  expect(await (await request.get('/health')).json()).toEqual({ status: 'ok', db: true })
})
