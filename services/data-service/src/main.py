from fastapi import FastAPI

app = FastAPI(title="Smart Money Data Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}