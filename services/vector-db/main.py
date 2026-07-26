"""
AegisMesh — Vector Database Service (vector-db)
Port 8004
"""

import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [VectorDB] %(message)s")
logger = logging.getLogger("VectorDB")

app = FastAPI(title="AegisMesh Vector DB Service", version="1.0.0")

class ConfigPatch(BaseModel):
    DB_CONNECTION_TIMEOUT_MS: int = 3000

runtime_config = {
    "db_connection_timeout_ms": 3000,
    "max_connections": 100
}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "vector-db",
        "db_connection_timeout_ms": runtime_config["db_connection_timeout_ms"],
        "max_connections": runtime_config["max_connections"]
    }

@app.post("/admin/config")
async def patch_config(patch: dict):
    logger.info(f"Received admin config patch: {patch}")
    if "DB_CONNECTION_TIMEOUT_MS" in patch:
        val = int(patch["DB_CONNECTION_TIMEOUT_MS"])
        runtime_config["db_connection_timeout_ms"] = val
        logger.info(f"Updated DB_CONNECTION_TIMEOUT_MS to {val}")
        return {
            "status": "SUCCESS",
            "message": f"Updated DB_CONNECTION_TIMEOUT_MS to {val} on vector-db",
            "db_connection_timeout_ms": val
        }
    return {"status": "NO_CHANGE", "current_config": runtime_config}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004)
