
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, crisis, market, teams, trades
from app.config import get_settings
from app.websocket import routes as websocket_routes

settings = get_settings()


app = FastAPI(
    title="E-Summit Live Stock Market API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(teams.router)
app.include_router(trades.router)
app.include_router(market.router)
app.include_router(admin.router)
app.include_router(crisis.router)
app.include_router(websocket_routes.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
