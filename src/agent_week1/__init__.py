import anthropic
from anthropic.types import MessageParam
import os


def main() -> None:
    print("Hello from agent-week1!")

    # Initialize the client (pointing to DeepSeek's Anthropic-compatible endpoint)
    client = anthropic.Anthropic(
        base_url=os.environ["ANTHROPIC_BASE_URL"],
        api_key=os.environ["ANTHROPIC_API_KEY"] # It's recommended to read this from an environment variable
    )

    # Send a message request
    messages: list[MessageParam] = [
        {
            "role": "user",
            "content": "Hi, introduce yourself!",
        }
    ]

    with client.messages.stream(
            model="deepseek-v4-pro",
            max_tokens=1000,
            system="Your name is Serenity. You are a helpful assistant.",
            messages=messages,
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
