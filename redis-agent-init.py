# redis_agent/__init__.py
"""Redis Enterprise AI Monitoring and Failover Agent."""

__version__ = "1.0.0"
__author__ = "Your Name"
__license__ = "MIT"

# Import core components to make them available directly
from redis_agent.core import RedisAgentCore
from redis_agent.main import main
