import json
import os
import sys
from unittest.mock import MagicMock

import click
import psutil
import pytest

from lightning_app import _PROJECT_ROOT
from lightning_app.cli.commands.connection import (
    _list_app_commands,
    _resolve_command_path,
    _retrieve_connection_to_an_app,
    connect,
    disconnect,
)
from lightning_app.utilities import cli_helpers
from lightning_app.utilities.commands import base


def monkeypatch_connection(monkeypatch, tmpdir, ppid):
    connection_path = os.path.join(tmpdir, ppid)
    try:
        monkeypatch.setattr("lightning_app.cli.commands.connection._clean_lightning_connection", MagicMock())
        monkeypatch.setattr("lightning_app.cli.commands.connection._PPID", ppid)
        monkeypatch.setattr("lightning_app.cli.commands.connection._LIGHTNING_CONNECTION", tmpdir)
        monkeypatch.setattr("lightning_app.cli.commands.connection._LIGHTNING_CONNECTION_FOLDER", connection_path)
    except ModuleNotFoundError:
        monkeypatch.setattr("lightning.app.cli.commands.connection._clean_lightning_connection", MagicMock())
        monkeypatch.setattr("lightning_app.cli.commands.connection._PPID", ppid)
        monkeypatch.setattr("lightning.app.cli.commands.connection._LIGHTNING_CONNECTION", tmpdir)
        monkeypatch.setattr("lightning.app.cli.commands.connection._LIGHTNING_CONNECTION_FOLDER", connection_path)
    return connection_path


def test_connect_disconnect_local(tmpdir, monkeypatch):
    disconnect()

    ppid = str(psutil.Process(os.getpid()).ppid())
    connection_path = monkeypatch_connection(monkeypatch, tmpdir, ppid=ppid)

    with pytest.raises(Exception, match="The commands weren't found. Is your app localhost running ?"):
        connect("localhost", True)

    with open(os.path.join(os.path.dirname(__file__), "jsons/connect_1.json")) as f:
        data = json.load(f)

    data["paths"]["/command/command_with_client"]["post"]["cls_path"] = os.path.join(
        _PROJECT_ROOT,
        data["paths"]["/command/command_with_client"]["post"]["cls_path"],
    )

    messages = []

    disconnect()

    def fn(msg):
        messages.append(msg)

    monkeypatch.setattr(click, "echo", fn)

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = data
    monkeypatch.setattr(cli_helpers.requests, "get", MagicMock(return_value=response))
    connect("localhost", True)
    assert _retrieve_connection_to_an_app() == ("localhost", None)
    command_path = _resolve_command_path("nested_command")
    assert not os.path.exists(command_path)
    command_path = _resolve_command_path("command_with_client")
    assert os.path.exists(command_path)
    s = "/" if sys.platform != "win32" else "\\"
    command_folder_path = f"{connection_path}{s}commands"
    expected = [
        f"Storing `command with client` at {command_folder_path}{s}command_with_client.py",
        f"You can review all the downloaded commands at {command_folder_path}",
        "You are connected to the local Lightning App.",
    ]
    assert messages == expected

    messages = []
    connect("localhost", True)
    assert messages == ["You are connected to the local Lightning App."]

    messages = []
    disconnect()
    assert messages == ["You are disconnected from the local Lightning App."]
    messages = []
    disconnect()
    assert messages == [
        "You aren't connected to any Lightning App. Please use `lightning connect app_name_or_id` to connect to one."
    ]

    assert _retrieve_connection_to_an_app() == (None, None)


def test_connect_disconnect_cloud(tmpdir, monkeypatch):
    disconnect()

    ppid_1 = str(psutil.Process(os.getpid()).ppid())
    ppid_2 = "222"

    connection_path = monkeypatch_connection(monkeypatch, tmpdir, ppid=ppid_1)

    target_file = _resolve_command_path("command_with_client")

    if os.path.exists(target_file):
        os.remove(target_file)

    with open(os.path.join(os.path.dirname(__file__), "jsons/connect_1.json")) as f:
        data = json.load(f)

    data["paths"]["/command/command_with_client"]["post"]["cls_path"] = os.path.join(
        _PROJECT_ROOT,
        data["paths"]["/command/command_with_client"]["post"]["cls_path"],
    )

    messages = []

    def fn(msg):
        messages.append(msg)

    monkeypatch.setattr(click, "echo", fn)

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = data
    monkeypatch.setattr(cli_helpers.requests, "get", MagicMock(return_value=response))
    project = MagicMock()
    project.project_id = "custom_project_name"
    monkeypatch.setattr(cli_helpers, "_get_project", MagicMock(return_value=project))
    client = MagicMock()
    lightningapps = MagicMock()

    app = MagicMock()
    app.name = "example"
    app.id = "1234"

    lightningapps.lightningapps = [app]
    client.lightningapp_instance_service_list_lightningapp_instances.return_value = lightningapps
    monkeypatch.setattr(cli_helpers, "LightningClient", MagicMock(return_value=client))

    monkeypatch.setattr(base, "_get_project", MagicMock(return_value=project))

    artifact = MagicMock()
    artifact.filename = "commands/command_with_client.py"
    artifacts = MagicMock()
    artifacts.artifacts = [artifact]
    client.lightningapp_instance_service_list_lightningapp_instance_artifacts.return_value = artifacts
    monkeypatch.setattr(base, "LightningClient", MagicMock(return_value=client))

    with open(data["paths"]["/command/command_with_client"]["post"]["cls_path"], "rb") as f:
        response.content = f.read()

    connect("example", True)
    assert _retrieve_connection_to_an_app() == ("example", "1234")
    commands = _list_app_commands()
    assert commands == ["command with client", "command without client", "nested command"]
    command_path = _resolve_command_path("nested_command")
    assert not os.path.exists(command_path)
    command_path = _resolve_command_path("command_with_client")
    assert os.path.exists(command_path)
    s = "/" if sys.platform != "win32" else "\\"
    command_folder_path = f"{connection_path}{s}commands"
    expected = [
        f"Storing `command with client` at {command_folder_path}{s}command_with_client.py",
        f"You can review all the downloaded commands at {command_folder_path}",
        " ",
        "The client interface has been successfully installed. ",
        "You can now run the following commands:",
        "    lightning command without client",
        "    lightning command with client",
        "    lightning nested command",
        " ",
        "You are connected to the cloud Lightning App: example.",
        "Usage: lightning [OPTIONS] COMMAND [ARGS]...",
        "",
        "  --help     Show this message and exit.",
        "",
        "Lightning App Commands",
        "  command with client    A command with a client.",
        "  command without client A command without a client.",
        "  nested command         A nested command.",
    ]
    assert messages == expected

    messages = []
    connect("example", True)
    assert messages == ["You are already connected to the cloud Lightning App: example."]

    _ = monkeypatch_connection(monkeypatch, tmpdir, ppid=ppid_2)

    messages = []
    connect("example", True)
    assert messages[0] == "Found existing connection, reusing cached commands"

    messages = []
    disconnect()
    print(messages)
    assert messages == ["You are disconnected from the cloud Lightning App: example."]

    _ = monkeypatch_connection(monkeypatch, tmpdir, ppid=ppid_1)

    messages = []
    disconnect()
    assert messages == ["You are disconnected from the cloud Lightning App: example."]

    messages = []
    disconnect()
    assert messages == [
        "You aren't connected to any Lightning App. Please use `lightning connect app_name_or_id` to connect to one."
    ]

    assert _retrieve_connection_to_an_app() == (None, None)
