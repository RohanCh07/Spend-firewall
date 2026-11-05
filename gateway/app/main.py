from fastapi import FastAPI

app = FastAPI(title="Spend Firewall Gateway")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
