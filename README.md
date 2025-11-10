# Hybrid Node Exporter

This exporter exposes metrics related to a Hybrid node, specifically for a given operator EVM address. It is designed to run as a Prometheus exporter and monitor:

- Docker container uptime for the hybrid node
- Heartbeat transactions for a specific operator address
- RPC/WebSocket request status and errors

## Configuration

Set the following environment variables (see `.env.example`):

- `WS_ENDPOINT`: WebSocket endpoint for block header subscription
- `RPC_ENDPOINT`: HTTP RPC endpoint for block/tx queries
- `OPERATOR_ADDRESSES`: EVM addresses to monitor (comma-separated)
- `METRIC_UPDATE_TIMEOUT_SECONDS`: Metric update interval (seconds)
- `METRICS_PORT`: Port for Prometheus metrics (default: 8000)
- `LOG_LEVEL`: Logging verbosity (default: INFO)
- `RECONNECT_TIMEOUT`: Delay before reconnecting WebSocket (seconds)

## Metrics

- `hybrid_node_uptime` (Gauge): Uptime of the hybrid node Docker container in seconds
- `hybrid_heartbeat` (Gauge): Timestamp of the last successful heartbeat transaction
- `rpc_request_status` (Counter): Status of RPC/WebSocket requests for heartbeat detection. Labels: `op_add`, `endpoint`, `status` (`success`/`fail`)

## Usage

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Run the exporter:

   ```bash
   python hybrid_node_exporter.py
   ```

3. Metrics are exposed at `http://localhost:8000/metrics` (or your configured port)

## Test Scripts

- `test_websocket.py`: Tests WebSocket subscription and block header reception
- `test_heartbeat_tx.py`: Verifies heartbeat transaction detection and block timestamp extraction for a given tx hash

## Docker Container Uptime

The exporter checks for a running Docker container named `nodeops/hybrid-node:latest` and reports its uptime in seconds.

## Error Handling & Logging

- All RPC and WebSocket errors are logged with timestamps and severity
- The exporter automatically reconnects to the WebSocket on failure and increments failure counters for Prometheus

## Requirements

See `requirements.txt` for all Python dependencies:

- prometheus_client
- python-dotenv
- web3
- docker
- websockets
- setuptools<81