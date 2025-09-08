#!/usr/bin/env python3
"""
BGP Listener - Real-time BGP monitoring with Slack notifications
Connects to RIPE RIS Live stream and filters BGP updates for specific ASNs and prefixes
"""

import asyncio
import json
import logging
import os
import sys
import ipaddress
from datetime import datetime
from typing import Dict, List, Set, Optional, Any
import yaml
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException


class BGPListener:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.monitored_asns = set(self.config.get("monitored_asns", []))
        self.monitored_prefixes = self._parse_prefixes(self.config.get("monitored_prefixes", []))
        self.slack_webhook = self._get_slack_webhook()
        self.ris_collectors = self.config.get("ris_collectors", ["rrc21"])
        self.reconnect_delay = self.config.get("reconnect_delay", 5)
        self.max_reconnect_attempts = self.config.get("max_reconnect_attempts", 0)
        self.slack_retry_attempts = self.config.get("slack_retry_attempts", 3)
        self.slack_retry_delay = self.config.get("slack_retry_delay", 2)
        self.session = None
        
        # Statistics tracking
        self.message_counts = {collector: 0 for collector in self.ris_collectors}
        self.total_bgp_messages = 0  # ALL BGP messages received (before filtering)
        self.slack_messages_sent = 0
        self.stats_task = None

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Config file {config_path} not found")
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing config file: {e}")
            sys.exit(1)

    def _get_slack_webhook(self) -> str:
        """Get Slack webhook URL from environment variable"""
        webhook = os.getenv("SLACK_WEBHOOK")
        if not webhook:
            print("Error: SLACK_WEBHOOK environment variable is not set")
            sys.exit(1)
        return webhook

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        # Get logger and configure it directly
        logger = logging.getLogger(__name__)
        
        # Only configure if not already configured
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.propagate = False  # Prevent propagation to root logger
            
        # Set websockets logging level
        logging.getLogger('websockets').setLevel(logging.WARNING)
        return logger

    def _parse_prefixes(self, prefixes: List[str]) -> List[ipaddress.IPv4Network]:
        """Parse string prefixes into ipaddress objects"""
        parsed = []
        for prefix in prefixes:
            try:
                parsed.append(ipaddress.IPv4Network(prefix, strict=False))
            except (ipaddress.AddressValueError, ValueError) as e:
                self.logger.warning(f"Invalid prefix {prefix}: {e}")
        return parsed

    def _matches_monitored_asn(self, as_path: List[int]) -> Optional[int]:
        """Check if any monitored ASN appears in the AS path"""
        if not as_path:
            return None
        
        for asn in as_path:
            if asn in self.monitored_asns:
                return asn
        return None

    def _matches_monitored_prefix(self, announced_prefix: str) -> Optional[str]:
        """Check if announced prefix matches or overlaps with monitored prefixes"""
        try:
            announced = ipaddress.IPv4Network(announced_prefix, strict=False)
            for monitored in self.monitored_prefixes:
                # Check for exact match or if announced prefix is more specific
                if announced.subnet_of(monitored) or announced == monitored:
                    return str(monitored)
        except (ipaddress.AddressValueError, ValueError):
            pass
        return None

    def _parse_bgp_message(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse BGP message and extract relevant information"""
        if data.get("type") != "UPDATE":
            return None

        # Extract key information
        prefix = data.get("prefix")
        as_path = data.get("path", [])
        peer_asn = data.get("peer_asn")
        origin_asn = as_path[-1] if as_path else peer_asn
        timestamp = data.get("timestamp")
        host = data.get("host", "unknown")
        
        # Check for withdrawals
        withdrawn = data.get("withdrawn", [])
        announcements = data.get("announcements", [])
        
        events = []
        
        # Process withdrawals
        for withdrawn_prefix in withdrawn:
            matched_prefix = self._matches_monitored_prefix(withdrawn_prefix)
            matched_asn = self._matches_monitored_asn(as_path)
            
            if matched_prefix or matched_asn:
                events.append({
                    "type": "withdrawal",
                    "prefix": withdrawn_prefix,
                    "as_path": as_path,
                    "origin_asn": origin_asn,
                    "peer_asn": peer_asn,
                    "timestamp": timestamp,
                    "host": host,
                    "matched_prefix": matched_prefix,
                    "matched_asn": matched_asn
                })
        
        # Process announcements
        if prefix:
            matched_prefix = self._matches_monitored_prefix(prefix)
            matched_asn = self._matches_monitored_asn(as_path)
            
            if matched_prefix or matched_asn:
                events.append({
                    "type": "announcement",
                    "prefix": prefix,
                    "as_path": as_path,
                    "origin_asn": origin_asn,
                    "peer_asn": peer_asn,
                    "timestamp": timestamp,
                    "host": host,
                    "matched_prefix": matched_prefix,
                    "matched_asn": matched_asn
                })
        
        return events

    def _format_slack_message(self, event: Dict[str, Any]) -> str:
        """Format BGP event as Slack message"""
        event_type = event["type"].upper()
        prefix = event["prefix"]
        as_path_str = " → ".join(map(str, event["as_path"])) if event["as_path"] else "N/A"
        origin_asn = event["origin_asn"]
        timestamp = datetime.fromtimestamp(event["timestamp"]).strftime("%Y-%m-%d %H:%M:%S UTC") if event["timestamp"] else "N/A"
        host = event["host"]
        
        match_info = []
        if event["matched_asn"]:
            match_info.append(f"ASN {event['matched_asn']}")
        if event["matched_prefix"]:
            match_info.append(f"Prefix {event['matched_prefix']}")
        
        match_str = " (Matched: " + ", ".join(match_info) + ")" if match_info else ""
        
        message = f"🚨 BGP {event_type}{match_str}\n"
        message += f"• Prefix: {prefix}\n"
        message += f"• AS Path: {as_path_str}\n"
        message += f"• Origin ASN: {origin_asn}\n"
        message += f"• RIS Collector: {host}\n"
        message += f"• Timestamp: {timestamp}"
        
        return message

    async def _print_stats(self):
        """Print statistics every 60 seconds"""
        while True:
            await asyncio.sleep(60)
            filtered_messages = sum(self.message_counts.values())
            self.logger.info("=== BGP Listener Statistics ===")
            self.logger.info(f"TOTAL BGP messages received: {self.total_bgp_messages}")
            self.logger.info(f"Filtered messages (matching ASNs/prefixes): {filtered_messages}")
            for collector, count in self.message_counts.items():
                self.logger.info(f"  {collector}: {count} filtered messages")
            self.logger.info(f"Slack messages sent: {self.slack_messages_sent}")
            self.logger.info("===============================")

    async def _send_slack_notification(self, message: str):
        """Send notification to Slack with retry logic"""
        for attempt in range(self.slack_retry_attempts):
            try:
                payload = {"text": message}
                async with self.session.post(
                    self.slack_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.slack_messages_sent += 1
                        self.logger.info(f"Slack notification sent successfully (Total sent: {self.slack_messages_sent})")
                        return
                    else:
                        self.logger.warning(f"Slack API returned status {response.status}")
                        
            except Exception as e:
                self.logger.warning(f"Failed to send Slack notification (attempt {attempt + 1}): {e}")
                
            if attempt < self.slack_retry_attempts - 1:
                await asyncio.sleep(self.slack_retry_delay)
        
        self.logger.error("Failed to send Slack notification after all retry attempts")

    async def _connect_and_listen(self):
        """Connect to RIS Live WebSocket and listen for BGP updates"""
        uri = "wss://ris-live.ripe.net/v1/ws/?client=bgp-listener-python"
        
        async with websockets.connect(uri) as websocket:
            self.logger.info(f"Connected to RIS Live: {uri}")
            
            # Subscribe to BGP updates for all configured collectors
            for collector in self.ris_collectors:
                subscription = {
                    "type": "ris_subscribe",
                    "data": {
                        "host": collector,
                        "socketOptions": {
                            "includeRaw": False
                        }
                    }
                }
                await websocket.send(json.dumps(subscription))
                self.logger.info(f"Subscribed to collector: {collector}")
            
            # Listen for messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    # Debug: log all message types we receive
                    msg_type = data.get("type", "unknown")
                    if msg_type not in ["ris_message"]:
                        self.logger.debug(f"Received message type: {msg_type}")
                    
                    if data.get("type") == "ris_message":
                        bgp_data = data.get("data", {})
                        
                        # Count ALL BGP messages received (before any filtering)
                        self.total_bgp_messages += 1
                        
                        # Parse and filter messages
                        events = self._parse_bgp_message(bgp_data)
                        
                        if events:
                            # Only count filtered messages per collector
                            host = bgp_data.get("host", "unknown")
                            if host in self.message_counts:
                                self.message_counts[host] += 1
                            else:
                                # Track unknown collectors too
                                if host != "unknown":
                                    self.message_counts[host] = 1
                                    self.logger.info(f"Receiving filtered messages from new collector: {host}")
                            
                            for event in events:
                                self.logger.info(f"BGP {event['type']}: {event['prefix']} via AS{event['origin_asn']} from {event['host']}")
                                slack_message = self._format_slack_message(event)
                                await self._send_slack_notification(slack_message)
                    
                except json.JSONDecodeError as e:
                    self.logger.warning(f"Failed to decode JSON message: {e}")
                except Exception as e:
                    self.logger.error(f"Error processing message: {e}")

    async def run(self):
        """Main run loop with reconnection logic"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # Start statistics printing task once
        if self.stats_task is None or self.stats_task.done():
            self.stats_task = asyncio.create_task(self._print_stats())
        
        attempt = 0
        while True:
            try:
                self.logger.info(f"Connecting to RIS Live (attempt {attempt + 1})")
                await self._connect_and_listen()
                
            except (ConnectionClosed, WebSocketException) as e:
                self.logger.warning(f"WebSocket connection lost: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
            
            attempt += 1
            if self.max_reconnect_attempts > 0 and attempt >= self.max_reconnect_attempts:
                self.logger.error("Maximum reconnection attempts reached. Exiting.")
                break
            
            self.logger.info(f"Reconnecting in {self.reconnect_delay} seconds...")
            await asyncio.sleep(self.reconnect_delay)

    async def cleanup(self):
        """Cleanup resources"""
        if self.stats_task and not self.stats_task.done():
            self.stats_task.cancel()
            try:
                await self.stats_task
            except asyncio.CancelledError:
                pass
        if self.session:
            await self.session.close()


async def main():
    """Main entry point"""
    listener = BGPListener()
    
    try:
        await listener.run()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Received interrupt signal, shutting down...")
    finally:
        await listener.cleanup()


if __name__ == "__main__":
    asyncio.run(main())