from fastapi import FastAPI

app = FastAPI(title="Elliott Wave Data Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}