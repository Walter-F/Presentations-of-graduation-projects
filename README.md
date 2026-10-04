Репозитории этих двух конкретных проектов содержат участки с конфиденциальными данными, поэтому исходный код размещён не будет, в отличие от презентаций.

## AI Redesign: запуск (Windows)

Нужно: Docker Desktop, Python 3.11, Node.js 22. Все команды — PowerShell из корня репозитория.

1. База данных:
   ```
   copy .env.example .env
   docker compose up -d
   ```
2. Бэкенд:
   ```
   py -3.11 -m venv .venv
   .venv\Scripts\pip install -r backend\requirements.txt
   cd backend
   $env:PYTHONUTF8=1
   ..\.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. Фронтенд, во втором окне:
   ```
   cd frontend
   npm install
   npm run dev
   ```
4. Откройте http://localhost:5173 — на странице «Сервер работает». Адрес http://localhost:8000/health отвечает `{"status":"ok","db":true}`.

С телефона в той же Wi-Fi: http://<IP компьютера>:5173 (IP — в `ipconfig`). При первом запуске Windows спросит доступ к сети для python.exe и node.exe: разрешите для частных сетей. Профиль Wi-Fi должен быть «Частная сеть».

Тесты бэкенда: `cd backend; ..\.venv\Scripts\pytest`.
