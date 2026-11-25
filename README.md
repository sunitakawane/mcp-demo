# Notes Assistant (MCP demo)

A terminal notes app that shows the Model Context Protocol (MCP) working end to end.

- `server.py` is an MCP **server**. It exposes a folder of Markdown notes as tools and a resource.
- `client.py` is an MCP **client**. It connects to the server, gives its tools to an LLM, and forwards the model's tool calls back to the server.

The client works with any OpenAI-compatible chat API that supports tool calling. The model is set with environment variables and is never hardcoded.

```
you ──> client.py ──(OpenAI-compatible API)──> LLM (chosen by LLM_MODEL)
              │
              └──(MCP over stdio)──> server.py ──> notes/*.md
```

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Edit `.env`, then choose a provider.

**Local with Ollama (no API key needed):**

```bash
ollama pull llama3.1
```

Use the values in `.env.example` as they are. The model must support tool calling.

**Hosted, for example OpenAI:**

```
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=<any tool-calling model your account can use>
```

Any OpenAI-compatible provider works the same way: change the three variables and nothing else.

## Run

```bash
python client.py
```

Commands:

| Command | What it does |
|---|---|
| `/notes` | Reads the `notes://index` resource directly. The model is not involved. |
| `/help` | Lists commands. |
| `/quit` | Exits. |

Anything else is sent to the model, which can call the tools below.

Example requests to try:

- "What notes do I have about MCP?"
- "Create a note called shopping.md with milk, eggs, and bread."
- "Add 'call the dentist' to the welcome note."
- "Read ../secret.txt." (The server refuses paths outside the notes folder.)

## MCP surface

| Kind | Name | Purpose |
|---|---|---|
| Tool | `search_notes(query)` | Case-insensitive search. An empty query lists all notes. |
| Tool | `read_note(name)` | Returns a note's full text. |
| Tool | `create_note(name, content)` | Creates a note. Fails if it already exists. |
| Tool | `append_to_note(name, text)` | Adds text to the end of an existing note. |
| Resource | `notes://index` | File name, title, and size of every note. |

## How it works

1. **Connect.** `client.py` starts `server.py` as a subprocess and talks to it over stdin and stdout using JSON-RPC.
2. **Discover.** The client calls `list_tools()`. The server returns each tool's name, description, and input schema, which come from the function's name, docstring, and type hints.
3. **Decide.** The client sends those tools to the model with your message. The model either answers directly or requests a tool call.
4. **Execute.** For each requested call, the client calls `call_tool()` on the server, which runs the Python function.
5. **Reply.** The client sends the result back to the model, which writes the final answer.

## Safety

Every note path is resolved and must stay inside `NOTES_DIR`. Paths such as `../` are refused with an error that the model can see and report.

## Add a tool

Add a decorated function to `server.py`. Write a clear docstring, because the model uses it to decide when to call the tool:

```python
@mcp.tool()
def count_notes() -> int:
    """Return how many notes exist."""
    return len(_all_notes())
```

Restart `client.py`. The client needs no changes.

## Project layout

```
server.py          MCP server: tools, resource, path safety
client.py          MCP client: connects, runs the model loop, handles commands
notes/             sample notes
.env.example       configuration template
requirements.txt   dependencies
.gitignore         keeps .env and the virtual environment out of git
```

## Not yet included

Automated tests will be added later.
