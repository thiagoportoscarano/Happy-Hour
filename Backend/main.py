import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.cassandra import connect, disconnect
from app.routers import auth, eventos, tickets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando Happy Hour API…")
    connect()          
    yield             
    logger.info("🛑 Encerrando Happy Hour API…")
    disconnect()

app = FastAPI(
    title="Happy Hour API",
    description="Backend para a plataforma de ingressos Happy Hour — UNIRIO EIA",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(eventos.router)
app.include_router(tickets.router)

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "Happy Hour API", "versao": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    from app.db.cassandra import get_session
    try:
        get_session().execute("SELECT release_version FROM system.local")
        return {"status": "ok", "cassandra": "conectado"}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}
