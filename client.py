"""
Terminal client for the Notes Assistant MCP server.

Works with any OpenAI-compatible chat API that supports tool calling
(Ollama, LM Studio, OpenAI, OpenRouter, vLLM, ...). The model is chosen
entirely by environment variables; nothing is hardcoded.

  LLM_BASE_URL  API endpoint (default: https://api.openai.com/v1)
  LLM_API_KEY   API key (any placeholder for local servers)
  LLM_MODEL     model name (required)
  NOTES_DIR     notes folder for the server (optional)

Commands:
  /notes   show the notes://index resource directly (no model involved)
  /help    show commands
  /quit    exit
"""

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client
from openai import OpenAI

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "not-needed")
LLM_MODEL = os.environ.get("LLM_MODEL")

SYSTEM_PROMPT = (
    "You are a notes assistant. The user's notes are Markdown files that you "
    "can search, read, create, and append to using the provided tools. "
    "Always read a note before summarizing or changing it, and never invent "
    "note contents. Keep answers short."
)


class NotesClient:
    def __init__(self) -> None:
        self.llm = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        self.session: ClientSession | None = None
        self.tools: list[dict] = []
        self.history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._stack = AsyncExitStack()

    # ----- MCP connection -----

    async def connect(self) -> None:
        # The SDK passes only a minimal set of environment variables to the
        # server process, so forward NOTES_DIR explicitly if it is set.
        env = get_default_environment()
        if "NOTES_DIR" in os.environ:
            env["NOTES_DIR"] = os.environ["NOTES_DIR"]

        params = StdioServerParameters(
            command=sys.executable,
            args=[str(HERE / "server.py")],
            env=env,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        
        listed = await self.session.list_tools()
        # Convert MCP tool metadata into the OpenAI function-calling format
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
            for t in listed.tools
        ]
        print(f"Connected. Model: {LLM_MODEL}")
        print(f"Tools: {', '.join(t.name for t in listed.tools)}")

    async def close(self) -> None:
        await self._stack.aclose()

    # ----- resources (no model involved) -----

    async def show_index(self) -> None:
        result = await self.session.read_resource("notes://index")
        for content in result.contents:
            print(getattr(content, "text", "(binary content)"))

    # ----- agent loop -----

    async def ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})

        while True:
            response = await asyncio.to_thread(
                self.llm.chat.completions.create,
                model=LLM_MODEL,
                messages=self.history,
                tools=self.tools,
            )
            message = response.choices[0].message
            self.history.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                return message.content or ""

            # The model asked for tools: run each on the MCP server
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                print(f"  [tool] {call.function.name}({args})")

                result = await self.session.call_tool(call.function.name, args)
                output = "\n".join(c.text for c in result.content if c.type == "text")
                if result.isError:
                    output = f"ERROR: {output}"

                self.history.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": output,
                })


def check_config() -> None:
    if not LLM_MODEL:
        sys.exit(
            "LLM_MODEL is not set. Add it to .env or export it, "
            "for example: export LLM_MODEL=llama3.1"
        )


async def main() -> None:
    check_config()
    notes = NotesClient()
    try:
        await notes.connect()
        print("Type a request, or /help for commands.")
        while True:
            user_text = (await asyncio.to_thread(input, "\nyou> ")).strip()
            if not user_text:
                continue
            if user_text in {"/quit", "/exit"}:
                break
            if user_text == "/help":
                print("/notes  show notes index (resource, no model)\n/quit   exit")
                continue
            if user_text == "/notes":
                await notes.show_index()
                continue

            try:
                answer = await notes.ask(user_text)
                print(f"\nassistant> {answer}")
            except Exception as exc:  # network, auth, or model errors
                print(f"\n[error] {exc}")
    finally:
        await notes.close()


if __name__ == "__main__":
    asyncio.run(main()) 