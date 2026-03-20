# -*- coding: utf-8 -*-
"""
FastAPI 入口：会议助手 MVP 后端。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.meeting import router as meeting_router

app = FastAPI(title="Intro Meeting Coach", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(meeting_router)


@app.get("/")
def root():
    return {"service": "intro-meeting-coach", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
