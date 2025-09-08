# BGP Listener

A real-time BGP monitoring service that connects to RIPE RIS Live stream, filters BGP updates for specific ASNs and prefixes, and sends notifications to Slack.

## Features

- **Real-time BGP Monitoring**: Connects to RIPE RIS Live WebSocket stream
- **Flexible Filtering**: Monitor specific ASNs (anywhere in AS path) and IP prefixes
- **Slack Integration**: Sends formatted notifications to Slack webhook
- **Docker Ready**: Containerized for easy deployment and service management
- **Robust Error Handling**: Automatic reconnection with configurable retry logic
- **Async Architecture**: High-performance async Python implementation
- **Statistics Reporting**: Shows message counts every 60 seconds

## Quick Start

### 1. Set up Slack Webhook
Create a Slack webhook URL:
1. Go to https://api.slack.com/apps
2. Create a new app or use existing
3. Add "Incoming Webhooks" feature
4. Create webhook for your channel
5. Copy the webhook URL

### 2. Configure Environment
```bash
# Copy the environment template
cp .env.example .env

# Edit .env and add your Slack webhook
SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
```

### 3. Configure Monitoring Targets
```bash
# Copy the configuration template
cp config.yaml.example config.yaml

# Edit config.yaml to set your monitored ASNs and prefixes
```

### 4. Deploy
```bash
docker compose up -d
```

### 5. Monitor
```bash
# View logs
docker compose logs -f bgp-listener

# Check statistics (printed every 60 seconds)
# Shows TOTAL BGP messages vs filtered matches
```

## Configuration

### Environment Variables
- **SLACK_WEBHOOK** (required): Your Slack webhook URL

### Config File (config.yaml.example → config.yaml)
```yaml
# ASNs to monitor (will match anywhere in AS path)
monitored_asns:
  - 3356   # Level 3
  - 174    # Cogent
  - 1299   # Telia

# IP prefixes to monitor (CIDR format)
monitored_prefixes:
  - "192.168.1.0/24"
  - "10.0.0.0/16"

# RIS collectors to subscribe to
ris_collectors:
  - "rrc21"  # Default collector
  - "rrc00"  # Amsterdam multihop
  - "rrc11"  # New York

# Connection settings
reconnect_delay: 5
max_reconnect_attempts: 0  # 0 = infinite retries
slack_retry_attempts: 3
slack_retry_delay: 2
```

## Message Format

BGP events are posted to Slack with the following information:
- Event type (ANNOUNCEMENT/WITHDRAWAL)
- IP prefix affected
- Complete AS path
- Origin ASN
- RIS collector that observed the update
- Timestamp
- What triggered the match (ASN or prefix)

## Service Management

- **Start service**: `docker compose up -d`
- **Stop service**: `docker compose down`
- **View logs**: `docker compose logs -f bgp-listener`
- **Restart service**: `docker compose restart bgp-listener`

## Monitoring

The service automatically:
- Reconnects to RIS Live if connection is lost
- Retries Slack notifications on failure
- Logs all activity to console (captured by Docker)
- Handles BGP announcements, withdrawals, and path changes