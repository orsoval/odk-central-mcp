# odk-central-mcp

MCP server for [ODK Central](https://docs.getodk.org/central-intro/) — expose your projects, forms, submissions and entities to Claude Desktop via [pyODK](https://getodk.github.io/pyodk/).

## Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List all projects on the server |
| `set_default_project` | Switch the default project for the current session |
| `list_forms` | List forms in a project |
| `get_form_details` | Get metadata for a specific form |
| `create_form` | Create (publish) a new form from an XLSForm/XML file |
| `update_form` | Update an existing form's definition and/or attachments |
| `list_submissions` | List submissions for a form |
| `get_submission_data` | Get tabular submission data (OData) with filtering/pagination |
| `list_entity_lists` | List Entity Lists (datasets) in a project |
| `list_entities` | List entities in an Entity List |
| `create_entity` | Create a new entity |
| `central_api_get` | Raw GET request to any Central API endpoint |

## Installation for Claude Desktop

Clone this repo somewhere on your machine, e.g. `~/Dev/odk-central-mcp`, then add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the equivalent path on your OS:

```json
{
  "mcpServers": {
    "odk-central": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/odk-central-mcp", "odk-central-mcp"],
      "env": {
        "ODK_CENTRAL_URL": "https://your-central-server.com",
        "ODK_CENTRAL_USERNAME": "your-email@example.com",
        "ODK_CENTRAL_PASSWORD": "your-password",
        "ODK_CENTRAL_PROJECT_ID": "1"
      }
    }
  }
}
```

> **Security note**: credentials are stored in plain text in the config file on your machine.
> Consider using a dedicated Central Web User with limited permissions, and never commit
> your real config file to a public repository.

## Requirements

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- An ODK Central server (v2024.1+)

## Development

```bash
git clone https://github.com/orsoval/odk-central-mcp.git
cd odk-central-mcp
uv sync
uv run odk-central-mcp
```

## License

MIT
