#!/usr/bin/env python3
# redis_agent/core.py - Core framework for Redis Enterprise monitoring agent

import logging
import os
import json
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path

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

@dataclass
class RedisInstance:
    """Information about a Redis instance/database to monitor"""
    name: str
    uid: str
    endpoints: Dict[str, Dict[str, Any]]  # DC name -> endpoint info
    active_dc: str = "primary"
    password: Optional[str] = None

@dataclass
class HealthStatus:
    """Health status of a Redis instance"""
    status: str = "unknown"  # healthy, degraded, failing, failed
    can_serve_traffic: bool = True
    latency_ms: float = 0
    memory_used_percent: float = 0
    hit_rate: float = 0
    ops_per_second: int = 0
    connected_clients: int = 0
    last_check: float = 0
    consecutive_errors: int = 0
    consecutive_anomalies: int = 0
    anomaly_score: float = 0
    error_message: Optional[str] = None

@dataclass
class AgentConfig:
    """Configuration for the Redis Enterprise Agent"""
    # Redis instances to monitor
    instances: List[RedisInstance] = field(default_factory=list)
    
    # Datacenters information
    datacenters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Monitoring settings
    monitoring_interval: int = 30  # seconds
    decision_interval: int = 60  # seconds
    
    # Anomaly detection settings
    model_path: str = "./models"
    anomaly_threshold: float = 0.8
    
    # Failover settings
    auto_failover: bool = False
    failover_provider: str = "dns"  # dns, haproxy, etc.
    failover_confidence_threshold: float = 0.95
    failover_consecutive_threshold: int = 3
    
    # DNS settings (if using DNS-based failover)
    dns_provider: str = "route53"  # route53, clouddns, etc.
    dns_config: Dict[str, Any] = field(default_factory=dict)
    
    # Alert settings
    alert_endpoints: Dict[str, Dict[str, Any]] = field(default_factory=dict)

