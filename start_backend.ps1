Set-Location -LiteralPath "D:\output\线上记帐工具\backend"
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
