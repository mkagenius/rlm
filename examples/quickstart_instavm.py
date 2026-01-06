"""
Quickstart example using InstaVM environment.

This demonstrates how to use RLM with InstaVM for fast, isolated code execution.
"""

import os

from dotenv import load_dotenv

from rlm import RLM
from rlm.logger import RLMLogger

load_dotenv()

logger = RLMLogger(log_dir="./logs")

rlm = RLM(
    backend="openai",  # or "portkey", "anthropic", etc.
    backend_kwargs={
        "model_name": "gpt-5-nano",  # or any other model
        "api_key": os.getenv("OPENAI_API_KEY"),
    },
    environment="instavm",  # Use InstaVM for code execution
    environment_kwargs={
        "api_key": os.getenv("INSTAVM_API_KEY"),  # Optional, will use env var if not set
        "timeout": 300,  # Execution timeout in seconds (default: 300)
        # "base_url": "https://api.instavm.io",  # Optional, default is already set
    },
    max_depth=1,
    logger=logger,
    verbose=True,  # For printing to console with rich, disabled by default.
)

result = rlm.completion("Print me the first 100 powers of two, each on a newline.")

print(result)
