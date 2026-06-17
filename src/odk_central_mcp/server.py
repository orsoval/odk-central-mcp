"""
ODK Central MCP Server
======================
Wraps pyODK to expose ODK Central resources as MCP tools for Claude Desktop.

Environment variables (set in claude_desktop_config.json → env):
  ODK_CENTRAL_URL       – Base URL of your Central instance
  ODK_CENTRAL_USERNAME  – Central web user email
  ODK_CENTRAL_PASSWORD  – Central web user password
  ODK_CENTRAL_PROJECT_ID – (optional) Default project ID
"""

import asyncio
import json
import logging
import os
from functools import partial
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("odk_central_mcp")

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "ODK Central",
    instructions=(
        "Serveur MCP pour ODK Central. "
        "Permet de lister les projets, formulaires, soumissions et entités "
        "d'un serveur ODK Central via pyODK."
    ),
)


# ---------------------------------------------------------------------------
# pyODK client helper (lazy, sync → async bridge)
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    """Return a shared pyODK Client, creating it on first call."""
    global _client
    if _client is not None:
        return _client

    from pyodk.client import Client

    url = os.environ.get("ODK_CENTRAL_URL", "")
    user = os.environ.get("ODK_CENTRAL_USERNAME", "")
    pwd = os.environ.get("ODK_CENTRAL_PASSWORD", "")
    project = os.environ.get("ODK_CENTRAL_PROJECT_ID")

    if not all([url, user, pwd]):
        raise RuntimeError(
            "Missing ODK Central credentials. "
            "Set ODK_CENTRAL_URL, ODK_CENTRAL_USERNAME, and ODK_CENTRAL_PASSWORD."
        )

    # Write a temporary pyodk config so Client() can pick it up
    import tempfile, textwrap, pathlib

    config_content = textwrap.dedent(f"""\
        [central]
        base_url = "{url}"
        username = "{user}"
        password = "{pwd}"
    """)
    if project:
        config_content += f"default_project_id = {project}\n"

    config_path = pathlib.Path(tempfile.gettempdir()) / ".pyodk_config_mcp.toml"
    config_path.write_text(config_content)
    cache_path = pathlib.Path(tempfile.gettempdir()) / ".pyodk_cache_mcp.toml"

    project_id = int(project) if project else None
    _client = Client(
        config_path=str(config_path),
        cache_path=str(cache_path),
        project_id=project_id,
    )
    _client.open()
    logger.info("pyODK client connected to %s", url)
    return _client


async def _run_sync(func, *args, **kwargs) -> Any:
    """Run a synchronous pyODK call in a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _serialize(obj: Any) -> str:
    """Convert pyODK response objects to JSON string."""
    if obj is None:
        return json.dumps(None)
    if isinstance(obj, list):
        return json.dumps(
            [_obj_to_dict(item) for item in obj],
            default=str, ensure_ascii=False, indent=2,
        )
    return json.dumps(
        _obj_to_dict(obj),
        default=str, ensure_ascii=False, indent=2,
    )


def _obj_to_dict(obj: Any) -> Any:
    """Best-effort conversion of a pyODK model to a dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
    return obj


# ---------------------------------------------------------------------------
# TOOLS — Projects
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_projects() -> str:
    """List all projects on the ODK Central server.

    Returns project id, name, description, creation date, and archived status.
    """
    client = _get_client()
    projects = await _run_sync(client.projects.list)
    return _serialize(projects)


@mcp.tool()
async def set_default_project(project_id: int) -> str:
    """Switch the default project for the current session.

    All subsequent calls without an explicit project_id will use this project.
    Does not modify the config file — resets on restart.

    Args:
        project_id: The project ID to use as the new default.
    """
    client = _get_client()
    client.project_id = project_id
    return json.dumps({"default_project_id": project_id, "status": "ok"})


# ---------------------------------------------------------------------------
# TOOLS — Forms
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_forms(project_id: Optional[int] = None) -> str:
    """List all forms in a project.

    Args:
        project_id: Project ID. Uses the default project if not specified.
    """
    client = _get_client()
    projects_id = project_id or client.project_id
    forms = await _run_sync(client.forms.list, project_id=projects_id)
    return _serialize(forms)


@mcp.tool()
async def get_form_details(form_id: str, project_id: Optional[int] = None) -> str:
    """Get detailed metadata for a specific form.

    Args:
        form_id: The xmlFormId of the form.
        project_id: Project ID. Uses the default project if not specified.
    """
    client = _get_client()
    pid = project_id or client.project_id
    form = await _run_sync(client.forms.get, form_id=form_id, project_id=pid)
    return _serialize(form)


