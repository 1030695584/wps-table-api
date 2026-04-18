from loguru import logger

from .api import WPS365DBSheetAPI
from .config import load_settings


def run(base_dir: str) -> None:
    settings = load_settings(base_dir)
    client_id = settings["client_id"]
    client_secret = settings["client_secret"]
    file_id = settings["file_id"]

    api = WPS365DBSheetAPI(
        client_id=client_id,
        client_secret=client_secret,
    )

    if not client_id or not client_secret:
        logger.error("请先设置环境变量 WPS_CLIENT_ID、WPS_CLIENT_SECRET")
        return
    if not file_id:
        logger.error("请先设置环境变量 WPS_FILE_ID")
        return

    logger.info("获取 Schema...")
    result = api.get_schema(file_id)
    logger.info(result)
