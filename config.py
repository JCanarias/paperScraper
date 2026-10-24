import os
from pathlib import Path

from dotenv import load_dotenv

# Read the variables defined in the .env file next to this one.
load_dotenv(Path(__file__).parent / ".env")

OPENALEX_API_URL = os.environ["OPENALEX_API_URL"]
SEMANTIC_SCHOLAR_API_URL = os.environ["SEMANTIC_SCHOLAR_API_URL"]
CUSTOM_LEGAL_SOURCE_API_URL = os.environ["CUSTOM_LEGAL_SOURCE_API_URL"]
UNPAYWALL_API_URL = os.environ["UNPAYWALL_API_URL"]
UNPAYWALL_EMAIL = os.environ["UNPAYWALL_EMAIL"]
CORE_API_URL = os.environ["CORE_API_URL"]
# Optional: without a key, CORE is skipped.
CORE_API_KEY = os.environ.get("CORE_API_KEY", "")
INTERNET_ARCHIVE_URL = os.environ["INTERNET_ARCHIVE_URL"]
GUTENDEX_API_URL = os.environ["GUTENDEX_API_URL"]
