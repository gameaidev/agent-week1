from anthropic.types import ToolParam


TOOLS: list[ToolParam] = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file located inside the project workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "A workspace-relative path, such as README.md.",
                }
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_bash",
        "description": (
            "Run a Bash script inside the project workspace after the user "
            "explicitly approves the request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "A workspace-relative Bash script path.",
                },
            },
            "required": ["filepath"],
            "additionalProperties": False,
        },
    },
    {
        "name": "http_get",
        "description": "Retrieve a bounded text response from a public HTTPS URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                    "description": "A public HTTPS URL without embedded credentials.",
                }
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
]
