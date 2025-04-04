# Redis Enterprise AI Monitoring and Failover Agent

An intelligent, AI-powered monitoring and automated failover solution for Redis Enterprise clusters deployed across multiple datacenters.

## Features

- **Real-time Monitoring**: Continuously monitor the health and performance of Redis Enterprise instances
- **AI-powered Anomaly Detection**: Detect unusual patterns and behavior using machine learning
- **Intelligent Failover**: Make data-driven decisions to failover between datacenters
- **Multi-Datacenter Support**: Monitor and manage Redis across geographically distributed datacenters
- **DNS-based Failover**: Seamless traffic redirection using Route53 or Cloud DNS
- **Comprehensive Alerting**: Notifications via Slack, Email, and PagerDuty
- **REST API**: Programmatic access for integration with existing tools
- **Historical Metrics**: Track performance over time for capacity planning

## Architecture

The Redis Enterprise Agent is built with a modular architecture that includes:

1. **Core Framework**: Central orchestration and coordination
2. **Monitoring Module**: Real-time metrics collection
3. **Anomaly Detection**: Machine learning-based anomaly detection
4. **Failover Management**: Intelligent decision making for failovers
5. **Alerting System**: Multi-channel notification delivery
6. **REST API**: HTTP interface for monitoring and control

## Installation

### Prerequisites

- Python 3.7 or higher
- Redis Enterprise clusters across multiple datacenters
- AWS Route53 or Google Cloud DNS for failover (if using DNS-based failover)

### Quick Install

```bash
# Clone the repository
git clone https://github.com/yourusername/redis-enterprise-agent.git
cd redis-enterprise-agent

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create configuration file
cp examples/config_basic.json config.json
# Edit config.json with your Redis Enterprise settings

# Run the agent
python -m redis_agent.main --config config.json
```

## Configuration

The agent is configured using a JSON file. Here's a basic example:

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
  
  "auto_failover": true,
  "failover_provider": "dns",
  "dns_provider": "route53",
  "dns_config": {
    "zone_id": "Z1ABCDEFGHIJKL",
    "records": [
      {
        "instance_name": "cache-service",
        "name": "redis-cache.example.com",
        "type": "CNAME",
        "ttl": 60
      }
    ]
  }
}
```

See the [Configuration Guide](docs/configuration.md) for detailed configuration options.

## Usage

### Running the Agent

```bash
# Basic operation
python -m redis_agent.main --config config.json

# With verbose logging
python -m redis_agent.main --config config.json --verbose

# Disable automatic failover (monitoring only)
python -m redis_agent.main --config config.json --no-failover
```

### API Access

The agent exposes a REST API for monitoring and control:

```bash
# Get health status of all instances
curl -X GET http://localhost:8080/api/status \
  -H "X-API-Key: YOUR_API_KEY"

# Trigger manual failover
curl -X POST http://localhost:8080/api/failover/redis-cache-01 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"target_dc": "secondary"}'
```

See the [API Documentation](docs/api.md) for all available endpoints.

## Monitoring and Alerting

The agent monitors key metrics including:

- Response time
- Memory usage
- Hit rate
- Connected clients
- Operation throughput
- Error rates
- Cross-datacenter replication status

Alerts can be delivered via:
- Slack
- Email
- PagerDuty

## Anomaly Detection

The agent uses Isolation Forest algorithm to detect anomalies in Redis metrics. It learns normal behavior and identifies unusual patterns that might indicate issues.

Features include:
- Self-training models
- Automatic adaptation to changing usage patterns
- Early warning of potential issues
- Contributing factor identification

## Deployment

### As a Service

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

### With Docker

```bash
docker build -t redis-enterprise-agent .
docker run -v $(pwd)/config.json:/config/config.json redis-enterprise-agent
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
