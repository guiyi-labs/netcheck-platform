import time

from fastapi import FastAPI

app = FastAPI(title="Demo Slow Service")


@app.get("/")
def slow_response() -> dict[str, str]:
    time.sleep(3)
    return {"status": "slow", "message": "response delayed by 3 seconds"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "demo-web-slow"}
