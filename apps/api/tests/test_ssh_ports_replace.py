from __future__ import annotations

from code_agent.ports.remote_scan import parse_ss_listening
from code_agent.tools.paths import path_in_scope


def test_parse_ss_listening_basic():
    stdout = """
State  Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*
LISTEN 0      511        127.0.0.1:3000       0.0.0.0:*
LISTEN 0      511            [::]:8080          [::]:*
LISTEN 0      128       192.168.1.5:5432       0.0.0.0:*
"""
    items = parse_ss_listening(stdout, exclude_ports={22})
    ports = {i["port"] for i in items}
    assert 3000 in ports
    assert 8080 in ports
    assert 22 not in ports
    # non-local bind excluded
    assert 5432 not in ports
    assert all(i["preview_path"].startswith("/api/preview/") for i in items)
    assert all(i.get("remote") is True for i in items)


def test_parse_ss_listening_dedupe_hosts():
    stdout = """
LISTEN 0 128 127.0.0.1:9000 0.0.0.0:*
LISTEN 0 128 0.0.0.0:9000 0.0.0.0:*
"""
    items = parse_ss_listening(stdout)
    assert len(items) == 1
    assert items[0]["port"] == 9000
    assert "127.0.0.1" in items[0]["address"]
    assert "0.0.0.0" in items[0]["address"]


def test_path_in_scope_include_exclude():
    assert path_in_scope("src/a.ts", ["src/**"], []) is True
    assert path_in_scope("docs/a.md", ["src/**"], []) is False
    assert path_in_scope("src/a.ts", [], ["src/**"]) is False
    assert path_in_scope("src/a.ts", ["**/*.ts"], ["**/vendor/**"]) is True
    assert path_in_scope("vendor/x.ts", ["**/*.ts"], ["vendor/**"]) is False
