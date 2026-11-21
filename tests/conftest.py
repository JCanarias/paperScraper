"""config.py needs the addresses of the APIs; the tests don't call them, but import the modules that read them."""
import os

for variable in ("OPENALEX_API_URL", "SEMANTIC_SCHOLAR_API_URL", "CUSTOM_LEGAL_SOURCE_API_URL", "UNPAYWALL_API_URL",
                 "UNPAYWALL_EMAIL", "CORE_API_URL", "INTERNET_ARCHIVE_URL", "GUTENDEX_API_URL"):
    os.environ.setdefault(variable, "https://example.org")
