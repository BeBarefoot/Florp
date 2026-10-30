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
    inference_border_enabled: bool = True
    inference_border_fraction: float = 0.12
    inference_border_min_px: int = 32
    wall_segmentation_weights: str = ''
    wall_segmentation_provider: str = 'yytsi'
    # Explicit local evaluation only; no weights or upstream code downloaded.
    workspace_semantic_source: str = ''
    workspace_semantic_weights: str = ''
    workspace_semantic_device: str = 'cpu'
    workspace_semantic_rotations: int = 1
    yytsi_run_dir: str = './models/yytsi'
    yytsi_checkpoint: str = 'best.safetensors'
    yytsi_device: str = 'auto'
    segmentation_multiscale: bool = True
    segmentation_tile_size: int = 448
    segmentation_tile_overlap: float = 0.30
    segmentation_max_tiles: int = 64
    segmentation_wall_threshold: float = 0.46
    llm_max_completion_tokens: int = 8192
    max_upload_mb: int = 20
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
settings = Settings()
