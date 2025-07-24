import os
import logging
import docker
from dotenv import load_dotenv
from datetime import datetime, timezone
import utils
import websockets
import json
from web3 import Web3, HTTPProvider
import asyncio
from prometheus_client import start_http_server, Gauge, Counter

load_dotenv()

# Configuration
WS_ENDPOINT = os.getenv("WS_ENDPOINT")
RPC_ENDPOINT = os.getenv("RPC_ENDPOINT")
OPERATOR_ADDRESS = os.getenv("OPERATOR_ADDRESS")
METRICS_PORT = int(os.getenv("METRICS_PORT", "8000"))
METRIC_UPDATE_TIMEOUT_SECONDS = int(os.getenv("METRIC_UPDATE_TIMEOUT_SECONDS", 60))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
RECONNECT_TIMEOUT = os.getenv("RECONNECT_TIMEOUT", 5)

# Setup logging
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=LOG_LEVEL, format=log_format)

# Initialize Docker client
try:
    docker_client = docker.from_env()
except Exception as e:
    logging.error(f"Failed to initialize Docker client: {e}")
    docker_client = None

# Start Prometheus metrics HTTP server
start_http_server(METRICS_PORT)

# Define Global Prometheus metrics
hybrid_node_uptime_metric = Gauge('hybrid_node_uptime', 'Hybrid node container uptime in seconds', ['op_add'])
heartbeat_metric = Gauge('hybrid_heartbeat', 'Epoch timestamp of last heartbeat transaction', ['op_add'])
rpc_request_status_metric = Counter('rpc_request_status', 'RPC request status', ['op_add', 'endpoint', 'status'])

# --- Metric Definitions ---

# hybrid_node_uptime: Gauge (integer value)
# 0: Hybrid node container is down.
# Positive number: Uptime of the Hybrid node container in seconds.
hybrid_node_uptime_seconds = 0
hybrid_node_container_id = None

# hybrid_heartbeat: Gauge (timestamp in epoch format)
# Timestamp of the last successful heartbeat transaction.
hybrid_heartbeat_timestamp = 0

# rpc_request_status: Counter
# Tracks success/failure of RPC calls for hybrid_heartbeat metric.
# Labels: op_add, endpoint, status (success/fail)
rpc_request_status_success = 0
rpc_request_status_fail = 0

# --- Helper Functions ---

def get_hybrid_node_container_status():
    global hybrid_node_uptime_seconds, hybrid_node_container_id
    if not docker_client:
        logging.error("Docker client not initialized.")
        return 0

    try:
        # Find the hybrid node container
        # Image name is "nodeops/hybrid-node:latest" as per projectBrief.md
        hybrid_container = None
        for container in docker_client.containers.list():
            if container.image.tags and "nodeops/hybrid-node:latest" in container.image.tags:
                hybrid_container = container
                break

        if hybrid_container:
            hybrid_node_container_id = hybrid_container.short_id
            if hybrid_container.status == "running":
                # Calculate uptime
                created_at_str = hybrid_container.attrs['Created']
                # Use the utility function to parse the timestamp
                created_at = utils.parse_docker_timestamp(created_at_str)

                if created_at:
                    now = datetime.now(timezone.utc)
                    uptime = (now - created_at).total_seconds()
                    hybrid_node_uptime_seconds = int(uptime)
                    # Update Prometheus gauge
                    hybrid_node_uptime_metric.labels(op_add=OPERATOR_ADDRESS).set(hybrid_node_uptime_seconds)
                    logging.debug(f"Hybrid node container {hybrid_node_container_id} is running. Uptime: {hybrid_node_uptime_seconds}s")
                    return hybrid_node_uptime_seconds
                else:
                    logging.error(f"Failed to parse container creation time for {hybrid_node_container_id}")
                    return 0
            else:
                logging.info(f"Hybrid node container {hybrid_node_container_id} is not running. Status: {hybrid_container.status}")
                hybrid_node_uptime_seconds = 0
                hybrid_node_uptime_metric.labels(op_add=OPERATOR_ADDRESS).set(0)
                return 0
        else:
            logging.info("Hybrid node container not found.")
            hybrid_node_uptime_seconds = 0
            hybrid_node_uptime_metric.labels(op_add=OPERATOR_ADDRESS).set(0)
            return 0
    except Exception as e:
        logging.error(f"Error checking Docker container status: {e}")
        return 0

