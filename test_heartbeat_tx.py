#!/usr/bin/env python3
"""
Test querying a specific transaction to verify heartbeat signature and extract its timestamp.
"""
import os
from dotenv import load_dotenv
from web3 import Web3, HTTPProvider

# Load env
load_dotenv()
RPC_ENDPOINT = os.getenv("RPC_ENDPOINT")

HEARTBEAT_SIG = "0x3defb962"
# Provided heartbeat transaction hash
TX_HASH = "0x2f68e3e0bd58c901dc4d03940569e2156c426ceacdebdb8f111045d50b92dfbf"
OPERATOR_ADDRESS = "0x8a6d025f1102E2768bF60381711CaBe9299fbA80".lower()

def main():
    if not RPC_ENDPOINT:
        print("RPC_ENDPOINT not set in .env")
        return

    # Connect HTTP provider
    w3 = Web3(HTTPProvider(RPC_ENDPOINT))
    try:
        tx = w3.eth.get_transaction(TX_HASH)
    except Exception as e:
        print(f"Error fetching transaction {TX_HASH}: {e}")
        return

    # Normalize input data
    input_data = tx.input if hasattr(tx, 'input') else tx['input']
    if isinstance(input_data, (bytes, bytearray)):
        input_data = '0x' + input_data.hex()

    print(f"Transaction input: {input_data}")

    # Check signature
    if input_data.startswith(HEARTBEAT_SIG):
        # Fetch block to get timestamp
        blk = w3.eth.get_block(tx.blockNumber if hasattr(tx, 'blockNumber') else tx['blockNumber'], full_transactions=False)
        ts = blk.timestamp if hasattr(blk, 'timestamp') else int(blk['timestamp'], 16)
        blkhash = blk.hash.hex() if hasattr(blk, 'hash') else blk['hash']
        blknumber = blk.number if hasattr(blk, 'number') else int(blk['number'], 16)
        print(f"Heartbeat detected in tx {TX_HASH}")
        print(f"Block number: {blknumber} at timestamp {ts}")

        # Normalize sender and input fields from original code
        tx_from = getattr(tx, 'from', None) or getattr(tx, 'sender', '')
        tx_input = getattr(tx, 'input', '')
        # Convert bytes input to hex string
        if isinstance(tx_input, (bytes, bytearray)):
            tx_input = '0x' + tx_input.hex()
        # Check for matching heartbeat signature
        if str(tx_from).lower() == OPERATOR_ADDRESS.lower() and tx_input.startswith("0x3defb962"):
            print(f"-> Heartbeat tx found in block {blknumber} hash 0x{blkhash} and timestamp {ts}")
    else:
        print(f"No heartbeat signature in tx {TX_HASH}")

if __name__ == "__main__":
    main()
