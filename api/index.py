# api/index.py

from app.main import app

@app.get("/health")
async def health():
    return {"ok": True}