class RedisAgentCore:
    """Core class for Redis Enterprise agent with health monitoring and failover"""
    
    def __init__(self, config_path: str):
        """Initialize the Redis Enterprise agent.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        
        # Initialize internal state
        self.running = True
        self.health_status = {}  # instance_uid -> dict of DC -> HealthStatus
        self.last_failover_time = {}  # instance_uid -> timestamp
        self.last_alert_time = {}  # alert_key -> timestamp
        
        # Initialize locks
        self._health_lock = threading.RLock()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Handle termination signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def _load_config(self, config_path: str) -> AgentConfig:
        """Load configuration from file."""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Create instances list from config
            instances = []
            for instance_config in config_data.get("instances", []):
                # Process endpoints
                endpoints = {}
                for endpoint in instance_config.get("endpoints", []):
                    dc_name = endpoint.get("dc", "unknown")
                    endpoints[dc_name] = {
                        "host": endpoint.get("host"),
                        "port": endpoint.get("port")
                    }
                
                # Create instance
                instance = RedisInstance(
                    name=instance_config.get("name", "unknown"),
                    uid=instance_config.get("uid", ""),
                    endpoints=endpoints,
                    active_dc=instance_config.get("active_dc", "primary"),
                    password=instance_config.get("password")
                )
                instances.append(instance)
            
            # Create AgentConfig
            return AgentConfig(
                instances=instances,
                datacenters=config_data.get("datacenters", {}),
                monitoring_interval=config_data.get("monitoring_interval", 30),
                decision_interval=config_data.get("decision_interval", 60),
                model_path=config_data.get("model_path", "./models"),
                anomaly_threshold=config_data.get("anomaly_threshold", 0.8),
                auto_failover=config_data.get("auto_failover", False),
                failover_provider=config_data.get("failover_provider", "dns"),
                failover_confidence_threshold=config_data.get("failover_confidence_threshold", 0.95),
                failover_consecutive_threshold=config_data.get("failover_consecutive_threshold", 3),
                dns_provider=config_data.get("dns_provider", "route53"),
                dns_config=config_data.get("dns_config", {}),
                alert_endpoints=config_data.get("alert_endpoints", {})
            )
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    def initialize(self):
        """Initialize agent resources and connections."""
        # Initialize health status tracking for all instances and datacenters
        for instance in self.config.instances:
            self.health_status[instance.uid] = {}
            self.last_failover_time[instance.uid] = 0
            
            for dc_name in instance.endpoints:
                self.health_status[instance.uid][dc_name] = HealthStatus()
        
        # Initialize monitoring module
        self._init_monitoring()
        
        # Initialize anomaly detection
        self._init_anomaly_detection()
        
        # Initialize failover provider
        self._init_failover_provider()
        
        # Initialize alerting
        self._init_alerting()
        
        logger.info("Redis Enterprise agent initialized")
    
    def _init_monitoring(self):
        """Initialize the monitoring module."""
        # This will be implemented in the monitoring module
        logger.info("Monitoring module initialized")
    
    def _init_anomaly_detection(self):
        """Initialize the anomaly detection module."""
        # This will be implemented in the anomaly detection module
        
        # Create model directory if it doesn't exist
        model_path = Path(self.config.model_path)
        model_path.mkdir(parents=True, exist_ok=True)
        
        logger.info("Anomaly detection module initialized")
    
    def _init_failover_provider(self):
        """Initialize the failover provider."""
        # This will be implemented in the failover module
        logger.info("Failover provider initialized")
    
    def _init_alerting(self):
        """Initialize the alerting module."""
        # This will be implemented in the alerting module
        logger.info("Alerting module initialized")
    
    def start(self):
        """Start the agent."""
        logger.info("Starting Redis Enterprise agent")
        self.running = True
        
        # Start monitoring and decision threads
        self._start_monitoring()
        self._start_decision_making()
        
        logger.info("Redis Enterprise agent started")
    
    def stop(self):
        """Stop the agent."""
        logger.info("Stopping Redis Enterprise agent")
        self.running = False
        
        # Clean up resources
        self._cleanup()
        
        logger.info("Redis Enterprise agent stopped")
    
    def _start_monitoring(self):
        """Start the monitoring thread."""
        # This will be implemented in the monitoring module
        logger.info("Monitoring started")
    
    def _start_decision_making(self):
        """Start the decision making thread."""
        # This will be implemented in the decision module
        logger.info("Decision making started")
    
    def _cleanup(self):
        """Clean up resources."""
        logger.info("Cleaned up resources")
    
    def update_health_status(self, instance_uid: str, dc_name: str, status: HealthStatus):
        """Update health status for an instance in a specific datacenter."""
        with self._health_lock:
            if (instance_uid in self.health_status and 
                dc_name in self.health_status[instance_uid]):
                self.health_status[instance_uid][dc_name] = status
                
                # Log significant health changes
                if status.status in ["failing", "failed"]:
                    logger.warning(f"Instance {instance_uid} in datacenter {dc_name} is {status.status}: {status.error_message}")
    
    def get_health_status(self) -> Dict[str, Dict[str, HealthStatus]]:
        """Get the current health status of all instances."""
        with self._health_lock:
            # Create a deep copy to avoid thread safety issues
            return {
                instance_uid: {
                    dc_name: HealthStatus(**vars(status))
                    for dc_name, status in dc_status.items()
                }
                for instance_uid, dc_status in self.health_status.items()
            }
    
    def get_instance_health(self, instance_uid: str) -> Dict[str, HealthStatus]:
        """Get the health status for a specific instance."""
        with self._health_lock:
            if instance_uid in self.health_status:
                return {
                    dc_name: HealthStatus(**vars(status))
                    for dc_name, status in self.health_status[instance_uid].items()
                }
            return {}
    
    def get_active_dc(self, instance_uid: str) -> str:
        """Get the currently active datacenter for an instance."""
        for instance in self.config.instances:
            if instance.uid == instance_uid:
                return instance.active_dc
        return ""
    
    def switch_active_dc(self, instance_uid: str, new_active_dc: str) -> bool:
        """Switch the active datacenter for an instance."""
        # This will be implemented in the failover module
        logger.info(f"Switching active DC for instance {instance_uid} to {new_active_dc}")
        
        # Update local config
        for instance in self.config.instances:
            if instance.uid == instance_uid:
                instance.active_dc = new_active_dc
                return True
        
        return False

def main():
    """Main entry point for the Redis Enterprise agent."""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <config_path>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    
    try:
        # Create and start the agent
        agent = RedisAgentCore(config_path)
        agent.initialize()
        agent.start()
        
        # Keep the main thread alive
        while agent.running:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        if 'agent' in locals():
            agent.stop()

if __name__ == "__main__":
    main()
