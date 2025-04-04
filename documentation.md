# Redis Enterprise AI Monitoring and Failover Agent
# End-to-End Documentation

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Azure OpenAI Integration](#azure-openai-integration)
6. [ELK Integration](#elk-integration)
7. [Enhanced Failover System](#enhanced-failover-system)
8. [API Reference](#api-reference)
9. [Metrics and Monitoring](#metrics-and-monitoring)
10. [Alerting System](#alerting-system)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)
13. [FAQs](#faqs)

## Overview

The Redis Enterprise AI Monitoring and Failover Agent is an intelligent, AI-powered solution for monitoring Redis Enterprise clusters across multiple datacenters and automatically managing failover when issues are detected. The agent uses a combination of server-side metrics, client-side logs, and machine learning to make data-driven decisions about when to failover between datacenters.

### Key Features

- **Real-time Monitoring**: Continuously monitor Redis Enterprise instances
- **AI-powered Decision Making**: Uses Azure OpenAI to analyze complex situations
- **Client Impact Analysis**: Integrates with ELK to analyze client-side logs
- **Intelligent Failover**: Makes data-driven decisions to failover between datacenters
- **Multi-Datacenter Support**: Manages Redis across geographically distributed clusters
- **DNS-based Failover**: Seamless traffic redirection using Route53 or Cloud DNS
- **Comprehensive Alerting**: Notifications via Slack, Email, and PagerDuty
- **REST API**: Programmatic access for integration with existing tools

## Architecture

The Redis Enterprise Agent consists of several integrated components:

### Core Components

1. **Core Framework** (`core.py`): Central orchestration that manages health status and coordinates between modules
2. **Monitoring Module** (`monitoring.py`): Collects real-time metrics from Redis instances
3. **Anomaly Detection** (`anomaly.py`): Uses machine learning to detect unusual patterns
4. **Failover Management** (`failover.py` & `enhanced_failover.py`): Makes decisions about when to switch traffic between datacenters
5. **Alerting System** (`alerting.py`): Sends notifications through multiple channels

### Enhanced Components

6. **Azure OpenAI Integration** (`azure_ai.py`): Uses Azure's AI for intelligent decision making
7. **ELK Client** (`elk_client.py`): Retrieves and analyzes client-side logs from Elasticsearch

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  Redis Enterprise Agent                  │
│                                                         │
│ ┌─────────────┐ ┌────────────┐ ┌────────────────────┐  │
│ │             │ │            │ │                    │  │
│ │ Monitoring  │ │  Anomaly   │ │  Enhanced Failover │  │
│ │   Module    │ │ Detection  │ │      Manager       │  │
│ │             │ │            │ │                    │  │
│ └──────┬──────┘ └──────┬─────┘ └──────────┬─────────┘  │
│        │               │                  │            │
│        ▼               ▼                  ▼            │
│ ┌─────────────────────────────────────────────────┐    │
│ │                    Core Agent                    │    │
│ └────────────────┬─────────────────┬──────────────┘    │
│                  │                 │                    │
│                  ▼                 ▼                    │
│ ┌────────────────────┐   ┌───────────────────┐         │
│ │  Azure OpenAI      │   │     ELK Client    │         │
│ │   Integration      │   │    Integration    │         │
│ └────────────────────┘   └───────────────────┘         │
│                                                         │
└─────────────────────────────────────────────────────────┘
          │                         │                  │
          ▼                         ▼                  ▼
┌───────────────────┐   ┌────────────────────┐  ┌─────────────┐
│ Redis Enterprise  │   │ Azure OpenAI API   │  │ ELK Stack   │
│     Clusters      │   │                    │  │             │
└───────────────────┘   └────────────────────┘  └─────────────┘
```

## Installation

### Prerequisites

- Python 3.7 or higher
- Redis Enterprise clusters across multiple datacenters
- AWS Route53 or Google Cloud DNS for failover (if using DNS-based failover)
- Azure OpenAI API access
- Elasticsearch/Kibana deployment for client logs

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/redis-enterprise-agent.git
cd redis-enterprise-agent
```

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

Your `requirements.txt` should include:

```
redis
requests
boto3
numpy
scikit-learn
pandas
python-dateutil
fastapi
uvicorn
openai>=1.0.0
elasticsearch
```

### Step 4: Add New Files

Add the enhanced components to your project:

1. Save `azure_ai.py` to `redis_agent/azure_ai.py`
2. Save `elk_client.py` to `redis_agent/elk_client.py`
3. Save `enhanced_failover.py` to `redis_agent/enhanced_failover.py`
4. Replace `main.py` with the modified version

### Step 5: Create Configuration File

Create a configuration file (e.g., `config.json`) using the provided template.

### Step 6: Test the Installation

```bash
python -m redis_agent.main --config config.json --verbose
```

## Configuration

The agent is configured using a JSON file. Below is a complete configuration reference.

### Basic Configuration

```json
{
  "instances": [
    {
      "name": "cache-service",
      "uid": "redis-cache-01",
      "endpoints": {
        "primary": {
          "host": "redis-cache.primary.example.com",
          "port": 16379
        },
        "secondary": {
          "host": "redis-cache.secondary.example.com",
          "port": 16379
        }
      },
      "active_dc": "primary",
      "password": "YOUR_REDIS_PASSWORD"
    }
  ],
  
  "datacenters": {
    "primary": {
      "name": "US-EAST",
      "api_url": "https://cluster1.redis-enterprise.example.com:9443",
      "api_user": "admin@example.com",
      "api_password": "YOUR_API_PASSWORD"
    },
    "secondary": {
      "name": "US-WEST",
      "api_url": "https://cluster2.redis-enterprise.example.com:9443",
      "api_user": "admin@example.com",
      "api_password": "YOUR_API_PASSWORD"
    }
  },
  
  "monitoring_interval": 30,
  "decision_interval": 60,
  
  "model_path": "./models",
  "anomaly_threshold": 0.8,
  
  "auto_failover": true,
  "failover_provider": "dns",
  "failover_confidence_threshold": 0.95,
  "failover_consecutive_threshold": 3
}
```

### Azure OpenAI Configuration

Add these settings to your configuration:

```json
"use_azure_openai": true,
"azure_openai": {
  "api_key": "YOUR_AZURE_OPENAI_API_KEY",
  "endpoint": "https://your-resource.openai.azure.com/",
  "api_version": "2023-05-15",
  "model": "gpt-4",
  "max_tokens": 1000,
  "temperature": 0.2,
  "timeout": 30
},
"ai_failover_confidence": 0.85,
"ai_consecutive_recommendations": 2
```

### ELK Configuration

Add these settings to your configuration:

```json
"use_elk": true,
"elk": {
  "url": "https://elasticsearch.example.com:9200",
  "username": "elastic",
  "password": "YOUR_ELK_PASSWORD",
  "index_pattern": "logstash-*",
  "verify_ssl": true,
  "timeout": 30,
  "cache_ttl": 300,
  "client_logs_only": true,
  "headers": {
    "X-Custom-Header": "value"
  }
}
```

### DNS Configuration (for failover)

```json
"dns_provider": "route53",
"dns_config": {
  "zone_id": "Z1ABCDEFGHIJKL",
  "aws_region": "us-east-1",
  "aws_access_key": "YOUR_AWS_ACCESS_KEY",
  "aws_secret_key": "YOUR_AWS_SECRET_KEY",
  "records": [
    {
      "instance_name": "cache-service",
      "name": "redis-cache.example.com",
      "type": "CNAME",
      "ttl": 60
    }
  ]
}
```

### Alerting Configuration

```json
"alert_endpoints": {
  "slack": {
    "webhook_url": "https://hooks.slack.com/services/TXXXXXX/BXXXXXX/XXXXXXXXXXXXXXXXXXXXXXXX"
  },
  "email": {
    "smtp_server": "smtp.example.com",
    "port": 587,
    "use_tls": true,
    "username": "alerts@example.com",
    "password": "YOUR_SMTP_PASSWORD",
    "from_address": "redis-monitor@example.com",
    "to_addresses": ["ops-team@example.com", "oncall@example.com"]
  },
  "pagerduty": {
    "service_key": "YOUR_PAGERDUTY_SERVICE_KEY",
    "client_url": "https://redis-monitor.example.com"
  }
}
```

### API Configuration

```json
"api": {
  "enabled": true,
  "api_key": "YOUR_SECURE_API_KEY",
  "host": "0.0.0.0",
  "port": 8080
}
```

## Azure OpenAI Integration

The agent uses Azure OpenAI to make intelligent decisions about when to failover Redis instances between datacenters. This integration analyzes a combination of server metrics, health statuses, and client logs to determine the best course of action.

### How It Works

1. The agent collects Redis metrics and health status
2. Client logs are retrieved from ELK
3. When issues are detected, the data is sent to Azure OpenAI
4. The AI analyzes the situation and makes a recommendation
5. Based on the recommendation confidence and consistency, a failover may be executed

### Azure OpenAI System Prompt

The agent uses a specialized system prompt to guide the AI's decision making. The prompt instructs the AI to analyze Redis metrics and client logs, focusing on:

1. Server-side metrics like latency, memory usage, hit rate, and errors
2. Client-side logs showing connection errors, timeouts, or retries
3. The relative health of alternative datacenters
4. The potential impact of a failover (disruption vs benefit)

The AI responds with a recommendation, confidence score, reasoning, and potential impact assessment.

### Setting Up Azure OpenAI

1. Create an Azure OpenAI resource in the Azure portal
2. Deploy a model (GPT-4 is recommended for best results)
3. Get your API key and endpoint URL
4. Add these to your configuration file

### Customizing AI Decision Making

The `ai_failover_confidence` setting (default: 0.85) controls the minimum confidence threshold for AI recommendations to be considered.

The `ai_consecutive_recommendations` setting (default: 2) determines how many consecutive recommendations are required before executing a failover.

## ELK Integration

The agent integrates with Elasticsearch to analyze client-side logs, providing valuable insights into how Redis performance issues are affecting client applications.

### How It Works

1. The agent queries Elasticsearch for logs related to specific Redis instances
2. It analyzes patterns in client errors, focusing on:
   - Connection errors
   - Timeout errors
   - Memory-related errors
   - Authentication errors
3. It calculates error rates and identifies error spikes
4. This client impact analysis is used in failover decisions
5. After failover, it compares error rates to determine if the failover was effective

### Setting Up ELK Integration

1. Ensure your client applications log Redis operations with appropriate context
2. Configure the agent with your Elasticsearch connection details
3. Test the connection with the `--verbose` flag to see log retrieval

### Client Log Requirements

For optimal integration, client logs should include:

1. **Redis Instance Identifier**: Include the Redis instance name or UID
2. **Operation Details**: Log the Redis operations being performed
3. **Error Information**: Log any Redis errors with stack traces
4. **Latency Metrics**: Include latency measurements for Redis operations
5. **Timestamps**: Ensure logs have accurate timestamps

Example log format:

```json
{
  "@timestamp": "2023-06-15T12:34:56.789Z",
  "level": "ERROR",
  "message": "Failed to set key: Connection timeout",
  "latency_ms": 1250,
  "redis_instance": "redis-cache-01",
  "operation": "SET",
  "key_pattern": "user:profile:*",
  "exception": "RedisConnectionTimeoutException",
  "log_source": "client"
}
```

## Enhanced Failover System

The enhanced failover system combines server metrics, ML-based anomaly detection, client logs, and AI recommendations to make intelligent decisions about when to failover Redis instances between datacenters.

### Failover Decision Process

1. **Initial Check**: Monitor Redis metrics and health status
2. **Anomaly Detection**: Apply machine learning to identify unusual patterns
3. **Client Impact Analysis**: Analyze client logs from ELK to understand user impact
4. **AI Consultation**: If issues are detected, consult Azure OpenAI for analysis
5. **Decision Execution**: If the AI recommends failover with high confidence consistently, execute the failover
6. **Post-Failover Analysis**: Evaluate client impact after failover to determine effectiveness

### Failover Types

1. **Automatic Failover**: Executed automatically based on AI recommendations and health metrics
2. **Manual Failover**: Triggered via API with post-failover analysis
3. **Monitor Only**: The agent can be run in monitor-only mode with `--no-failover` flag

### DNS-based Failover

The agent uses DNS-based failover to redirect traffic between datacenters. It supports:

1. **AWS Route53**: Updates CNAME records in Route53 hosted zones
2. **Google Cloud DNS**: Updates DNS records in Google Cloud DNS

### Customizing Failover Behavior

These configuration settings control failover behavior:

- `auto_failover`: Set to `false` to disable automatic failover
- `failover_confidence_threshold`: Minimum confidence level required (0.0-1.0)
- `failover_consecutive_threshold`: Number of consecutive failures before failover
- `ai_failover_confidence`: Minimum confidence for AI-recommended failovers
- `ai_consecutive_recommendations`: Required consecutive AI recommendations

## API Reference

The agent provides a REST API for monitoring and control.

### Authentication

All API requests require the `X-API-Key` header with the configured API key.

### Status Endpoints

```
GET /api/status
```
Get health status of all instances

```
GET /api/status/{instance_uid}
```
Get detailed status of a specific instance

### Metrics Endpoints

```
GET /api/metrics/{instance_uid}
```
Get metrics history for an instance

```
GET /api/metrics/{instance_uid}/latest
```
Get latest metrics for an instance

### Failover Endpoints

```
POST /api/failover/{instance_uid}
```
Trigger manual failover for an instance

Request body:
```json
{
  "target_dc": "secondary",
  "force": false,
  "reason": "Maintenance"
}
```

```
GET /api/failover/history
```
Get failover decision history

### Alert Endpoints

```
GET /api/alerts
```
Get alert history

Query parameters:
- `limit`: Maximum number of alerts to return
- `severity`: Filter by severity
- `alert_type`: Filter by alert type
- `instance_uid`: Filter by instance UID

### Client Log Endpoints

```
GET /api/client-errors/{instance_uid}
```
Get client error analysis from ELK

### AI Recommendation Endpoints

```
GET /api/ai-recommendations/{instance_uid}
```
Get recent AI recommendations for an instance

## Metrics and Monitoring

The agent monitors a comprehensive set of metrics from Redis Enterprise instances.

### Key Metrics Monitored

1. **Basic Redis Metrics**
   - Response time/latency
   - Memory usage
   - Hit rate
   - Connected clients
   - Operation throughput
   - Rejected connections
   - Evicted keys

2. **Redis Enterprise Specific Metrics**
   - Shard metrics
   - Cluster metrics
   - Cross-datacenter replication status

3. **Client-Side Metrics**
   - Error rates
   - Timeout frequency
   - Connection failure rates
   - Operation latency

### Anomaly Detection

The agent uses machine learning (Isolation Forest algorithm) to detect anomalies in Redis metrics. It learns normal behavior patterns and identifies unusual deviations that might indicate issues.

Features of anomaly detection:

- Self-training models
- Automatic adaptation to changing usage patterns
- Early warning of potential issues
- Contributing factor identification

### Health Scoring

The agent calculates health scores for each datacenter based on multiple metrics:

- Status (healthy, degraded, failing, failed)
- Latency
- Memory usage
- Hit rate
- Connected clients
- Error counts
- Anomaly scores

These health scores are used to determine the best datacenter to serve traffic.

## Alerting System

The agent provides a comprehensive alerting system that can notify operators about issues through multiple channels.

### Alert Types

1. **Anomaly Detection Alerts**
   - Unusual patterns in Redis metrics
   - Latency spikes
   - Memory usage anomalies
   - Operation pattern changes

2. **Threshold-based Alerts**
   - High memory usage (>90%)
   - High latency (>100ms)
   - Low hit rate (<50%)
   - Connection saturation

3. **Availability Alerts**
   - Connection failures
   - Authentication failures
   - Replication failures

4. **Failover Alerts**
   - Automatic failover executed
   - Manual failover required
   - Failover success/failure
   - Post-failover impact analysis

### Alert Channels

The agent can send alerts through:

1. **Slack**: Uses webhook URLs to post alerts to Slack channels
2. **Email**: Sends detailed HTML and text emails
3. **PagerDuty**: Integrates with PagerDuty for incident management

### Alert Rate Limiting

The agent implements rate limiting to prevent alert storms:

- Critical alerts: Maximum 1 per minute
- Error alerts: Maximum 1 per 3 minutes
- Warning alerts: Maximum 1 per 5 minutes
- Info alerts: Maximum 1 per 10 minutes

Failover-related alerts always bypass rate limiting.

## Deployment

### Running as a Service

#### On Linux (systemd)

Create a systemd service file at `/etc/systemd/system/redis-agent.service`:

```ini
[Unit]
Description=Redis Enterprise AI Monitoring and Failover Agent
After=network.target

[Service]
Type=simple
User=redis-agent
WorkingDirectory=/opt/redis-agent
ExecStart=/opt/redis-agent/venv/bin/python -m redis_agent.main --config /etc/redis-agent/config.json
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable redis-agent
sudo systemctl start redis-agent
```

#### With Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "redis_agent.main", "--config", "/config/config.json"]
```

Build and run the Docker image:

```bash
docker build -t redis-enterprise-agent .
docker run -v $(pwd)/config.json:/config/config.json redis-enterprise-agent
```

### Environment Variables

The agent supports these environment variables:

- `AZURE_OPENAI_API_KEY`: API key for Azure OpenAI
- `AZURE_OPENAI_ENDPOINT`: Endpoint URL for Azure OpenAI
- `ELASTICSEARCH_URL`: URL for Elasticsearch
- `ELASTICSEARCH_USERNAME`: Username for Elasticsearch
- `ELASTICSEARCH_PASSWORD`: Password for Elasticsearch

### Security Considerations

1. **API Security**: Use a strong API key and consider putting the API behind a reverse proxy with TLS
2. **Credential Management**: Use environment variables for secrets instead of including them in config files
3. **Network Security**: Ensure Redis and API communication uses TLS/SSL
4. **Access Control**: Run the agent with minimal required permissions

## Troubleshooting

### Common Issues

#### Connection Issues

**Symptom**: Agent cannot connect to Redis instances

**Solutions**:
- Verify Redis hostname and port
- Check network connectivity: `telnet redis-host port`
- Verify credentials
- Check if Redis requires TLS

#### Azure OpenAI Issues

**Symptom**: Agent cannot connect to Azure OpenAI

**Solutions**:
- Verify API key and endpoint URL
- Check network connectivity
- Validate model deployment in Azure
- Check quota limits in Azure

#### ELK Issues

**Symptom**: Agent cannot retrieve client logs

**Solutions**:
- Verify Elasticsearch URL and credentials
- Check index pattern is correct
- Ensure client logs contain Redis instance identifiers
- Test Elasticsearch query directly

#### Failover Issues

**Symptom**: Failover is not executing when expected

**Solutions**:
- Check if `auto_failover` is enabled
- Verify confidence thresholds are appropriate
- Check DNS credentials and permissions
- Look for specific error messages in logs

### Logging

The agent logs to both the console and a log file. Check the logs at:

- `/var/log/redis-agent.log` (when running as a service)
- Console output (when running directly)

Increase verbosity with the `--verbose` flag for more detailed logs.

### Diagnostic Commands

```bash
# Check if Redis instances are reachable
redis-cli -h redis-host -p port -a password ping

# Verify AWS credentials and permissions
aws route53 list-hosted-zones --profile your-profile

# Test connection to Azure OpenAI
curl -X POST "https://your-resource.openai.azure.com/openai/deployments/your-deployment/chat/completions?api-version=2023-05-15" \
  -H "Content-Type: application/json" \
  -H "api-key: YOUR_API_KEY" \
  -d '{"messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"Hello"}]}'

# Test connection to Elasticsearch
curl -X GET "https://elasticsearch.example.com:9200/_cluster/health" \
  -u "username:password"
```

## FAQs

### General Questions

**Q: How does the agent decide when to failover?**

A: The agent uses a combination of Redis metrics, anomaly detection, client impact analysis, and AI recommendations to decide when to failover. It looks for consistent evidence that a datacenter is experiencing issues and that a failover would improve the situation.

**Q: Does the agent require Azure OpenAI to function?**

A: No, the agent can function without Azure OpenAI, but it will fall back to the standard failover logic, which may be less intelligent in complex situations.

**Q: How much does it cost to run the agent with Azure OpenAI?**

A: The agent is designed to minimize API calls to Azure OpenAI, only consulting the AI when issues are detected and rate-limiting consultations to once per 5 minutes per instance. The actual cost will depend on your Azure pricing tier and the number of issues detected.

### Technical Questions

**Q: Can the agent monitor multiple Redis Enterprise clusters?**

A: Yes, the agent can monitor multiple Redis instances across multiple datacenters.

**Q: How does DNS-based failover work?**

A: The agent updates DNS records to point to the healthy datacenter when a failover is executed. This requires Route53 or Google Cloud DNS and appropriate permissions.

**Q: Does the agent support TLS/SSL for Redis connections?**

A: Yes, the agent supports TLS/SSL for Redis connections. Configure this in the endpoints section of your configuration.

**Q: How do I add new alert channels?**

A: To add a new alert channel, you would need to modify the `alerting.py` module to support the new channel and update the configuration schema.

### Operational Questions

**Q: How do I monitor the agent itself?**

A: The agent exposes metrics via its API that can be scraped by monitoring systems like Prometheus. You can also monitor the agent's log file for warnings and errors.

**Q: How often does the agent check Redis instances?**

A: By default, the agent checks Redis instances every 30 seconds, but this is configurable with the `monitoring_interval` setting.

**Q: How does the agent handle transient issues?**

A: The agent uses a consecutive error threshold to avoid failovers due to transient issues. It will only consider failover after multiple consecutive failures.

**Q: How can I test the agent without risking production?**

A: You can run the agent with the `--no-failover` flag to monitor without executing failovers. This allows you to see what decisions the agent would make without actually performing failovers.
