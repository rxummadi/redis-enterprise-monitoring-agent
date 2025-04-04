#!/usr/bin/env python3
# redis_agent/failover.py - Failover module for Redis Enterprise

import logging
import threading
import time
import json
import boto3
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger("redis-agent.failover")

class FailoverProvider(ABC):
    """Abstract base class for failover providers"""
    
    @abstractmethod
    def perform_failover(self, instance_uid: str, from_dc: str, to_dc: str, instance_info: Dict[str, Any]) -> bool:
        """
        Perform failover from one datacenter to another.
        
        Args:
            instance_uid: Instance UID
            from_dc: Current active datacenter
            to_dc: Target datacenter to failover to
            instance_info: Additional instance information
            
        Returns:
            True if failover was successful, False otherwise
        """
        pass

class DNSFailoverProvider(FailoverProvider):
    """DNS-based failover provider (AWS Route53, Google Cloud DNS)"""
    
    def __init__(self, config):
        """Initialize the DNS failover provider.
        
        Args:
            config: Agent configuration
        """
        self.config = config
        self.dns_provider = self._create_dns_provider()
    
    def _create_dns_provider(self):
        """Create the DNS provider based on configuration."""
        provider_type = self.config.dns_provider
        dns_config = self.config.dns_config
        
        if provider_type == "route53":
            return Route53Provider(dns_config)
        elif provider_type == "clouddns":
            return CloudDNSProvider(dns_config)
        else:
            raise ValueError(f"Unsupported DNS provider: {provider_type}")
    
    def perform_failover(self, instance_uid: str, from_dc: str, to_dc: str, instance_info: Dict[str, Any]) -> bool:
        """Perform DNS-based failover."""
        # Find the DNS records to update
        dns_records = self._get_dns_records_for_instance(instance_uid, instance_info)
        
        if not dns_records:
            logger.error(f"No DNS records configured for instance {instance_uid}")
            return False
        
        # Get the target endpoint for the destination DC
        target_endpoint = self._get_endpoint_for_dc(instance_uid, to_dc, instance_info)
        
        if not target_endpoint:
            logger.error(f"No endpoint found for instance {instance_uid} in datacenter {to_dc}")
            return False
        
        # Update DNS records
        success = True
        for record in dns_records:
            record_type = record.get("type", "CNAME")
            record_name = record.get("name")
            ttl = record.get("ttl", 60)
            
            if not record_name:
                logger.error(f"Record name missing for instance {instance_uid}")
                success = False
                continue
            
            # Update the record
            try:
                result = self.dns_provider.update_record(
                    record_name=record_name,
                    record_type=record_type,
                    ttl=ttl,
                    value=target_endpoint
                )
                
                if result:
                    logger.info(f"Successfully updated DNS record {record_name} to {target_endpoint}")
                else:
                    logger.error(f"Failed to update DNS record {record_name}")
                    success = False
            
            except Exception as e:
                logger.error(f"Error updating DNS record {record_name}: {e}")
                success = False
        
        return success
    
    def _get_dns_records_for_instance(self, instance_uid: str, instance_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get DNS records that need to be updated for an instance."""
        # Check instance-specific DNS records
        instance_name = instance_info.get("name", "")
        
        # Instance-specific records have priority
        dns_records = []
        
        for record in self.config.dns_config.get("records", []):
            # Check if this record is for our instance
            record_instance = record.get("instance_uid", "")
            record_instance_name = record.get("instance_name", "")
            
            if (record_instance and record_instance == instance_uid) or \
               (record_instance_name and record_instance_name == instance_name):
                dns_records.append(record)
        
        # If no instance-specific records found, check for default records
        if not dns_records:
            for record in self.config.dns_config.get("records", []):
                if not record.get("instance_uid") and not record.get("instance_name"):
                    # This is a default record (not assigned to a specific instance)
                    # Add instance-specific information
                    modified_record = record.copy()
                    modified_record["instance_uid"] = instance_uid
                    modified_record["instance_name"] = instance_name
                    dns_records.append(modified_record)
        
        return dns_records
    
    def _get_endpoint_for_dc(self, instance_uid: str, dc_name: str, instance_info: Dict[str, Any]) -> str:
        """Get the endpoint hostname for an instance in a specific datacenter."""
        # Check if endpoints are explicitly defined in the instance info
        endpoints = instance_info.get("endpoints", {})
        
        if dc_name in endpoints:
            endpoint = endpoints[dc_name]
            if "host" in endpoint:
                return endpoint["host"]
        
        # If not found in instance info, check if we have a mapping in DNS config
        endpoint_map = self.config.dns_config.get("endpoint_map", {})
        
        if instance_uid in endpoint_map and dc_name in endpoint_map[instance_uid]:
            return endpoint_map[instance_uid][dc_name]
        
        # If still not found, use a default format
        instance_name = instance_info.get("name", instance_uid)
        return f"{instance_name}.{dc_name}.example.com"  # Default fallback format

class Route53Provider:
    """AWS Route 53 DNS provider implementation"""
    
    def __init__(self, config):
        """Initialize the Route 53 provider.
        
        Args:
            config: DNS configuration
        """
        self.config = config
        self.route53 = self._create_route53_client()
    
    def _create_route53_client(self):
        """Create Route 53 client."""
        # Check for explicit credentials
        if "aws_access_key" in self.config and "aws_secret_key" in self.config:
            return boto3.client(
                'route53',
                aws_access_key_id=self.config["aws_access_key"],
                aws_secret_access_key=self.config["aws_secret_key"],
                region_name=self.config.get("aws_region", "us-east-1")
            )
        
        # Use default credentials (environment, IAM role, etc.)
        return boto3.client('route53')
    
    def update_record(self, record_name: str, record_type: str, ttl: int, value: str) -> bool:
        """Update a Route 53 DNS record."""
        try:
            # Get the hosted zone ID
            zone_id = self.config.get("zone_id")
            if not zone_id:
                logger.error("No zone_id specified in Route 53 configuration")
                return False
            
            # Ensure record name ends with a dot for Route 53
            if not record_name.endswith('.'):
                record_name = f"{record_name}."
            
            # For CNAME records, ensure value ends with a dot
            if record_type == "CNAME" and not value.endswith('.'):
                value = f"{value}."
            
            # Create the change batch
            response = self.route53.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': 'UPSERT',
                            'ResourceRecordSet': {
                                'Name': record_name,
                                'Type': record_type,
                                'TTL': ttl,
                                'ResourceRecords': [
                                    {
                                        'Value': value
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
            
            logger.info(f"DNS update initiated: {response['ChangeInfo']['Id']}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating Route 53 record: {e}")
            return False

class CloudDNSProvider:
    """Google Cloud DNS provider implementation"""
    
    def __init__(self, config):
        """Initialize the Cloud DNS provider.
        
        Args:
            config: DNS configuration
        """
        self.config = config
        # Note: Actual implementation would use google-cloud-dns library
        # For simplicity, we'll just log what would happen
    
    def update_record(self, record_name: str, record_type: str, ttl: int, value: str) -> bool:
        """Update a Cloud DNS record."""
        # This is a simplified implementation - in production, use google-cloud-dns
        try:
            project_id = self.config.get("project_id")
            zone_name = self.config.get("zone_name")
            
            if not project_id or not zone_name:
                logger.error("Missing project_id or zone_name in Cloud DNS configuration")
                return False
            
            # Log the operation
            logger.info(f"Would update Cloud DNS record: {record_name} to {value} in zone {zone_name}")
            
            # Simulate success
            return True
            
        except Exception as e:
            logger.error(f"Error updating Cloud DNS record: {e}")
            return False

class FailoverDecision:
    """Represents a failover decision with reasoning and confidence."""
    
    def __init__(self, instance_uid: str, instance_name: str, 
                from_dc: str, to_dc: str, confidence: float, 
                reason: str, metrics: Optional[Dict[str, Any]] = None):
        """Initialize a failover decision.
        
        Args:
            instance_uid: Instance UID
            instance_name: Instance name
            from_dc: Current active datacenter
            to_dc: Target datacenter for failover
            confidence: Confidence level (0.0-1.0)
            reason: Reason for failover decision
            metrics: Related metrics
        """
        self.instance_uid = instance_uid
        self.instance_name = instance_name
        self.from_dc = from_dc
        self.to_dc = to_dc
        self.confidence = confidence
        self.reason = reason
        self.metrics = metrics or {}
        self.timestamp = time.time()
        self.id = f"{instance_uid}_{int(self.timestamp)}"

class FailoverManager:
    """Manager for making and executing failover decisions"""
    
    def __init__(self, core_agent):
        """Initialize the failover manager.
        
        Args:
            core_agent: Reference to the core agent
        """
        self.core = core_agent
        self.config = core_agent.config
        self.provider = None
        self.decision_thread = None
        self.running = False
        self.decisions_history = []
        self.last_failover_time = {}  # instance_uid -> timestamp
        self.lock = threading.RLock()
    
    def initialize(self):
        """Initialize the failover manager."""
        # Create failover provider
        if self.config.failover_provider == "dns":
            self.provider = DNSFailoverProvider(self.config)
        else:
            raise ValueError(f"Unsupported failover provider: {self.config.failover_provider}")
        
        # Initialize last failover time
        for instance in self.config.instances:
            self.last_failover_time[instance.uid] = 0
        
        logger.info(f"Initialized failover manager with {self.config.failover_provider} provider")
    
    def start(self):
        """Start the decision thread."""
        if self.decision_thread and self.decision_thread.is_alive():
            logger.warning("Decision thread already running")
            return
        
        self.running = True
        self.decision_thread = threading.Thread(
            target=self._decision_loop,
            daemon=True
        )
        self.decision_thread.start()
        logger.info("Failover decision thread started")
    
    def stop(self):
        """Stop the decision thread."""
        self.running = False
        if self.decision_thread and self.decision_thread.is_alive():
            self.decision_thread.join(timeout=5)
        logger.info("Failover decision thread stopped")
    
    def _decision_loop(self):
        """Main loop for making failover decisions."""
        # Initial sleep to allow health monitoring to collect data
        time.sleep(60)
        
        while self.running:
            try:
                # Check all instances for potential failover
                for instance in self.config.instances:
                    self._check_instance_for_failover(instance)
                
                # Sleep until next check
                time.sleep(self.config.decision_interval)
            
            except Exception as e:
                logger.error(f"Error in decision loop: {e}")
                time.sleep(30)  # Shorter sleep on error
    
    def _check_instance_for_failover(self, instance):
        """Check if an instance requires failover."""
        instance_uid = instance.uid
        active_dc = instance.active_dc
        
        # Get current health status
        health_status = self.core.get_instance_health(instance_uid)
        
        # Skip if no health status available
        if not health_status:
            return
        
        # Check if the active DC is having problems
        active_dc_status = health_status.get(active_dc)
        if not active_dc_status:
            logger.warning(f"No health status for active DC {active_dc}")
            return
        
        # Check if the active DC can serve traffic
        if active_dc_status.can_serve_traffic:
            # Everything is fine
            return
        
        # Find the best alternative DC
        alternative_dc = self._find_best_alternative_dc(instance, health_status)
        
        if not alternative_dc:
            logger.warning(f"No healthy alternative DC found for instance {instance.name}")
            return
        
        # Create failover decision
        decision = self._make_failover_decision(instance, active_dc, alternative_dc, health_status)
        
        # Check if we should execute the failover
        if decision.confidence >= self.config.failover_confidence_threshold:
            if self.config.auto_failover:
                self._execute_failover(decision)
            else:
                logger.warning(f"Automatic failover disabled. Manual intervention required: {decision.reason}")
                self._send_manual_intervention_alert(decision)
        else:
            logger.info(f"Failover confidence too low ({decision.confidence:.2f}): {decision.reason}")
    
    def _find_best_alternative_dc(self, instance, health_status):
        """Find the best alternative datacenter for failover."""
        active_dc = instance.active_dc
        best_dc = None
        best_score = -1
        
        for dc_name, status in health_status.items():
            # Skip the active DC
            if dc_name == active_dc:
                continue
            
            # Skip DCs that can't serve traffic
            if not status.can_serve_traffic:
                continue
            
            # Calculate a score based on health metrics
            score = self._calculate_dc_score(status)
            
            if score > best_score:
                best_score = score
                best_dc = dc_name
        
        return best_dc
    
    def _calculate_dc_score(self, status):
        """Calculate a health score for a datacenter."""
        score = 0
        
        # Higher score is better
        if status.status == "healthy":
            score += 100
        elif status.status == "degraded":
            score += 50
        
        # Penalize high latency
        if status.latency_ms > 0:
            latency_score = max(0, 50 - status.latency_ms / 2)  # 0ms = 50 points, 100ms = 0 points
            score += latency_score
        
        # Penalize high memory usage
        if status.memory_used_percent < 80:
            memory_score = (100 - status.memory_used_percent) / 2  # 0% = 50 points, 100% = 0 points
            score += memory_score
        
        # Reward high hit rate
        if status.hit_rate > 0:
            hit_rate_score = status.hit_rate * 30  # 100% = 30 points
            score += hit_rate_score
        
        # Penalize consecutive errors
        score -= status.consecutive_errors * 10
        
        # Penalize consecutive anomalies
        score -= status.consecutive_anomalies * 5
        
        return score
    
    def _make_failover_decision(self, instance, from_dc, to_dc, health_status):
        """Create a failover decision with reasoning and confidence."""
        # Extract relevant health information
        active_status = health_status.get(from_dc)
        target_status = health_status.get(to_dc)
        
        if not active_status or not target_status:
            return FailoverDecision(
                instance_uid=instance.uid,
                instance_name=instance.name,
                from_dc=from_dc,
                to_dc=to_dc,
                confidence=0.0,
                reason="Missing health status for one or both datacenters",
                metrics={}
            )
        
        # Start with base confidence
        confidence = 0.5
        reasons = []
        
        # Check for critical conditions
        if active_status.status == "failed":
            confidence += 0.4
            reasons.append(f"Active DC ({from_dc}) has failed")
        
        if active_status.consecutive_errors >= 3:
            confidence += 0.3
            reasons.append(f"Active DC has {active_status.consecutive_errors} consecutive errors")
        
        # Check less critical but concerning conditions
        if active_status.status == "failing":
            confidence += 0.2
            reasons.append(f"Active DC ({from_dc}) is failing")
        
        if active_status.memory_used_percent > 95:
            confidence += 0.2
            reasons.append(f"Active DC memory usage critical: {active_status.memory_used_percent:.1f}%")
        
        if active_status.latency_ms > 500:
            confidence += 0.15
            reasons.append(f"Active DC latency critical: {active_status.latency_ms:.1f}ms")
        
        # Check if target DC is significantly better
        if target_status.status == "healthy" and active_status.status != "healthy":
            confidence += 0.1
            reasons.append(f"Target DC ({to_dc}) is healthy")
        
        # Reduce confidence based on recent failovers (avoid flapping)
        last_failover = self.last_failover_time.get(instance.uid, 0)
        time_since_last_failover = time.time() - last_failover
        
        if time_since_last_failover < 3600:  # Less than 1 hour
            confidence -= 0.3
            reasons.append(f"Recent failover ({time_since_last_failover:.0f} seconds ago)")
        elif time_since_last_failover < 86400:  # Less than 1 day
            confidence -= 0.1
            reasons.append(f"Failover in last 24 hours")
        
        # Ensure confidence is between 0 and 1
        confidence = max(0.0, min(1.0, confidence))
        
        # Create the decision object
        metrics = {
            "active_dc": {
                "status": active_status.status,
                "latency_ms": active_status.latency_ms,
                "memory_used_percent": active_status.memory_used_percent,
                "hit_rate": active_status.hit_rate,
                "consecutive_errors": active_status.consecutive_errors,
                "can_serve_traffic": active_status.can_serve_traffic
            },
            "target_dc": {
                "status": target_status.status,
                "latency_ms": target_status.latency_ms,
                "memory_used_percent": target_status.memory_used_percent,
                "hit_rate": target_status.hit_rate,
                "consecutive_errors": target_status.consecutive_errors,
                "can_serve_traffic": target_status.can_serve_traffic
            }
        }
        
        reason = "; ".join(reasons)
        
        return FailoverDecision(
            instance_uid=instance.uid,
            instance_name=instance.name,
            from_dc=from_dc,
            to_dc=to_dc,
            confidence=confidence,
            reason=reason,
            metrics=metrics
        )
    
    def _execute_failover(self, decision):
        """Execute a failover decision."""
        logger.info(f"Executing failover for {decision.instance_name} from {decision.from_dc} to {decision.to_dc}")
        
        try:
            # Find instance info
            instance_info = None
            for instance in self.config.instances:
                if instance.uid == decision.instance_uid:
                    instance_info = {
                        "name": instance.name,
                        "uid": instance.uid,
                        "endpoints": instance.endpoints
                    }
                    break
            
            if not instance_info:
                logger.error(f"Instance info not found for {decision.instance_uid}")
                return False
            
            # Perform the failover
            success = self.provider.perform_failover(
                instance_uid=decision.instance_uid,
                from_dc=decision.from_dc,
                to_dc=decision.to_dc,
                instance_info=instance_info
            )
            
            if success:
                # Update the active DC in the core agent
                self.core.switch_active_dc(decision.instance_uid, decision.to_dc)
                
                # Update the last failover time
                self.last_failover_time[decision.instance_uid] = time.time()
                
                # Send alert
                self._send_failover_alert(decision, success=True)
                
                # Add to history
                with self.lock:
                    self.decisions_history.append(decision)
                    # Limit history size
                    if len(self.decisions_history) > 100:
                        self.decisions_history = self.decisions_history[-100:]
                
                logger.info(f"Failover successful for {decision.instance_name} to {decision.to_dc}")
                return True
            else:
                logger.error(f"Failover failed for {decision.instance_name} to {decision.to_dc}")
                self._send_failover_alert(decision, success=False)
                return False
        
        except Exception as e:
            logger.error(f"Error executing failover: {e}")
            self._send_failover_alert(decision, success=False, error=str(e))
            return False
    
    def _send_failover_alert(self, decision, success=True, error=None):
        """Send an alert about a failover event."""
        if not hasattr(self.core, "alerting"):
            return
        
        severity = "info" if success else "error"
        alert_type = "failover_succeeded" if success else "failover_failed"
        
        message = f"Failover {'succeeded' if success else 'failed'} for {decision.instance_name}"
        if not success and error:
            message += f": {error}"
        
        details = {
            "instance_uid": decision.instance_uid,
            "instance_name": decision.instance_name,
            "from_dc": decision.from_dc,
            "to_dc": decision.to_dc,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "metrics": decision.metrics,
            "timestamp": decision.timestamp
        }
        
        if error:
            details["error"] = error
        
        self.core.alerting.send_alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details
        )
    
    def _send_manual_intervention_alert(self, decision):
        """Send an alert requesting manual intervention."""
        if not hasattr(self.core, "alerting"):
            return
        
        message = f"Manual failover required for {decision.instance_name} from {decision.from_dc} to {decision.to_dc}"
        
        details = {
            "instance_uid": decision.instance_uid,
            "instance_name": decision.instance_name,
            "from_dc": decision.from_dc,
            "to_dc": decision.to_dc,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "metrics": decision.metrics,
            "timestamp": decision.timestamp
        }
        
        self.core.alerting.send_alert(
            alert_type="manual_failover_required",
            severity="warning",
            message=message,
            details=details
        )
    
    def get_decision_history(self):
        """Get the history of failover decisions."""
        with self.lock:
            return self.decisions_history.copy()
    
    def perform_manual_failover(self, instance_uid: str, target_dc: str) -> bool:
        """Perform a manual failover for an instance.
        
        Args:
            instance_uid: Instance UID
            target_dc: Target datacenter
            
        Returns:
            True if successful, False otherwise
        """
        # Find instance
        instance = None
        for inst in self.config.instances:
            if inst.uid == instance_uid:
                instance = inst
                break
        
        if not instance:
            logger.error(f"Instance {instance_uid} not found")
            return False
        
        # Create decision
        decision = FailoverDecision(
            instance_uid=instance_uid,
            instance_name=instance.name,
            from_dc=instance.active_dc,
            to_dc=target_dc,
            confidence=1.0,  # Maximum confidence for manual failover
            reason="Manual failover requested",
            metrics={}
        )
        
        # Execute failover
        return self._execute_failover(decision)