@mcp.tool()
async def create_form(
    definition_path: str,
    project_id: Optional[int] = None,
    form_id: Optional[str] = None,
    attachments: Optional[list] = None,
) -> str:
    """Create (publish) a new form on ODK Central from an XLSForm or XML file.

    Args:
        definition_path: Absolute path to the .xlsx (XLSForm) or .xml file on your machine.
        project_id: Project ID. Uses the default project if not specified.
        form_id: Optional xmlFormId override. If omitted, derived from the definition.
        attachments: Optional list of absolute file paths for form attachments (e.g. CSV media).
    """
    client = _get_client()
    pid = project_id or client.project_id
    kwargs: dict = {"definition": definition_path, "project_id": pid}
    if form_id:
        kwargs["form_id"] = form_id
    if attachments:
        kwargs["attachments"] = attachments
    form = await _run_sync(client.forms.create, **kwargs)
    return _serialize(form)


@mcp.tool()
async def update_form(
    form_id: str,
    definition_path: Optional[str] = None,
    project_id: Optional[int] = None,
    attachments: Optional[list] = None,
) -> str:
    """Update an existing form with a new definition and/or new attachments.

    At least one of definition_path or attachments must be provided.

    Args:
        form_id: The xmlFormId of the form to update.
        definition_path: Path to the new .xlsx or .xml definition file.
        project_id: Project ID. Uses the default project if not specified.
        attachments: List of absolute file paths for updated form attachments.
    """
    client = _get_client()
    pid = project_id or client.project_id
    kwargs: dict = {"form_id": form_id, "project_id": pid}
    if definition_path:
        kwargs["definition"] = definition_path
    if attachments:
        kwargs["attachments"] = attachments
    form = await _run_sync(client.forms.update, **kwargs)
    return _serialize(form)


# ---------------------------------------------------------------------------
# TOOLS — Submissions
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_submissions(
    form_id: str,
    project_id: Optional[int] = None,
) -> str:
    """List all submissions for a form.

    Args:
        form_id: The xmlFormId of the form.
        project_id: Project ID. Uses the default project if not specified.
    """
    client = _get_client()
    pid = project_id or client.project_id
    subs = await _run_sync(
        client.submissions.list, form_id=form_id, project_id=pid,
    )
    return _serialize(subs)


@mcp.tool()
async def get_submission_data(
    form_id: str,
    project_id: Optional[int] = None,
    filter: Optional[str] = None,
    top: Optional[int] = None,
    skip: Optional[int] = None,
) -> str:
    """Get submission data as a table (OData format).

    Returns structured rows that can be analyzed directly.

    Args:
        form_id: The xmlFormId of the form.
        project_id: Project ID. Uses the default project if not specified.
        filter: OData $filter expression, e.g. "__system/submissionDate ge 2024-01-01".
        top: Maximum number of rows to return.
        skip: Number of rows to skip (pagination).
    """
    client = _get_client()
    pid = project_id or client.project_id
    kwargs: dict[str, Any] = {"form_id": form_id, "project_id": pid}
    if filter:
        kwargs["filter"] = filter
    if top:
        kwargs["top"] = top
    if skip:
        kwargs["skip"] = skip
    data = await _run_sync(client.submissions.get_table, **kwargs)
    return _serialize(data)


# ---------------------------------------------------------------------------
# TOOLS — Entity Lists (Datasets)
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_entity_lists(project_id: Optional[int] = None) -> str:
    """List all Entity Lists (datasets) in a project.

    Args:
        project_id: Project ID. Uses the default project if not specified.
    """
    client = _get_client()
    pid = project_id or client.project_id
    el = await _run_sync(client.entity_lists.list, project_id=pid)
    return _serialize(el)


# ---------------------------------------------------------------------------
# TOOLS — Entities
# ---------------------------------------------------------------------------
@mcp.tool()
async def list_entities(
    entity_list_name: str,
    project_id: Optional[int] = None,
) -> str:
    """List entities in an Entity List.

    Args:
        entity_list_name: Name of the Entity List.
        project_id: Project ID. Uses the default project if not specified.
    """
    client = _get_client()
    pid = project_id or client.project_id
    entities = await _run_sync(
        client.entities.list,
        entity_list_name=entity_list_name,
        project_id=pid,
    )
    return _serialize(entities)


@mcp.tool()
async def create_entity(
    entity_list_name: str,
    label: str,
    data: Dict[str, str],
    project_id: Optional[int] = None,
) -> str:
    """Create a new entity in an Entity List.

    Args:
        entity_list_name: Name of the Entity List.
        label: Display label for the entity.
        data: Dictionary of property name → value pairs.
        project_id: Project ID. Uses the default project if not specified.
    """
    client = _get_client()
    pid = project_id or client.project_id
    entity = await _run_sync(
        client.entities.create,
        entity_list_name=entity_list_name,
        label=label,
        data=data,
        project_id=pid,
    )
    return _serialize(entity)


# ---------------------------------------------------------------------------
# TOOLS — Raw API access
# ---------------------------------------------------------------------------
@mcp.tool()
async def central_api_get(path: str) -> str:
    """Make a raw GET request to the ODK Central API.

    Useful for endpoints not covered by the other tools.
    See https://docs.getodk.org/central-api/ for available endpoints.

    Args:
        path: API path, e.g. "/v1/projects/1/forms".
    """
    client = _get_client()
    response = await _run_sync(client.get, path)
    response.raise_for_status()
    return json.dumps(response.json(), default=str, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
