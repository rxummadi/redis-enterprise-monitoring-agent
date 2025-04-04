#!/usr/bin/env python3
# redis_agent/monitoring.py - Monitoring module for Redis Enterprise

import logging
import threading
import time
import json
import redis
import requests
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger("redis-agent.monitoring")

class RedisMonitor:
    """Monitor Redis Enterprise instances for health and performance"""
    
    def __init__(self, core_agent):
        """Initialize the Redis monitoring module.
        
        Args:
            core_agent: Reference to the core agent
        """
        self.core = core_agent
        self.config = core_agent.config
        self.clients = {}  # instance_uid -> dict of DC -> Redis client
        self.api_sessions = {}  # DC name -> requests Session
        self.metrics_history = {}  # instance_uid -> list of metrics
        self.monitoring_thread = None
        self.running = False
        self.lock = threading.RLock()
    
    def initialize(self):
        """Initialize Redis clients and API sessions."""
        self._init_redis_clients()
        self._init_api_sessions()
        
        # Initialize metrics history
        for instance in self.config.instances:
            self.metrics_history[instance.uid] = []
    
    def _init_redis_clients(self):
        """Initialize Redis clients for all instances and datacenters."""
        for instance in self.config.instances:
            self.clients[instance.uid] = {}
            
            for dc_name, endpoint in instance.endpoints.items():
                try:
                    # Create Redis client
                    client = redis.Redis(
                        host=endpoint["host"],
                        port=endpoint["port"],
                        password=instance.password,
                        socket_timeout=5.0,
                        socket_connect_timeout=3.0,
                        health_check_interval=30,
                        decode_responses=True
                    )
                    
                    # Test connection
                    client.ping()
                    
                    # Store client
                    self.clients[instance.uid][dc_name] = client
                    logger.info(f"Connected to Redis instance {instance.name} in datacenter {dc_name}")
                
                except Exception as e:
                    logger.error(f"Failed to connect to Redis instance {instance.name} in datacenter {dc_name}: {e}")
    
    def _init_api_sessions(self):
        """Initialize Redis Enterprise API sessions for all datacenters."""
        for dc_name, dc_config in self.config.datacenters.items():
            try:
                session = requests.Session()
                # Add authentication if available
                if "api_user" in dc_config and "api_password" in dc_config:
                    session.auth = (dc_config["api_user"], dc_config["api_password"])
                
                # Test connection if API URL is provided
                if "api_url" in dc_config:
                    response = session.get(f"{dc_config['api_url']}/v1/cluster", verify=False)
                    if response.status_code == 200:
                        logger.info(f"Connected to Redis Enterprise API in datacenter {dc_name}")
                    else:
                        logger.warning(f"API connection test for datacenter {dc_name} returned status {response.status_code}")
                
                # Store session
                self.api_sessions[dc_name] = session
            
            except Exception as e:
                logger.error(f"Failed to initialize API session for datacenter {dc_name}: {e}")
    
    def start(self):
        """Start the monitoring thread."""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.warning("Monitoring thread already running")
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True
        )
        self.monitoring_thread.start()
        logger.info("Redis monitoring thread started")
    
    def stop(self):
        """Stop the monitoring thread."""
        self.running = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
        logger.info("Redis monitoring thread stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                # Monitor all instances
                for instance in self.config.instances:
                    self._monitor_instance(instance)
                
                # Sleep until next interval
                time.sleep(self.config.monitoring_interval)
            
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(5)  # Shorter sleep on error to recover faster
    
    def _monitor_instance(self, instance):
        """Monitor a specific Redis instance across all datacenters."""
        for dc_name, endpoint in instance.endpoints.items():
            try:
                # Skip if no client for this instance/DC
                if (instance.uid not in self.clients or 
                    dc_name not in self.clients[instance.uid]):
                    continue
                
                client = self.clients[instance.uid][dc_name]
                
                # Try to reconnect if needed
                if not hasattr(client, "connection") or client.connection is None:
                    try:
                        client = redis.Redis(
                            host=endpoint["host"],
                            port=endpoint["port"],
                            password=instance.password,
                            socket_timeout=5.0,
                            socket_connect_timeout=3.0,
                            decode_responses=True
                        )
                        self.clients[instance.uid][dc_name] = client
                    except Exception as e:
                        logger.error(f"Failed to reconnect to {instance.name} in {dc_name}: {e}")
                        continue
                
                # Measure response time
                start_time = time.time()
                ping_result = client.ping()
                latency_ms = (time.time() - start_time) * 1000
                
                if not ping_result:
                    # Failed to ping
                    self._update_error_status(instance.uid, dc_name, "Failed to ping Redis")
                    continue
                
                # Get Redis INFO
                info = client.info()
                
                # Extract key metrics
                used_memory = int(info.get("used_memory", 0))
                maxmemory = int(info.get("maxmemory", 1))
                memory_percent = (used_memory / maxmemory * 100) if maxmemory > 0 else 0
                
                # Redis hits/misses
                hits = int(info.get("keyspace_hits", 0))
                misses = int(info.get("keyspace_misses", 0))
                hit_rate = hits / (hits + misses) if hits + misses > 0 else 0
                
                # Get other metrics
                connected_clients = int(info.get("connected_clients", 0))
                ops_per_second = int(info.get("instantaneous_ops_per_sec", 0))
                
                # Get additional metrics from Redis Enterprise API if available
                api_metrics = self._get_api_metrics(instance.uid, dc_name)
                
                # Combine all metrics
                metrics = {
                    "timestamp": time.time(),
                    "instance_uid": instance.uid,
                    "instance_name": instance.name,
                    "datacenter": dc_name,
                    "latency_ms": latency_ms,
                    "memory_used_bytes": used_memory,
                    "memory_max_bytes": maxmemory,
                    "memory_used_percent": memory_percent,
                    "hit_rate": hit_rate,
                    "hits": hits,
                    "misses": misses,
                    "ops_per_second": ops_per_second,
                    "connected_clients": connected_clients,
                    "rejected_connections": int(info.get("rejected_connections", 0)),
                    "evicted_keys": int(info.get("evicted_keys", 0)),
                    "expired_keys": int(info.get("expired_keys", 0)),
                }
                
                # Add API metrics if available
                if api_metrics:
                    metrics.update(api_metrics)
                
                # Store metrics
                with self.lock:
                    self.metrics_history[instance.uid].append(metrics)
                    # Limit history size (keep last 1000 samples)
                    if len(self.metrics_history[instance.uid]) > 1000:
                        self.metrics_history[instance.uid] = self.metrics_history[instance.uid][-1000:]
                
                # Update health status based on metrics
                health_status = self._calculate_health_status(metrics)
                self.core.update_health_status(instance.uid, dc_name, health_status)
                
                # Pass metrics to anomaly detection module if available
                if hasattr(self.core, "anomaly_detector"):
                    self.core.anomaly_detector.process_metrics(instance.uid, dc_name, metrics)
            
            except Exception as e:
                logger.error(f"Error monitoring instance {instance.name} in datacenter {dc_name}: {e}")
                self._update_error_status(instance.uid, dc_name, str(e))
    
    def _update_error_status(self, instance_uid: str, dc_name: str, error_message: str):
        """Update instance health status with an error."""
        from redis_agent.core import HealthStatus
        
        status = HealthStatus(
            status="failed",
            can_serve_traffic=False,
            last_check=time.time(),
            consecutive_errors=1,  # Will be incremented by core
            error_message=error_message
        )
        
        self.core.update_health_status(instance_uid, dc_name, status)
    
    def _calculate_health_status(self, metrics: Dict[str, Any]):
        """Calculate health status based on metrics."""
        from redis_agent.core import HealthStatus
        
        # Create basic health status
        status = HealthStatus(
            latency_ms=metrics["latency_ms"],
            memory_used_percent=metrics["memory_used_percent"],
            hit_rate=metrics["hit_rate"],
            ops_per_second=metrics["ops_per_second"],
            connected_clients=metrics["connected_clients"],
            last_check=metrics["timestamp"],
            consecutive_errors=0
        )
        
        # Determine status based on thresholds
        is_healthy = True
        
        # Check latency
        if metrics["latency_ms"] > 100:  # More than 100ms
            is_healthy = False
            status.status = "degraded"
        
        # Check memory usage
        if metrics["memory_used_percent"] > 90:  # More than 90%
            is_healthy = False
            status.status = "degraded"
            
            # Critical if above 95%
            if metrics["memory_used_percent"] > 95:
                status.status = "failing"
                status.can_serve_traffic = False
        
        # Check rejected connections
        if metrics["rejected_connections"] > 0:
            is_healthy = False
            status.status = "degraded"
        
        # Set status to healthy if everything is good
        if is_healthy:
            status.status = "healthy"
        
        return status
    
    def _get_api_metrics(self, instance_uid: str, dc_name: str) -> Dict[str, Any]:
        """Get additional metrics from Redis Enterprise API if available."""
        if dc_name not in self.api_sessions:
            return {}
        
        try:
            # Check if this datacenter has API configured
            dc_config = self.config.datacenters.get(dc_name, {})
            if "api_url" not in dc_config:
                return {}
            
            # Find the database UID for this instance
            db_uid = None
            for instance in self.config.instances:
                if instance.uid == instance_uid:
                    db_uid = instance.uid
                    break
            
            if not db_uid:
                return {}
            
            # Make API request
            session = self.api_sessions[dc_name]
            api_url = dc_config["api_url"]
            
            # Try to get database stats
            response = session.get(f"{api_url}/v1/bdbs/{db_uid}/stats?interval=1sec", verify=False)
            
            if response.status_code != 200:
                logger.warning(f"Failed to get API metrics for {instance_uid} in {dc_name}: {response.status_code}")
                return {}
            
            # Process response
            data = response.json()
            api_metrics = {}
            
            # Extract metrics from response
            if "intervals" in data and data["intervals"]:
                latest = data["intervals"][-1]
                
                # Map Redis Enterprise metrics to our format
                metric_mapping = {
                    "total_req": "api_total_requests",
                    "read_req": "api_read_requests",
                    "write_req": "api_write_requests",
                    "total_connections": "api_total_connections",
                    "total_egress_bytes": "api_egress_bytes",
                    "total_ingress_bytes": "api_ingress_bytes",
                    "avg_latency": "api_avg_latency_ms",
                    "avg_read_latency": "api_avg_read_latency_ms",
                    "avg_write_latency": "api_avg_write_latency_ms"
                }
                
                for src_key, dest_key in metric_mapping.items():
                    if src_key in latest:
                        api_metrics[dest_key] = latest[src_key]
            
            return api_metrics
            
        except Exception as e:
            logger.error(f"Error getting API metrics for {instance_uid} in {dc_name}: {e}")
            return {}
    
    def get_latest_metrics(self, instance_uid: str, limit: int = 1) -> List[Dict[str, Any]]:
        """Get the latest metrics for an instance."""
        with self.lock:
            if instance_uid in self.metrics_history:
                return self.metrics_history[instance_uid][-limit:]
            return []
    
    def get_metrics_history(self, instance_uid: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get metrics history for an instance for the specified time window."""
        with self.lock:
            if instance_uid not in self.metrics_history:
                return []
            
            # Calculate cutoff time
            cutoff_time = time.time() - (minutes * 60)
            
            # Filter metrics by timestamp
            return [
                m for m in self.metrics_history[instance_uid]
                if m["timestamp"] >= cutoff_time
            ]
