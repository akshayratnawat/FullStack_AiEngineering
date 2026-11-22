"""Send one prompt to the configured chat deployment and print the reply.

Run from the backend folder:
    uv run python scripts/ask_model.py
    uv run python scripts/ask_model.py "Say hello in five words."

Proves the chat deployment name, endpoint and key work. Makes one small paid call.
"""

import sys

from pydantic_ai import Agent

from app.assistant.model import create_chat_model

prompt = sys.argv[1] if len(sys.argv) > 1 else "Reply with the single word: ready"
result = Agent(create_chat_model()).run_sync(prompt)
print(result.output)
