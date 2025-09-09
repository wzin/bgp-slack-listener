# BGP Listener - Claude Code Documentation

## Project Overview
Real-time BGP monitoring service that connects to RIPE RIS Live WebSocket stream, filters BGP updates for specific ASNs and IP prefixes, and sends Slack notifications for matching events.

## Architecture

### Core Components
- **BGPListener Class**: Main application class handling all functionality
- **Async Event Loop**: WebSocket connection, message processing, and Slack notifications
- **Configuration System**: YAML-based config with environment variables
- **Docker Deployment**: Containerized service with compose setup

### Key Functionality

#### BGP Monitoring
- Connects to `wss://ris-live.ripe.net/v1/ws/` WebSocket
- Subscribes to multiple RIS collectors (configurable)
- Processes real-time BGP UPDATE messages
- Tracks both announcements and withdrawals

#### Filtering Logic
- **ASN Matching**: Checks if any monitored ASN appears anywhere in AS path
- **Prefix Matching**: Checks for exact matches or more specific announcements within monitored prefixes
- **Event Processing**: Extracts relevant BGP information and creates events for matching updates

#### Slack Integration
- Formats BGP events as structured Slack messages
- Retry logic with configurable attempts and delays
- Tracks notification success/failure rates

#### Statistics & Monitoring
- Prints comprehensive stats every 5 minutes
- Tracks total BGP messages received vs filtered matches
- Per-collector message counts
- Slack notification success metrics

### Configuration

#### Environment Variables
- `SLACK_WEBHOOK`: Required Slack webhook URL for notifications

#### config.yaml Structure
```yaml
monitored_asns: [list]        # ASNs to monitor in AS paths
monitored_prefixes: [list]    # CIDR prefixes to monitor
ris_collectors: [list]        # RIS collector hosts to subscribe to
reconnect_delay: int          # Seconds between reconnection attempts
max_reconnect_attempts: int   # Max reconnects (0 = infinite)
slack_retry_attempts: int     # Slack notification retry count
slack_retry_delay: int        # Seconds between Slack retries
```

#### Current Configuration Values
- **Monitored ASNs**: 3356 (Level 3), 174 (Cogent), 1299 (Telia), 43253 (CBT), 51747 (Internet Vikings), 24940 (Hetzner)
- **Monitored Prefixes**: 185.236.43.0/24, 185.159.186.0/24, 185.159.185.0/24, 45.150.75.0/24
- **RIS Collectors**: rrc21, rrc00, rrc11

### File Structure
```
bgp-listener/
├── bgp_listener.py          # Main application
├── config.yaml              # Production configuration
├── config.yaml.example      # Configuration template
├── requirements.txt         # Python dependencies
├── Dockerfile              # Container build instructions
├── docker-compose.yml      # Service deployment config
├── README.md               # User documentation
└── CLAUDE.md               # This file
```

### Dependencies
- `websockets>=11.0.3`: WebSocket client for RIS Live connection
- `aiohttp>=3.8.5`: HTTP client for Slack webhooks
- `PyYAML>=6.0.1`: YAML configuration parsing
- `ipaddress>=1.0.23`: IP prefix matching and validation
- `asyncio-mqtt>=0.11.1`: MQTT support (unused in current implementation)

### Error Handling & Resilience
- **WebSocket Reconnection**: Automatic reconnection with exponential backoff
- **Slack Retry Logic**: Configurable retry attempts with delays
- **Message Parsing**: Graceful handling of malformed JSON/BGP messages
- **Resource Cleanup**: Proper async task and session cleanup on shutdown

### Performance Characteristics
- **Message Processing**: Handles high-frequency BGP updates (thousands per minute)
- **Memory Usage**: Lightweight, processes messages in streaming fashion
- **Network Efficiency**: WebSocket connection reduces overhead vs polling

### Deployment Commands
- **Start**: `docker compose up -d`
- **Logs**: `docker compose logs -f bgp-listener`
- **Stop**: `docker compose down`
- **Restart**: `docker compose restart bgp-listener`

### Key Features
- Real-time BGP event monitoring and filtering
- Flexible ASN and prefix matching
- Slack notification system with retry logic
- Comprehensive statistics and logging
- Docker containerization for easy deployment
- Automatic reconnection and error recovery

### Testing & Validation
- Monitor logs for connection status and message processing
- Statistics show filtering effectiveness (total vs matched messages)
- Slack notifications confirm end-to-end functionality
- Docker logs provide complete audit trail