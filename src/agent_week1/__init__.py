import anthropic
import os
from anthropic.types import (
    MessageParam,
    ThinkingConfigEnabledParam,
    OutputConfigParam,
)


def main() -> None:
    print("Hello from agent-week1!")

    # Initialize the client (pointing to DeepSeek's Anthropic-compatible endpoint)
    client = anthropic.Anthropic(
        base_url=os.environ["ANTHROPIC_BASE_URL"],
        api_key=os.environ["ANTHROPIC_API_KEY"]  # It's recommended to read this from an environment variable
    )

    # Send a message request
    messages: list[MessageParam] = [
        {
            "role": "user",
            "content": "Hi, introduce yourself!",
        }
    ]

    thinking_config: ThinkingConfigEnabledParam = {
        "type": "enabled",
        "budget_tokens": 1024,
    }

    output_config: OutputConfigParam = {
        "effort": "high",
    }

    with client.messages.stream(
            model="deepseek-v4-pro",
            max_tokens=2000,
            system="Your name is Serenity. You are a helpful assistant.",
            messages=messages,
            thinking=thinking_config,
            output_config=output_config,
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
