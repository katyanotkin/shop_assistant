from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_cloud_project: str
    # Email notification is optional — omit to skip and rely on CSV only
    notify_email: Optional[str] = None
    gmail_app_password: Optional[str] = None
    gmail_from: str = ""
    match_score_threshold: float = 7.0
    partial_score_threshold: float = 4.0
    fetch_timeout: float = 12.0
    max_candidates: int = 20

    model_config = {"env_file": ".env"}
