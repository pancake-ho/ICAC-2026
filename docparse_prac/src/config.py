"""
API KEY 및 경로 설정/파일 읽기 수행
"""

from pathlib import Path
import os
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = BASE_DIR / "samples"
OUTPUTS_DIR = BASE_DIR / "outputs"

load_dotenv(BASE_DIR / ".env")

UPSTAGE_API_KEY = os.getenv("ICAC_KEY")

DOCUMENT_PARSE_URL = "https://api.upstage.ai/v1/document-digitization"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".tiff",
    ".webp",
}

DEFAULT_MODEL = "document-parse"
DEFAULT_OUTPUT_FORMATS = "['markdown', 'html']"