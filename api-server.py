# redis_agent/api/server.py
import logging
import json
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger("redis-agent.api")

class FailoverRequest(BaseModel):
    target_dc: str
    force: bool = False
    reason: Optional[str] = None

class ApiServer:
    """API server for Redis Enterprise agent."""
    
    def __init__(self, core_agent, api_key: str, host: str = "0.0.0.0", port: int = 8080):
        """Initialize the API server.
        
        Args:
            core_agent: Reference to the core agent
            api_key: API key for authentication
            host: Host to bind to
            port: Port to listen on
        """
        self.core = core_agent
        self.api_key = api_key
        self.host = host
        self.port = port
        self.app = FastAPI(title="Redis Enterprise Agent API")
        
        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Add routes from routes module
        from redis_agent.api.routes import create_api_router
        router = create_api_router(self.core, self.api_key)
        self.app.include_router(router, prefix="/api")
    
    def start(self):
        """Start the API server."""
        import uvicorn
        
        # Run in a separate thread
        import threading
        threading.Thread(
            target=uvicorn.run,
            args=(self.app,),
            kwargs={"host": self.host, "port": self.port},
            daemon=True
        ).start()
        
        logger.info(f"API server started on {self.host}:{self.port}")