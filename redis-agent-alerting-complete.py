#!/usr/bin/env python3
# redis_agent/alerting.py - Alerting module for Redis Enterprise monitoring agent

import logging
import threading
import time
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("redis-agent.alerting")

class AlertManager:
    """Manage and send alerts through multiple channels"""
    
    def __init__(self, core_agent):
        """Initialize the alert manager.
        
        Args:
            core_agent: Reference to the core agent
        """
        self.core = core_agent
        self.config = core_agent.config
        self.alert_history = []
        self.last_alert_time = {}  # alert_key -> timestamp
        self.lock = threading.RLock()
    
    def initialize(self):
        """Initialize alert channels."""
        # Validate alert configuration
        self._validate_alert_config()
        logger.info("Alert manager initialized")
    
    def _validate_alert_config(self):
        """Validate the alert configuration."""
        alert_endpoints = self.config.alert_endpoints
        
        if not alert_endpoints:
            logger.warning("No alert endpoints configured")
            return
        
        # Check Slack configuration
        if "slack" in alert_endpoints:
            slack_config = alert_endpoints["slack"]
            if "webhook_url" not in slack_config:
                logger.error("Slack webhook URL not configured")
        
        # Check email configuration
        if "email" in alert_endpoints:
            email_config = alert_endpoints["email"]
            required_fields = ["smtp_server", "port", "from_address", "to_addresses"]
            for field in required_fields:
                if field not in email_config:
                    logger.error(f"Email configuration missing required field: {field}")
        
        # Check PagerDuty configuration
        if "pagerduty" in alert_endpoints:
            pd_config = alert_endpoints["pagerduty"]
            if "service_key" not in pd_config:
                logger.error("PagerDuty service key not configured")
    
    def send_alert(self, alert_type: str, severity: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Send an alert through all configured channels.
        
        Args:
            alert_type: Type of alert
            severity: Alert severity (info, warning, error, critical)
            message: Alert message
            details: Optional additional details
        """
        # Create alert object
        alert = {
            "type": alert_type,
            "severity": severity,
            "message": message,
            "details": details or {},
            "timestamp": time.time()
        }
        
        # Add alert ID and formatted timestamp
        alert["id"] = f"{alert_type}_{int(alert['timestamp'])}"
        alert["timestamp_str"] = datetime.fromtimestamp(alert["timestamp"]).isoformat()
        
        # Check rate limiting
        if not self._should_send_alert(alert):
            logger.debug(f"Rate limiting alert: {alert['id']}")
            return
        
        # Log the alert
        log_level = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL
        }.get(severity, logging.INFO)
        
        logger.log(log_level, f"ALERT: {message}")
        
        # Send through all channels
        self._send_to_slack(alert)
        self._send_to_email(alert)
        self._send_to_pagerduty(alert)
        
        # Store in history
        with self.lock:
            self.alert_history.append(alert)
            # Limit history size
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]
            
            # Update last alert time
            alert_key = f"{alert_type}_{details.get('instance_uid', '')}" if details else alert_type
            self.last_alert_time[alert_key] = alert["timestamp"]
    
    def _should_send_alert(self, alert):
        """Check if we should send this alert (rate limiting)."""
        alert_type = alert["type"]
        details = alert["details"]
        
        # Create a key for this alert type and instance
        alert_key = f"{alert_type}_{details.get('instance_uid', '')}" if details else alert_type
        
        # Check when we last sent this type of alert
        last_time = self.last_alert_time.get(alert_key, 0)
        time_since_last = alert["timestamp"] - last_time
        
        # Get minimum interval between alerts of this type
        min_interval = 300  # Default: 5 minutes
        
        # Use different intervals based on severity
        if alert["severity"] == "critical":
            min_interval = 60  # 1 minute for critical alerts
        elif alert["severity"] == "error":
            min_interval = 180  # 3 minutes for error alerts
        elif alert["severity"] == "warning":
            min_interval = 300  # 5 minutes for warning alerts
        else:  # info
            min_interval = 600  # 10 minutes for info alerts
        
        # Always send critical alerts about failover
        if alert_type in ["failover_succeeded", "failover_failed", "manual_failover_required"] and \
           alert["severity"] in ["critical", "error"]:
            return True
        
        # Rate limit other alerts
        return time_since_last >= min_interval
    
    def _send_to_slack(self, alert):
        """Send alert to Slack webhook."""
        # Check if Slack is configured
        if "slack" not in self.config.alert_endpoints:
            return
        
        slack_config = self.config.alert_endpoints["slack"]
        webhook_url = slack_config.get("webhook_url")
        
        if not webhook_url:
            logger.warning("Slack webhook URL not configured")
            return
        
        try:
            # Create Slack message
            color = {
                "info": "#36a64f",  # green
                "warning": "#ffcc00",  # yellow
                "error": "#ff9900",  # orange
                "critical": "#ff0000"  # red
            }.get(alert["severity"], "#36a64f")
            
            # Format message with details
            fields = []
            
            # Add basic fields
            fields.append({
                "title": "Severity",
                "value": alert["severity"].upper(),
                "short": True
            })
            
            fields.append({
                "title": "Time",
                "value": alert["timestamp_str"],
                "short": True
            })
            
            # Add instance details if available
            if "instance_name" in alert["details"]:
                fields.append({
                    "title": "Instance",
                    "value": alert["details"]["instance_name"],
                    "short": True
                })
            
            if "datacenter" in alert["details"]:
                fields.append({
                    "title": "Datacenter",
                    "value": alert["details"]["datacenter"],
                    "short": True
                })
            
            # Add additional fields for specific alert types
            if alert["type"] == "anomaly_detected":
                if "anomaly_score" in alert["details"]:
                    fields.append({
                        "title": "Anomaly Score",
                        "value": f"{alert['details']['anomaly_score']:.2f}",
                        "short": True
                    })
                
                # Add metrics
                metrics = alert["details"].get("metrics", {})
                if metrics:
                    metrics_text = "\n".join([
                        f"• {k}: {v}" for k, v in metrics.items()
                    ])
                    
                    fields.append({
                        "title": "Metrics",
                        "value": metrics_text,
                        "short": False
                    })
            
            elif alert["type"] in ["failover_succeeded", "failover_failed", "manual_failover_required"]:
                if "from_dc" in alert["details"] and "to_dc" in alert["details"]:
                    fields.append({
                        "title": "Failover",
                        "value": f"From {alert['details']['from_dc']} to {alert['details']['to_dc']}",
                        "short": True
                    })
                
                if "reason" in alert["details"]:
                    fields.append({
                        "title": "Reason",
                        "value": alert["details"]["reason"],
                        "short": False
                    })
            
            # Create the payload
            payload = {
                "attachments": [
                    {
                        "fallback": alert["message"],
                        "color": color,
                        "pretext": "Redis Enterprise Alert",
                        "title": alert["message"],
                        "fields": fields,
                        "footer": f"Redis Agent • {alert['type']}"
                    }
                ]
            }
            
            # Send the request
            response = requests.post(
                webhook_url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"Error sending Slack alert: {response.text}")
            
        except Exception as e:
            logger.error(f"Error sending Slack alert: {e}")
    
    def _send_to_email(self, alert):
        """Send alert via email."""
        # Check if email is configured
        if "email" not in self.config.alert_endpoints:
            return
        
        email_config = self.config.alert_endpoints["email"]
        required_fields = ["smtp_server", "port", "from_address", "to_addresses"]
        
        for field in required_fields:
            if field not in email_config:
                logger.warning(f"Email configuration missing required field: {field}")
                return
        
        try:
            # Create email message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert['severity'].upper()}] Redis Alert: {alert['message']}"
            msg["From"] = email_config["from_address"]
            
            # Handle to_addresses as string or list
            to_addresses = email_config["to_addresses"]
            if isinstance(to_addresses, str):
                to_addresses = [to_addresses]
            
            msg["To"] = ", ".join(to_addresses)
            
            # Create email body
            text_body = f"""
Redis Enterprise Alert

Type: {alert['type']}
Severity: {alert['severity'].upper()}
Time: {alert['timestamp_str']}
Message: {alert['message']}

"""
            
            # Add details
            if alert["details"]:
                text_body += "Details:\n"
                for key, value in alert["details"].items():
                    if isinstance(value, dict):
                        text_body += f"  {key}:\n"
                        for k, v in value.items():
                            text_body += f"    {k}: {v}\n"
                    else:
                        text_body += f"  {key}: {value}\n"
            
            # HTML version
            html_body = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .alert-header {{ background-color: #f8f8f8; padding: 10px; }}
        .alert-body {{ padding: 10px; }}
        .label {{ font-weight: bold; }}
        .severity-info {{ color: green; }}
        .severity-warning {{ color: #cc9900; }}
        .severity-error {{ color: #cc6600; }}
        .severity-critical {{ color: red; }}
    </style>
</head>
<body>
    <div class="alert-header">
        <h2>Redis Enterprise Alert</h2>
        <p><span class="label">Type:</span> {alert['type']}</p>
        <p><span class="label">Severity:</span> <span class="severity-{alert['severity']}">{alert['severity'].upper()}</span></p>
        <p><span class="label">Time:</span> {alert['timestamp_str']}</p>
        <p><span class="label">Message:</span> {alert['message']}</p>
    </div>
    <div class="alert-body">
"""
            
            # Add details to HTML
            if alert["details"]:
                html_body += "<h3>Details:</h3>"
                html_body += "<table border='0' cellpadding='5'>"
                
                for key, value in alert["details"].items():
                    if isinstance(value, dict):
                        html_body += f"<tr><td colspan='2'><b>{key}:</b></td></tr>"
                        for k, v in value.items():
                            html_body += f"<tr><td style='padding-left:20px'>{k}:</td><td>{v}</td></tr>"
                    else:
                        html_body += f"<tr><td><b>{key}:</b></td><td>{value}</td></tr>"
                
                html_body += "</table>"
            
            html_body += """
    </div>
</body>
</html>
"""
            
            # Attach the text and HTML parts
            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)
            
            # Connect to the SMTP server and send
            with smtplib.SMTP(email_config["smtp_server"], email_config["port"]) as server:
                # Use TLS if specified
                if email_config.get("use_tls", False):
                    server.starttls()
                
                # Authenticate if credentials provided
                if "username" in email_config and "password" in email_config:
                    server.login(email_config["username"], email_config["password"])
                
                # Send the email
                server.sendmail(
                    email_config["from_address"],
                    to_addresses,
                    msg.as_string()
                )
            
            logger.info(f"Sent email alert to {', '.join(to_addresses)}")
            
        except Exception as e:
            logger.error(f"Error sending email alert: {e}")
    
    def _send_to_pagerduty(self, alert):
        """Send alert to PagerDuty."""
        # Check if PagerDuty is configured
        if "pagerduty" not in self.config.alert_endpoints:
            return
        
        pd_config = self.config.alert_endpoints["pagerduty"]
        service_key = pd_config.get("service_key")
        
        if not service_key:
            logger.warning("PagerDuty service key not configured")
            return
        
        # Only send high severity alerts to PagerDuty
        if alert["severity"] not in ["error", "critical"]:
            return
        
        try:
            # Create PagerDuty payload
            payload = {
                "service_key": service_key,
                "event_type": "trigger",
                "incident_key": alert["id"],
                "description": alert["message"],
                "details": alert["details"],
                "client": "Redis Enterprise Agent",
                "client_url": pd_config.get("client_url", "")
            }
            
            # Send the request
            response = requests.post(
                "https://events.pagerduty.com/generic/2010-04-15/create_event.json",
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"Error sending PagerDuty alert: {response.text}")
            else:
                logger.info("Sent PagerDuty alert")
            
        except Exception as e:
            logger.error(f"Error sending PagerDuty alert: {e}")
    
    def get_alert_history(self, limit: int = 100, severity: Optional[str] = None, alert_type: Optional[str] = None):
        """Get recent alerts, optionally filtered by severity and type."""
        with self.lock:
            # Filter alerts
            filtered_alerts = self.alert_history
            
            if severity:
                filtered_alerts = [a for a in filtered_alerts if a["severity"] == severity]
            
            if alert_type:
                filtered_alerts = [a for a in filtered_alerts if a["type"] == alert_type]
            
            # Sort by timestamp (newest first) and limit
            return sorted(
                filtered_alerts,
                key=lambda a: a["timestamp"],
                reverse=True
            )[:limit]
