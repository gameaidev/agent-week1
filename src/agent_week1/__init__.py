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
            "content": "Hi, how are you?",
        }
    ]

    message = client.messages.create(
        model="deepseek-v4-flash",
        max_tokens=1000,
        system="You are a helpful assistant.",
        messages=messages,
    )

    # Print the response
    response_text = "".join(
        block.text
        for block in message.content
        if block.type == "text"
    )

    print(response_text)