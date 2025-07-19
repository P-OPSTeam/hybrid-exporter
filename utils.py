import logging
from datetime import datetime
import re

def parse_docker_timestamp(timestamp_str: str) -> datetime:
    """
    Parses a Docker container creation timestamp string into a datetime object.
    Example format: "2025-07-09T14:27:56.123456789Z"
    """
    try:
        # Remove nanoseconds if present
        if '.' in timestamp_str:
            timestamp_str = timestamp_str.split('.')[0]
        # Ensure it's timezone-aware: Docker uses Z for UTC
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        # If timestamp has no timezone offset, assume UTC
        if re.search(r"[+-]\d{2}:\d{2}$", timestamp_str) is None:
            timestamp_str += '+00:00'

        # Parse the string into a timezone-aware datetime object
        # The format needs to match exactly, including potential timezone info
        # Example: "2025-07-09T14:27:56+00:00"
        parsed_dt = datetime.strptime(timestamp_str, "%Y-%m-%dT%H:%M:%S%z")
        return parsed_dt
    except ValueError as e:
        logging.error(f"Error parsing Docker timestamp '{timestamp_str}': {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during timestamp parsing: {e}")
        return None