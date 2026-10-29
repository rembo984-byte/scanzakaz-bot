from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health() -> dict:
    return {"ok": True}
