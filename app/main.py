import logging
from fastapi import FastAPI
from .database import Base, engine
from .api.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
Base.metadata.create_all(bind=engine)
app = FastAPI(title="Geospatial Measurement API", version="1.0.0")
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok"}
