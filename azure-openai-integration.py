#!/usr/bin/env python3
# redis_agent/azure_ai.py - Azure OpenAI integration for decision making

import os
import time
import json
import logging
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

import openai
import requests
from openai import AzureOpenAI

logger = logging.getLogger("redis-agent.azure-ai")

class AzureOpenAIDecisionMaker:
    """Use Azure OpenAI to make intelligent failover decisions"""
    
    def __init__(self, core_agent):
        """Initialize the Azure OpenAI integration.
        
        Args:
            core_agent: Reference to the core agent
        """
        self.core = core_agent
        self.config = core_agent.config
        self.azure_config = self.config.azure_openai
        self.client = self._init_azure_openai_client()
        self.lock = threading.RLock()
        self.last_consultation_time = {}  # instance_uid -> timestamp
        self.last_decision = {}  # instance_uid -> decision dict
        
    def _init_azure_openai_client(self):
        """Initialize the Azure OpenAI client."""
        try:
            # Initialize the Azure OpenAI client
            client = AzureOpenAI(
                api_key=self.azure_config.get("api_key", os.environ.get("AZURE_OPENAI_API_KEY")),
                api_version=self.azure_config.get("api_version", "2023-05-15"),
                azure_endpoint=self.azure_config.get("endpoint", os.environ.get("AZURE_OPENAI_ENDPOINT"))
            )
            
            # Test connection with a simple request
            if self._test_connection(client):
                logger.info(f"Successfully connected to Azure OpenAI")
                return client
            else:
                logger.error(f"Failed to connect to Azure OpenAI")
                return None
                
        except Exception as e:
            logger.error(f"Error initializing Azure OpenAI client: {e}")
            return None
            
    def _test_connection(self, client):
        """Test the connection to Azure OpenAI."""
        try:
            # Send a simple completion request to test the connection
            response = client.chat.completions.create(
                model=self.azure_config.get("model", "gpt-4"),
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for Redis monitoring."},
                    {"role": "user", "content": "Test connection"}
                ],
                max_tokens=10
            )
            return True
        except Exception as e:
            logger.error(f"Test connection failed: {e}")
            return False
            
    def analyze_situation(self, instance_uid: str, metrics: Dict[str, Any], 
                         elk_logs: List[Dict[str, Any]], health_statuses: Dict[str, Any]) -> Dict[str, Any]:
        """
        Consults Azure OpenAI to analyze Redis situation and recommend actions.
        
        Args:
            instance_uid: The Redis instance UID
            metrics: Current metrics data
            elk_logs: Recent client logs from ELK
            health_statuses: Health status of all datacenters
            
        Returns:
            Decision dictionary with recommendation and confidence
        """
        if not self.client:
            logger.error("Azure OpenAI client not initialized")
            return {
                "recommendation": "no_action",
                "confidence": 0.0,
                "reason": "Azure OpenAI client not initialized"
            }
            
        # Rate limit the Azure OpenAI consultations
        # Don't consult more than once per 5 minutes for the same instance
        current_time = time.time()
        last_time = self.last_consultation_time.get(instance_uid, 0)
        
        if current_time - last_time < 300:  # 5 minutes in seconds
            # Return the last decision if available
            if instance_uid in self.last_decision:
                return self.last_decision[instance_uid]
            else:
                return {
                    "recommendation": "no_action",
                    "confidence": 0.0,
                    "reason": "Rate limited"
                }
                
        # Prepare the context for the AI model
        context = self._prepare_ai_context(instance_uid, metrics, elk_logs, health_statuses)
        
        try:
            # Send the request to Azure OpenAI
            response = self.client.chat.completions.create(
                model=self.azure_config.get("model", "gpt-4"),
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": context}
                ],
                temperature=0.2,  # Low temperature for more deterministic responses
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            # Parse the response
            response_text = response.choices[0].message.content
            try:
                decision = json.loads(response_text)
                
                # Validate the decision
                if not self._validate_decision(decision):
                    logger.error(f"Invalid decision from Azure OpenAI: {decision}")
                    decision = {
                        "recommendation": "no_action",
                        "confidence": 0.0,
                        "reason": "Invalid response from AI"
                    }
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Azure OpenAI response: {response_text}")
                decision = {
                    "recommendation": "no_action",
                    "confidence": 0.0,
                    "reason": "Failed to parse AI response"
                }
                
            # Update last consultation time and decision
            self.last_consultation_time[instance_uid] = current_time
            self.last_decision[instance_uid] = decision
            
            return decision
            
        except Exception as e:
            logger.error(f"Error consulting Azure OpenAI: {e}")
            return {
                "recommendation": "no_action",
                "confidence": 0.0,
                "reason": f"Error: {str(e)}"
            }
            
    def _prepare_ai_context(self, instance_uid: str, metrics: Dict[str, Any], 
                          elk_logs: List[Dict[str, Any]], health_statuses: Dict[str, Any]) -> str:
        """
        Prepares a context message for the AI model.
        
        Args:
            instance_uid: The Redis instance UID
            metrics: Current metrics data
            elk_logs: Recent client logs from ELK
            health_statuses: Health status of all datacenters
            
        Returns:
            Formatted context string
        """
        # Find instance info
        instance_name = "unknown"
        active_dc = "unknown"
        for instance in self.config.instances:
            if instance.uid == instance_uid:
                instance_name = instance.name
                active_dc = instance.active_dc
                break
                
        # Format metrics
        metrics_str = json.dumps(metrics, indent=2)
        
        # Format health statuses
        health_str = json.dumps(health_statuses, indent=2)
        
        # Format client logs (limited to most relevant)
        relevant_logs = self._extract_relevant_logs(elk_logs, instance_uid)
        logs_str = json.dumps(relevant_logs, indent=2)
        
        # Calculate summary stats from logs
        log_stats = self._calculate_log_stats(elk_logs, instance_uid)
        log_stats_str = json.dumps(log_stats, indent=2)
        
        # Build the context message
        context = f"""
I need to analyze the following Redis Enterprise instance situation and decide if failover is needed:

INSTANCE INFORMATION:
- Name: {instance_name}
- ID: {instance_uid}
- Current Active DC: {active_dc}

CURRENT METRICS:
{metrics_str}

HEALTH STATUS ACROSS DATACENTERS:
{health_str}

CLIENT LOG SUMMARY STATISTICS:
{log_stats_str}

SAMPLE CLIENT LOGS:
{logs_str}

Based on this information, I need you to determine if a failover is needed, and if so, which datacenter should become the new active datacenter.
Respond with a JSON object containing your recommendation and reasoning.
        """
        
        return context
        
    def _get_system_prompt(self) -> str:
        """Returns the system prompt for the AI model."""
        return """You are an expert Redis database monitoring assistant that analyzes Redis metrics and client logs to determine if failover to another datacenter is needed.

Your task is to analyze the provided Redis metrics, health status, and client logs, and determine:
1. If failover is needed based on performance degradation or errors
2. Which datacenter should become the new active datacenter if failover is needed
3. How confident you are in this decision

Consider these factors in your analysis:
- Server-side metrics like latency, memory usage, hit rate, and errors
- Client-side logs showing connection errors, timeouts, or retries
- The relative health of alternative datacenters
- The potential impact of a failover (disruption vs benefit)

Avoid recommending failover unless there's strong evidence it will improve the situation. Look for corroborating evidence between server metrics and client logs.

YOUR RESPONSE MUST BE A VALID JSON OBJECT with these keys:
- recommendation: One of: "failover", "no_action", "monitor", "manual_review"
- target_dc: (Only if recommendation is "failover") Name of the recommended target datacenter
- confidence: Numeric value between 0 and 1 indicating confidence in your recommendation
- reason: Brief explanation of your reasoning
- potential_impact: Brief assessment of the impact of your recommendation
- primary_indicators: Array of the main metrics/logs that influenced your decision
"""

    def _validate_decision(self, decision: Dict[str, Any]) -> bool:
        """
        Validates the decision from Azure OpenAI.
        
        Args:
            decision: The decision dictionary from Azure OpenAI
            
        Returns:
            True if decision is valid, False otherwise
        """
        required_keys = ["recommendation", "confidence", "reason"]
        
        # Check required keys
        for key in required_keys:
            if key not in decision:
                return False
                
        # Validate recommendation value
        valid_recommendations = ["failover", "no_action", "monitor", "manual_review"]
        if decision["recommendation"] not in valid_recommendations:
            return False
            
        # Validate confidence
        try:
            confidence = float(decision["confidence"])
            if confidence < 0 or confidence > 1:
                return False
        except (ValueError, TypeError):
            return False
            
        # Check for target_dc if recommendation is failover
        if decision["recommendation"] == "failover" and "target_dc" not in decision:
            return False
            
        return True
        
    def _extract_relevant_logs(self, logs: List[Dict[str, Any]], instance_uid: str, max_logs: int = 10) -> List[Dict[str, Any]]:
        """
        Extracts the most relevant logs for a Redis instance from ELK logs.
        
        Args:
            logs: List of log entries from ELK
            instance_uid: The Redis instance UID
            max_logs: Maximum number of logs to include
            
        Returns:
            List of the most relevant log entries
        """
        # Filter logs for this instance
        instance_logs = [log for log in logs if log.get("redis_instance") == instance_uid or instance_uid in log.get("message", "")]
        
        # Prioritize logs with errors or high latency
        error_logs = [log for log in instance_logs if 
                     log.get("level") in ["ERROR", "SEVERE", "FATAL"] or 
                     "error" in log.get("message", "").lower() or 
                     "timeout" in log.get("message", "").lower() or 
                     "exception" in log.get("message", "").lower()]
        
        # Prioritize recent logs
        recent_logs = sorted(instance_logs, key=lambda x: x.get("@timestamp", 0), reverse=True)
        
        # Combine error logs and recent logs, prioritizing errors
        combined_logs = []
        combined_logs.extend(error_logs[:max_logs//2])
        
        # Add recent logs that aren't already included
        error_ids = {log.get("_id") for log in combined_logs}
        for log in recent_logs:
            if log.get("_id") not in error_ids and len(combined_logs) < max_logs:
                combined_logs.append(log)
                
        return combined_logs[:max_logs]
        
    def _calculate_log_stats(self, logs: List[Dict[str, Any]], instance_uid: str) -> Dict[str, Any]:
        """
        Calculates summary statistics from client logs.
        
        Args:
            logs: List of log entries from ELK
            instance_uid: The Redis instance UID
            
        Returns:
            Dictionary with log statistics
        """
        # Filter logs for this instance
        instance_logs = [log for log in logs if log.get("redis_instance") == instance_uid or instance_uid in log.get("message", "")]
        
        # Calculate stats
        stats = {
            "total_logs": len(instance_logs),
            "error_count": 0,
            "timeout_count": 0,
            "retry_count": 0,
            "latency_stats": {
                "min": None,
                "max": None,
                "avg": None
            },
            "error_rate": 0.0,
            "logs_per_minute": {},
            "error_types": {}
        }
        
        # Count error types
        for log in instance_logs:
            # Check for errors
            if log.get("level") in ["ERROR", "SEVERE", "FATAL"] or "error" in log.get("message", "").lower():
                stats["error_count"] += 1
                
                # Categorize error type
                message = log.get("message", "").lower()
                if "timeout" in message:
                    stats["timeout_count"] += 1
                    error_type = "timeout"
                elif "connection" in message:
                    error_type = "connection"
                elif "memory" in message:
                    error_type = "memory"
                elif "authentication" in message:
                    error_type = "auth"
                else:
                    error_type = "other"
                    
                stats["error_types"][error_type] = stats["error_types"].get(error_type, 0) + 1
                
            # Check for retries
            if "retry" in log.get("message", "").lower():
                stats["retry_count"] += 1
                
            # Extract latency if available
            latency = log.get("latency_ms")
            if latency is not None:
                try:
                    latency = float(latency)
                    if stats["latency_stats"]["min"] is None or latency < stats["latency_stats"]["min"]:
                        stats["latency_stats"]["min"] = latency
                    if stats["latency_stats"]["max"] is None or latency > stats["latency_stats"]["max"]:
                        stats["latency_stats"]["max"] = latency
                except (ValueError, TypeError):
                    pass
                    
            # Group by minute for timeline analysis
            timestamp = log.get("@timestamp")
            if timestamp:
                try:
                    minute = timestamp[:16]  # YYYY-MM-DDTHH:MM
                    stats["logs_per_minute"][minute] = stats["logs_per_minute"].get(minute, 0) + 1
                except:
                    pass
                    
        # Calculate derived stats
        if stats["total_logs"] > 0:
            stats["error_rate"] = stats["error_count"] / stats["total_logs"]
            
        # Calculate average latency
        latencies = [float(log.get("latency_ms")) for log in instance_logs if log.get("latency_ms") is not None]
        if latencies:
            stats["latency_stats"]["avg"] = sum(latencies) / len(latencies)
            
        return stats
