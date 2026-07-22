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
    fetch_timeout: float = 8.0
    max_candidates: int = 40
    admin_password: Optional[str] = None
    base_url: Optional[str] = None
    bootstrap_admin_email: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    session_secret: str = "dev-session-secret-change-in-production"

    model_config = {"env_file": ".env"}
