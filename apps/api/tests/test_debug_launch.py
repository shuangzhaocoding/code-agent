from code_agent.debug.launch import (
    build_debugpy_argv,
    default_current_file_config,
    expand_config,
    load_launch_configs_from_text,
    parse_launch_entry,
)


def test_load_launch_json():
    text = """
    {
      "version": "0.2.0",
      "configurations": [
        {
          "name": "App",
          "type": "python",
          "request": "launch",
          "module": "uvicorn",
          "args": ["app:main", "--reload"],
          "cwd": "${workspaceFolder}/backend",
          "env": {"FOO": "1"},
          "stopOnEntry": true
        },
        {
          "name": "Node",
          "type": "node",
          "request": "launch",
          "program": "index.js"
        }
      ]
    }
    """
    configs = load_launch_configs_from_text(text)
    assert len(configs) == 1
    assert configs[0].name == "App"
    assert configs[0].module == "uvicorn"
    assert configs[0].stop_on_entry is True


def test_expand_current_file():
    cfg = default_current_file_config("backend/main.py")
    expanded = expand_config(cfg, workspace_root="/tmp/ws", current_file="backend/main.py")
    assert expanded.program == "backend/main.py"
    assert expanded.cwd == "backend"
    argv = build_debugpy_argv(expanded, listen_host="127.0.0.1", listen_port=5678)
    assert "debugpy" in argv
    assert "--wait-for-client" in argv
    assert "backend/main.py" in argv


def test_parse_condition_fields():
    cfg = parse_launch_entry(
        {
            "name": "X",
            "type": "python",
            "program": "${file}",
            "python": "${workspaceFolder}/.venv/bin/python",
        }
    )
    expanded = expand_config(cfg, workspace_root="/proj", current_file="a.py")
    assert expanded.python.endswith(".venv/bin/python")
    assert expanded.program == "a.py" or expanded.program.endswith("a.py")