def update_metrics():
    """
    Updates all Prometheus metrics.
    """
    logging.info("Starting metric update cycle...")

    # Update hybrid_node_uptime
    current_uptime = get_hybrid_node_container_status()
    hybrid_node_uptime_metric.labels(op_add=OPERATOR_ADDRESS).set(current_uptime)
    logging.info(f"hybrid_node_uptime: {current_uptime}s (op_add={OPERATOR_ADDRESS})")

    # Update hybrid_heartbeat and RPC status
    heartbeat_metric.labels(op_add=OPERATOR_ADDRESS).set(hybrid_heartbeat_timestamp)
    logging.info(f"hybrid_heartbeat: {hybrid_heartbeat_timestamp} (op_add={OPERATOR_ADDRESS})")
    logging.info(f"rpc_request_status: success={rpc_request_status_success}, fail={rpc_request_status_fail} (op_add={OPERATOR_ADDRESS}")

    logging.info("Metric update cycle finished.")

async def _listen_for_heartbeats(operator_address):
    """
    Listens for new blocks via WebSocket, fetches full block data,
    filters for heartbeat transactions from operator_address,
    and updates global hybrid_heartbeat_timestamp and RPC status counters.
    """
    logging.info(f"Listening for heartbeat transactions from operator {operator_address}")

    global hybrid_heartbeat_timestamp, rpc_request_status_success, rpc_request_status_fail

    web3_http = Web3(HTTPProvider(RPC_ENDPOINT))
    while True:
        try:
            async with websockets.connect(WS_ENDPOINT) as ws:
                # Subscribe to new block headers
                subscribe_msg = {
                "jsonrpc": "2.0", "method": "eth_subscribe",
                "params": ["newHeads"], "id": 1
            }
                try:
                    await ws.send(json.dumps(subscribe_msg))
                    rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="success").inc()
                    rpc_request_status_success += 1
                except Exception as e:
                    rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="fail").inc()
                    logging.error(f"WS subscribe failed: {e}")
                    rpc_request_status_fail += 1
                    return
                try:
                    resp = await ws.recv()
                    rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="success").inc()
                    rpc_request_status_success += 1
                except Exception as e:
                    rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="fail").inc()
                    logging.error(f"WS subscribe confirmation failed: {e}")
                    rpc_request_status_fail += 1
                    return
                msg = json.loads(resp)
                sub_id = msg.get("result")
                if not sub_id:
                    logging.error(f"Subscription failed: {msg}")
                    logging.info(f"Reconnecting to WebSocket in {RECONNECT_TIMEOUT} seconds...")
                    rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="fail").inc()
                    rpc_request_status_fail += 1
                    await asyncio.sleep(RECONNECT_TIMEOUT)
                    continue
                logging.info(f"Subscribed to newHeads with subscription id {sub_id}")
                # Listen for new block headers
                while True:
                    try:
                        data = await ws.recv()
                        rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="success").inc()
                        rpc_request_status_success += 1
                    except Exception as e:
                        rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="fail").inc()
                        rpc_request_status_fail += 1
                        logging.error(f"WS recv failed: {e}")
                        break
                    msg = json.loads(data)
                    params = msg.get("params")
                    if params and params.get("subscription") == sub_id:
                        header = params.get("result", {})
                        # Fetch block by hash with full transactions for easier parsing
                        block_hash = header.get("hash")
                        if not block_hash:
                            continue
                        try:
                            block = web3_http.eth.get_block(block_hash, full_transactions=True)
                            # Instrument HTTP block fetch success
                            rpc_request_status_metric.labels(op_add=operator_address, endpoint=RPC_ENDPOINT, status="success").inc()
                            rpc_request_status_success += 1
                        except Exception as e:
                            # Instrument HTTP block fetch failure
                            rpc_request_status_metric.labels(op_add=operator_address, endpoint=RPC_ENDPOINT, status="fail").inc()
                            rpc_request_status_fail += 1
                            logging.error(f"Failed to fetch block {block_hash}: {e}")
                            continue
                        # Extract timestamp directly
                        timestamp = block.timestamp if hasattr(block, 'timestamp') else block['timestamp']

                        logging.debug(f"Checking block {block.number if hasattr(block, 'number') else int(block['number'], 16)} with hash {block_hash} for {len(block.transactions)} transaction(s) from {operator_address}...")
                        # Check each transaction
                        for tx in block.transactions:
                            # Normalize sender and input fields
                            tx_from = getattr(tx, 'from', None) or getattr(tx, 'sender', '')
                            tx_input = getattr(tx, 'input', '')
                            # Convert bytes input to hex string
                            if isinstance(tx_input, (bytes, bytearray)):
                                tx_input = '0x' + tx_input.hex()
                            # Check for matching heartbeat signature
                            if str(tx_from).lower() == operator_address.lower() and tx_input.startswith("0x3defb962"):
                                hybrid_heartbeat_timestamp = timestamp
                                # Update Prometheus metrics
                                heartbeat_metric.labels(op_add=operator_address).set(timestamp)
                                rpc_request_status_metric.labels(op_add=operator_address, endpoint=RPC_ENDPOINT, status="success").inc()
                                rpc_request_status_success += 1
                                logging.info(f"Heartbeat tx found in block {block_hash}, timestamp {timestamp}")
                                break
        except websockets.exceptions.ConnectionClosed as cc:
            logging.error(f"WebSocket connection closed: {cc}")
            rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="fail").inc()
            rpc_request_status_fail += 1
            await asyncio.sleep(RECONNECT_TIMEOUT)
            logging.info(f"Reconnecting to WebSocket in {RECONNECT_TIMEOUT} seconds...")
        except Exception as e:
            logging.error(f"Unexpected error in heartbeat listener: {e}")
            rpc_request_status_metric.labels(op_add=operator_address, endpoint=WS_ENDPOINT, status="fail").inc()
            rpc_request_status_fail
            await asyncio.sleep(RECONNECT_TIMEOUT)
            logging.info(f"Reconnecting to WebSocket in {RECONNECT_TIMEOUT} seconds...")

