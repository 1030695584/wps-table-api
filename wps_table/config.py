import os
from typing import Dict
from dotenv import load_dotenv


def load_settings(base_dir: str) -> Dict[str, str]:
    load_dotenv(os.path.join(base_dir, ".env"))
    return {
        "client_id": os.getenv("WPS_CLIENT_ID", ""),
        "client_secret": os.getenv("WPS_CLIENT_SECRET", ""),
        "file_id": os.getenv("WPS_FILE_ID", ""),
    }
