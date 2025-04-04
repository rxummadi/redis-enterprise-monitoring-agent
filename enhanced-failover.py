#!/usr/bin/env python3
# redis_agent/enhanced_failover.py - Enhanced failover with Azure OpenAI and ELK integration

import logging
import threading
import time
import json
from typing import Dict, List, Any, Optional

from redis_agent.failover import FailoverManager, FailoverDecision

logger = logging.getLogger("redis-agent.enhanced-failover")

class EnhancedFailoverManager(FailoverManager):
    """Enhanced failover manager with Azure OpenAI and ELK integration"""
    
    def initialize(self):
        """Initialize the enhanced failover manager."""
        # Initialize the parent class
        super().initialize()
        
        # Track consecutive AI recommendations
        self.ai_recommendations = {}  # instance_uid -> list of recommendations
        
        logger.info("Enhanced failover manager initialized")
        
    def _check_instance_for_failover(self, instance):
        """
        Enhanced check if an instance requires failover, using Azure OpenAI and ELK logs.
        
        Args:
            instance: Redis instance
        """
        instance_uid = instance.uid
        active_dc = instance.active_dc
        
        # Get current health status
        health_status = self.core.get_instance_health(instance_uid)
        
        # Skip if no health status available
        if not health_status:
            return
            
        # Get latest metrics for instance
        if hasattr(self.core, "monitoring"):
            latest_metrics = self.core.monitoring.get_latest_metrics(instance_uid, limit=1)
            metrics = latest_metrics[0] if latest_metrics else {}
        else:
            metrics = {}
            
        # Get client logs from ELK if available
        if hasattr(self.core, "elk_client"):
            client_logs = self.core.elk_client.get_client_logs(instance_uid, minutes=30)
            client_error_analysis = self.core.elk_client.analyze_client_errors(instance_uid, minutes=30)
        else:
            client_logs = []
            client_error_analysis = {}
            
        # Check if we should consult the AI
        should_consult_ai = self._should_consult_ai(instance_uid, health_status, metrics, client_error_analysis)
        
        if should_consult_ai:
            # Consult Azure OpenAI for decision
            if hasattr(self.core, "ai_advisor"):
                ai_decision = self.core.ai_advisor.analyze_situation(
                    instance_uid=instance_uid,
                    metrics=metrics,
                    elk_logs=client_logs,
                    health_statuses=health_status
                )
                
                # Store the AI recommendation
                self._track_ai_recommendation(instance_uid, ai_decision)
                
                # Check if we should execute a failover based on AI recommendation
                if self._should_execute_ai_recommendation(instance_uid, ai_decision):
                    target_dc = ai_decision.get("target_dc")
                    confidence = ai_decision.get("confidence", 0.0)
                    reason = ai_decision.get("reason", "AI recommendation")
                    
                    # Create failover decision
                    decision = FailoverDecision(
                        instance_uid=instance_uid,
                        instance_name=instance.name,
                        from_dc=active_dc,
                        to_dc=target_dc,
                        confidence=confidence,
                        reason=f"AI recommended: {reason}",
                        metrics=metrics
                    )
                    
                    # Check if we should execute the failover
                    if self.config.auto_failover and confidence >= self.config.failover_confidence_threshold:
                        self._execute_failover(decision)
                    else:
                        logger.warning(f"AI recommended failover but confidence {confidence} is below threshold or auto-failover is disabled: {reason}")
                        self._send_manual_intervention_alert(decision)
            else:
                # Fall back to standard approach if AI advisor not available
                super()._check_instance_for_failover(instance)
        else:
            # Use standard approach
            super()._check_instance_for_failover(instance)
    
    def _should_consult_ai(self, instance_uid: str, health_status: Dict[str, Any], 
                          metrics: Dict[str, Any], client_error_analysis: Dict[str, Any]) -> bool:
        """
        Determine if we should consult Azure OpenAI for this instance.
        
        Args:
            instance_uid: Instance UID
            health_status: Health status data
            metrics: Current metrics
            client_error_analysis: Client error analysis from ELK
            
        Returns:
            True if we should consult AI, False otherwise
        """
        if not hasattr(self.core, "ai_advisor"):
            return False
            
        # Check if active DC has issues
        active_dc = None
        for instance in self.core.config.instances:
            if instance.uid == instance_uid:
                active_dc = instance.active_dc
                break
                
        if not active_dc or active_dc not in health_status:
            return False
            
        active_status = health_status[active_dc]
        
        # Check for critical conditions that would definitely warrant AI consultation
        if active_status.status in ["failing", "failed"]:
            return True
            
        if active_status.consecutive_errors >= 2:
            return True
            
        if active_status.is_anomaly and active_status.anomaly_score > 0.7:
            return True
            
        # Check client impact from ELK
        if client_error_analysis.get("client_impact") in ["medium", "high", "severe"]:
            return True
            
        if client_error_analysis.get("error_rate", 0) > 0.05:
            return True
            
        if client_error_analysis.get("has_connection_errors", False) or client_error_analysis.get("has_timeout_errors", False):
            return True
            
        # Check for less critical but concerning conditions
        if active_status.memory_used_percent > 90:
            return True
            
        if active_status.latency_ms > 200:
            return True
            
        if client_error_analysis.get("error_count", 0) > 10:
            return True
            
        # Don't consult AI for healthy instances with minimal client errors
        return False
        
    def _track_ai_recommendation(self, instance_uid: str, decision: Dict[str, Any]):
        """
        Track AI recommendations for an instance to detect consistent patterns.
        
        Args:
            instance_uid: Instance UID
            decision: AI decision
        """
        if instance_uid not in self.ai_recommendations:
            self.ai_recommendations[instance_uid] = []
            
        # Add the new recommendation
        self.ai_recommendations[instance_uid].append({
            "timestamp": time.time(),
            "recommendation": decision.get("recommendation"),
            "target_dc": decision.get("target_dc"),
            "confidence": decision.get("confidence", 0.0)
        })
        
        # Keep only the last 5 recommendations
        if len(self.ai_recommendations[instance_uid]) > 5:
            self.ai_recommendations[instance_uid] = self.ai_recommendations[instance_uid][-5:]
            
    def _should_execute_ai_recommendation(self, instance_uid: str, decision: Dict[str, Any]) -> bool:
        """
        Determine if we should execute the AI recommendation based on consistency and confidence.
        
        Args:
            instance_uid: Instance UID
            decision: Current AI decision
            
        Returns:
            True if we should execute the recommendation, False otherwise
        """
        # Only consider failover recommendations
        if decision.get("recommendation") != "failover" or "target_dc" not in decision:
            return False
            
        # Check confidence threshold
        min_confidence = self.config.ai_failover_confidence or 0.8
        if decision.get("confidence", 0.0) < min_confidence:
            return False
            
        # Check for consistent recommendations
        if instance_uid in self.ai_recommendations:
            recent_recs = self.ai_recommendations[instance_uid]
            
            # Need at least 2 recommendations to consider consistency
            if len(recent_recs) >= 2:
                # Check if the last recommendation (excluding the current one) matches
                prev_rec = recent_recs[-1]
                
                if (prev_rec["recommendation"] == "failover" and 
                    prev_rec["target_dc"] == decision.get("target_dc") and
                    prev_rec["confidence"] >= min_confidence):
                    # We have consistent recommendations for failover
                    return True
                    
        # Need more consistent recommendations
        return False
        
    def perform_manual_failover(self, instance_uid: str, target_dc: str, reason: Optional[str] = None) -> bool:
        """
        Perform a manual failover for an instance with enhanced logging and ELK analysis.
        
        Args:
            instance_uid: Instance UID
            target_dc: Target datacenter
            reason: Optional reason for manual failover
            
        Returns:
            True if successful, False otherwise
        """
        # Get client logs before failover
        client_logs_before = None
        if hasattr(self.core, "elk_client"):
            client_logs_before = self.core.elk_client.analyze_client_errors(instance_uid, minutes=10)
            
        # Perform the standard failover
        result = super().perform_manual_failover(instance_uid, target_dc)
        
        if result:
            # Log the manual failover with client metrics
            logger.info(f"Manual failover for {instance_uid} to {target_dc} succeeded. " +
                      f"Client errors before: {client_logs_before.get('error_count', 0) if client_logs_before else 'N/A'}")
            
            # Schedule a post-failover check to analyze client impact
            if hasattr(self.core, "elk_client"):
                threading.Timer(300, self._check_post_failover_client_impact, args=[instance_uid, client_logs_before]).start()
                
        return result
        
    def _check_post_failover_client_impact(self, instance_uid: str, pre_failover_analysis: Optional[Dict[str, Any]]):
        """
        Check client impact after failover to determine if it was successful.
        
        Args:
            instance_uid: Instance UID
            pre_failover_analysis: Client error analysis before failover
        """
        if not hasattr(self.core, "elk_client"):
            return
            
        # Get post-failover client logs
        post_failover_analysis = self.core.elk_client.analyze_client_errors(instance_uid, minutes=10)
        
        # Compare pre and post failover metrics
        if pre_failover_analysis and post_failover_analysis:
            pre_error_rate = pre_failover_analysis.get("error_rate", 0)
            post_error_rate = post_failover_analysis.get("error_rate", 0)
            
            pre_error_count = pre_failover_analysis.get("error_count", 0)
            post_error_count = post_failover_analysis.get("error_count", 0)
            
            # Determine if failover improved the situation
            if post_error_rate < pre_error_rate * 0.5:
                impact = "Significant improvement"
            elif post_error_rate < pre_error_rate:
                impact = "Slight improvement"
            elif post_error_rate > pre_error_rate * 1.5:
                impact = "Situation worsened"
            else:
                impact = "No significant change"
                
            # Log the results
            logger.info(f"Post-failover analysis for {instance_uid}: {impact}. " +
                      f"Error rate: {pre_error_rate:.2%} -> {post_error_rate:.2%}, " +
                      f"Error count: {pre_error_count} -> {post_error_count}")
            
            # Send alert about impact
            if hasattr(self.core, "alerting"):
                severity = "info"
                if "worsened" in impact:
                    severity = "warning"
                    
                self.core.alerting.send_alert(
                    alert_type="failover_impact",
                    severity=severity,
                    message=f"Failover impact for {instance_uid}: {impact}",
                    details={
                        "instance_uid": instance_uid,
                        "impact": impact,
                        "pre_failover_error_rate": pre_error_rate,
                        "post_failover_error_rate": post_error_rate,
                        "pre_failover_error_count": pre_error_count,
                        "post_failover_error_count": post_error_count
                    }
                )
