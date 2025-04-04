#!/usr/bin/env python3
# redis_agent/elk_client.py - ELK client for retrieving client-side logs

import logging
import json
import threading
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger("redis-agent.elk")

class ELKClient:
    """Client for retrieving logs from Elasticsearch/Kibana."""
    
    def __init__(self, core_agent):
        """Initialize the ELK client.
        
        Args:
            core_agent: Reference to the core agent
        """
        self.core = core_agent
        self.config = core_agent.config.elk
        self.session = None
        self.logs_cache = {}  # instance_uid -> list of logs
        self.last_query_time = {}  # instance_uid -> timestamp
        self.lock = threading.RLock()
        
    def initialize(self):
        """Initialize the ELK client."""
        self._create_session()
        logger.info("ELK client initialized")
        
    def _create_session(self):
        """Create a requests session for ELK API."""
        self.session = requests.Session()
        
        # Add authentication if configured
        if "username" in self.config and "password" in self.config:
            self.session.auth = HTTPBasicAuth(self.config["username"], self.config["password"])
            
        # Add headers if configured
        if "headers" in self.config:
            self.session.headers.update(self.config["headers"])
            
        # Add TLS/SSL verification
        self.session.verify = self.config.get("verify_ssl", True)
        
    def get_client_logs(self, instance_uid: str, minutes: int = 30, max_logs: int = 1000, 
                       force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get client logs for a Redis instance from ELK.
        
        Args:
            instance_uid: Redis instance UID
            minutes: Time window in minutes
            max_logs: Maximum number of logs to retrieve
            force_refresh: Force refresh of cached logs
            
        Returns:
            List of log entries
        """
        with self.lock:
            current_time = time.time()
            
            # Check if we need to query ELK again
            last_query = self.last_query_time.get(instance_uid, 0)
            cache_ttl = self.config.get("cache_ttl", 300)  # 5 minutes default
            
            if force_refresh or (current_time - last_query > cache_ttl):
                # Query ELK for new logs
                logs = self._query_elk(instance_uid, minutes, max_logs)
                self.logs_cache[instance_uid] = logs
                self.last_query_time[instance_uid] = current_time
                return logs
            else:
                # Return cached logs
                return self.logs_cache.get(instance_uid, [])
                
    def _query_elk(self, instance_uid: str, minutes: int, max_logs: int) -> List[Dict[str, Any]]:
        """
        Query Elasticsearch for logs.
        
        Args:
            instance_uid: Redis instance UID
            minutes: Time window in minutes
            max_logs: Maximum number of logs to retrieve
            
        Returns:
            List of log entries
        """
        try:
            # Find instance name
            instance_name = None
            for instance in self.core.config.instances:
                if instance.uid == instance_uid:
                    instance_name = instance.name
                    break
            
            # Calculate time range
            now = datetime.utcnow()
            start_time = now - timedelta(minutes=minutes)
            
            # Format time for Elasticsearch
            start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            end_time_str = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            
            # Build Elasticsearch query
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_time_str,
                                        "lte": end_time_str
                                    }
                                }
                            },
                            {
                                "bool": {
                                    "should": [
                                        {
                                            "term": {
                                                "redis_instance.keyword": instance_uid
                                            }
                                        },
                                        {
                                            "term": {
                                                "redis_instance_name.keyword": instance_name
                                            }
                                        },
                                        {
                                            "query_string": {
                                                "query": f"message:*{instance_uid}* OR message:*{instance_name}*",
                                                "analyze_wildcard": True
                                            }
                                        }
                                    ],
                                    "minimum_should_match": 1
                                }
                            }
                        ]
                    }
                },
                "sort": [
                    {
                        "@timestamp": {
                            "order": "desc"
                        }
                    }
                ],
                "size": max_logs
            }
            
            # Add filters for client-side logs
            if self.config.get("client_logs_only", True):
                query["query"]["bool"]["must"].append({
                    "term": {
                        "log_source.keyword": "client"
                    }
                })
                
            # Add filters for error logs if requested
            if self.config.get("errors_only", False):
                query["query"]["bool"]["must"].append({
                    "bool": {
                        "should": [
                            {
                                "terms": {
                                    "level.keyword": ["ERROR", "SEVERE", "FATAL", "WARNING"]
                                }
                            },
                            {
                                "query_string": {
                                    "query": "message:*error* OR message:*exception* OR message:*timeout* OR message:*fail*",
                                    "analyze_wildcard": True
                                }
                            }
                        ],
                        "minimum_should_match": 1
                    }
                })
                
            # Make the request to Elasticsearch
            index_pattern = self.config.get("index_pattern", "logstash-*")
            url = f"{self.config['url']}/{index_pattern}/_search"
            
            response = self.session.post(
                url,
                json=query,
                timeout=self.config.get("timeout", 30)
            )
            
            # Parse the response
            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", {}).get("hits", [])
                
                # Extract logs from hits
                logs = []
                for hit in hits:
                    # Get the log data
                    source = hit.get("_source", {})
                    
                    # Add the document ID
                    source["_id"] = hit.get("_id")
                    
                    # Add to logs
                    logs.append(source)
                    
                logger.info(f"Retrieved {len(logs)} logs for instance {instance_uid} from ELK")
                return logs
            else:
                logger.error(f"Error querying ELK: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            logger.error(f"Error querying ELK: {e}")
            return []
            
    def analyze_client_errors(self, instance_uid: str, minutes: int = 30) -> Dict[str, Any]:
        """
        Analyze client logs for errors and patterns.
        
        Args:
            instance_uid: Redis instance UID
            minutes: Time window in minutes
            
        Returns:
            Analysis results
        """
        logs = self.get_client_logs(instance_uid, minutes)
        
        if not logs:
            return {
                "error_rate": 0,
                "error_count": 0,
                "total_logs": 0,
                "has_connection_errors": False,
                "has_timeout_errors": False,
                "has_memory_errors": False,
                "client_impact": "none"
            }
            
        # Count errors
        total_logs = len(logs)
        error_count = 0
        connection_errors = 0
        timeout_errors = 0
        memory_errors = 0
        authentication_errors = 0
        
        # Error patterns
        for log in logs:
            message = log.get("message", "").lower()
            level = log.get("level", "").upper()
            
            is_error = (
                level in ["ERROR", "SEVERE", "FATAL"] or
                "error" in message or
                "exception" in message
            )
            
            if is_error:
                error_count += 1
                
                # Categorize errors
                if "connection" in message or "connect" in message:
                    connection_errors += 1
                    
                if "timeout" in message or "timed out" in message:
                    timeout_errors += 1
                    
                if "memory" in message or "oom" in message or "out of memory" in message:
                    memory_errors += 1
                    
                if "auth" in message or "password" in message or "unauthorized" in message:
                    authentication_errors += 1
                    
        # Calculate error rate
        error_rate = error_count / total_logs if total_logs > 0 else 0
        
        # Determine client impact
        client_impact = "none"
        if error_rate > 0.5:
            client_impact = "severe"
        elif error_rate > 0.2:
            client_impact = "high"
        elif error_rate > 0.05:
            client_impact = "medium"
        elif error_rate > 0:
            client_impact = "low"
            
        # Calculate time distribution of errors
        timestamps = {}
        for log in logs:
            if log.get("@timestamp"):
                minute = log.get("@timestamp")[:16]  # YYYY-MM-DDTHH:MM
                if minute not in timestamps:
                    timestamps[minute] = {"total": 0, "errors": 0}
                timestamps[minute]["total"] += 1
                
                message = log.get("message", "").lower()
                level = log.get("level", "").upper()
                
                is_error = (
                    level in ["ERROR", "SEVERE", "FATAL"] or
                    "error" in message or
                    "exception" in message
                )
                
                if is_error:
                    timestamps[minute]["errors"] += 1
                    
        # Identify spikes in errors
        error_spikes = []
        for minute, counts in timestamps.items():
            if counts["total"] > 0 and counts["errors"] / counts["total"] > 0.5 and counts["errors"] >= 3:
                error_spikes.append(minute)
                
        # Prepare results
        results = {
            "error_rate": error_rate,
            "error_count": error_count,
            "total_logs": total_logs,
            "has_connection_errors": connection_errors > 0,
            "has_timeout_errors": timeout_errors > 0,
            "has_memory_errors": memory_errors > 0,
            "has_authentication_errors": authentication_errors > 0,
            "connection_error_count": connection_errors,
            "timeout_error_count": timeout_errors,
            "memory_error_count": memory_errors,
            "authentication_error_count": authentication_errors,
            "client_impact": client_impact,
            "error_distribution": timestamps,
            "error_spikes": error_spikes
        }
        
        return results
