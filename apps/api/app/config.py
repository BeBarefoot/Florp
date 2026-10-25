from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    database_url: str = 'sqlite:///./data/florp.db'
    storage_path: str = './data/storage'
    cors_origins: str = 'http://localhost:3000'
    llm_api_key: str = ''
    llm_model: str = 'gpt-4.1-mini'
    llm_base_url: str = 'https://api.openai.com/v1'
    image_api_key: str = ''
    image_model: str = 'fal-ai/flux-control-lora-depth'
    fal_api_base: str = 'https://queue.fal.run'
    pretrained_yolo_weights: str = ''
    llm_max_completion_tokens: int = 8192
    max_upload_mb: int = 20
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
settings = Settings()
