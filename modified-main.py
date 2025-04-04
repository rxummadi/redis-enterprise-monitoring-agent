#!/usr/bin/env python3
# redis_agent/main.py - Modified main entry point with Azure OpenAI and ELK integration

import os
import sys
import logging
import argparse
import json
import time
import signal
from pathlib import Path

# Module imports
from redis_agent.core import RedisAgentCore
from redis_agent.monitoring import RedisMonitor
from redis_agent.anomaly import AnomalyDetector
from redis_agent.enhanced_failover import EnhancedFailoverManager
from redis_agent.alerting import AlertManager
from redis_agent.azure_ai import AzureOpenAIDecisionMaker
from redis_agent.elk_client import ELKClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("redis_agent.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("redis-agent")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Redis Enterprise AI Monitoring Agent")
    parser.add_argument(
        "-c", "--config", 
        required=True,
        help="Path to configuration file"
    )
    parser.add_argument(
        "-v", "--verbose", 
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--no-failover", 
        action="store_true",
        help="Disable automatic failover"
    )
    parser.add_argument(
        "--no-ai", 
        action="store_true",
        help="Disable Azure OpenAI integration"
    )
    parser.add_argument(
        "--no-elk", 
        action="store_true",
        help="Disable ELK integration"
    )
    return parser.parse_args()

def setup_logging(verbose=False):
    """Setup logging level based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.getLogger("redis-agent").setLevel(level)
    
    # Set level for specific modules
    module_loggers = [
        "redis-agent.core",
        "redis-agent.monitoring",
        "redis-agent.anomaly",
        "redis-agent.failover",
        "redis-agent.enhanced-failover",
        "redis-agent.alerting",
        "redis-agent.azure-ai",
        "redis-agent.elk"
    ]
    
    for module in module_loggers:
        logging.getLogger(module).setLevel(level)

def main():
    """Main entry point for the Redis Enterprise agent."""
    # Parse command line arguments
    args = parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Check config file exists
    config_path = args.config
    if not os.path.isfile(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    
    try:
        # Check if config file is valid JSON
        with open(config_path, 'r') as f:
            try:
                json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in configuration file: {e}")
                sys.exit(1)
        
        # Override config if --no-failover is specified
        if args.no_failover:
            logger.info("Automatic failover disabled via command line argument")
        
        # Create and initialize the agent
        agent = RedisAgentCore(config_path)
        
        # Apply command line overrides
        if args.no_failover:
            agent.config.auto_failover = False
            
        if args.no_ai:
            agent.config.use_azure_openai = False
            
        if args.no_elk:
            agent.config.use_elk = False
        
        # Initialize core components
        agent.monitoring = RedisMonitor(agent)
        agent.anomaly_detector = AnomalyDetector(agent)
        
        # Initialize Azure OpenAI integration if enabled
        if getattr(agent.config, "use_azure_openai", True) and not args.no_ai:
            if hasattr(agent.config, "azure_openai"):
                logger.info("Initializing Azure OpenAI integration")
                agent.ai_advisor = AzureOpenAIDecisionMaker(agent)
            else:
                logger.warning("Azure OpenAI configuration missing. Disabling AI integration.")
                agent.config.use_azure_openai = False
        
        # Initialize ELK integration if enabled
        if getattr(agent.config, "use_elk", True) and not args.no_elk:
            if hasattr(agent.config, "elk"):
                logger.info("Initializing ELK integration")
                agent.elk_client = ELKClient(agent)
            else:
                logger.warning("ELK configuration missing. Disabling ELK integration.")
                agent.config.use_elk = False
        
        # Initialize enhanced or standard failover
        if getattr(agent.config, "use_azure_openai", True) or getattr(agent.config, "use_elk", True):
            agent.failover = EnhancedFailoverManager(agent)
            logger.info("Using enhanced failover with AI and/or ELK integration")
        else:
            from redis_agent.failover import FailoverManager
            agent.failover = FailoverManager(agent)
            logger.info("Using standard failover")
            
        # Initialize alerting
        agent.alerting = AlertManager(agent)
        
        # Initialize the agent
        agent.initialize()
        
        # Initialize all modules
        agent.monitoring.initialize()
        agent.anomaly_detector.initialize()
        
        if hasattr(agent, "elk_client"):
            agent.elk_client.initialize()
            
        agent.failover.initialize()
        agent.alerting.initialize()
        
        # Start the agent
        agent.start()
        
        # Keep the main thread alive with clean shutdown on signals
        while agent.running:
            time.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error(f"Error in main: {e}", exc_info=True)
    finally:
        if 'agent' in locals():
            agent.stop()

if __name__ == "__main__":
    main()
