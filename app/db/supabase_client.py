# app/db/supabase_client.py
import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Module-level singleton — one connection shared across the app.
# Creating a new client on every request wastes time and resources.
_client: Client = None


def get_client() -> Client:
    """
    Returns the Supabase client, creating it on first call.
    This is the Singleton pattern — one instance for the lifetime
    of the application.
    """
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")

        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set in .env"
            )

        _client = create_client(url, key)
        logger.info("Supabase client initialised")

    return _client