# --- Main Execution ---

async def main_async():
    """
    Main loop using asyncio.
    """
    logging.info("Starting Hybrid Node Exporter (asyncio mode)...")
    if not WS_ENDPOINT or not OPERATOR_ADDRESS or not RPC_ENDPOINT:
        logging.error("Configuration error: WS_ENDPOINT, RPC_ENDPOINT and OPERATOR_ADDRESS must be set in .env file.")
        return

    logging.info(f"Operator address: {OPERATOR_ADDRESS}")
    logging.info(f"RPC endpoint: from {RPC_ENDPOINT}")
    logging.info(f"WebSocket endpoint: {WS_ENDPOINT}")

    # Start the heartbeat listener as a background task
    # Ensure WS_ENDPOIN/RPC_ENDPOINT are valid URLs
    if (WS_ENDPOINT and (WS_ENDPOINT.startswith("ws://") or WS_ENDPOINT.startswith("wss://")) or
       (RPC_ENDPOINT and RPC_ENDPOINT.startswith("http://") or RPC_ENDPOINT.startswith("https://"))):
        # Start heartbeat listener task
        asyncio.create_task(_listen_for_heartbeats(OPERATOR_ADDRESS))
    else:
        logging.warning("WS_ENDPOINT is not a websocket URL or RPC_ENDPOINT is/are not a valid URL. \
                         Heartbeat monitoring will not start.")

    while True:
        update_metrics()
        logging.info(f"Waiting for {METRIC_UPDATE_TIMEOUT_SECONDS} seconds until next update...")
        await asyncio.sleep(METRIC_UPDATE_TIMEOUT_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logging.info("Exporter stopped by user.")
    except Exception as e:
        logging.critical(f"An unhandled exception occurred: {e}")
