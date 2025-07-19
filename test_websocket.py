import json
import asyncio
import websockets
import requests
import os
import logging
from dotenv import load_dotenv

"""
Test WS and RPC URLs endpoint
"""

load_dotenv()
WEBSOCKET_URL = os.getenv("WS_ENDPOINT")
RPC_URL = os.getenv("RPC_ENDPOINT")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Setup logging
log_format = "%(asctime)s - %(levelname)s - %(message)s"
logging.basicConfig(level=LOG_LEVEL, format=log_format)

if not WEBSOCKET_URL or not RPC_URL:
    logging.error("Please set WS_ENDPOINT and RPC_ENDPOINT in your environment variables.")
    exit(1)

logging.info(f"WebSocket URL: {WEBSOCKET_URL}")
logging.info(f"Using RPC URL: {RPC_URL}")


if __name__ == "__main__":
    async def main():
        try:
            async with websockets.connect(WEBSOCKET_URL) as ws:
                logging.info('Connected to WebSocket')
                subscribe_message = {
                    "jsonrpc": "2.0", "method": "eth_subscribe",
                    "params": ["newHeads"], "id": 1
                }
                await ws.send(json.dumps(subscribe_message))
                async for message in ws:
                    data = json.loads(message)
                    if data.get('method') == 'eth_subscription':
                        block_header = data['params']['result']
                        block_number = int(block_header['number'], 16)
                        # Fetch full block via HTTP RPC to get transaction list
                        payload = {
                            "jsonrpc": "2.0", "id": 1,
                            "method": "eth_getBlockByNumber",
                            "params": [block_header['number'], True]
                        }
                        try:
                            resp = requests.post(RPC_URL, json=payload)
                            resp.raise_for_status()
                            blk = resp.json().get('result', {})
                            txs = blk.get('transactions', [])
                            logging.info(f"Block {block_number} received with {len(txs)} transactions")
                        except Exception as e:
                            logging.error(f"Error fetching block {block_number}: {e}")
        except websockets.exceptions.ConnectionClosed as cc:
            logging.error(f"WebSocket connection closed: {cc}")
        except Exception as e:
            logging.error(f"Unexpected error in heartbeat listener: {e}")
    asyncio.run(main())