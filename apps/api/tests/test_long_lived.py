from code_agent.tools.long_lived import is_long_lived_command, normalize_terminal_command


def test_detects_common_dev_servers():
    assert is_long_lived_command("npm run dev")
    assert is_long_lived_command("pnpm run start")
    assert is_long_lived_command("yarn dev")
    assert is_long_lived_command("bun run serve")
    assert is_long_lived_command("npx vite")
    assert is_long_lived_command("next dev")
    assert is_long_lived_command("uvicorn app:main --reload")
    assert is_long_lived_command("python -m http.server 8080")
    assert is_long_lived_command("nohup npm run dev &")
    assert is_long_lived_command("docker compose up")
    assert is_long_lived_command("cd backend && npm run dev")
    assert is_long_lived_command("cd apps/web && pnpm start")
    assert is_long_lived_command("cd api; uvicorn app:main --reload")
    assert not is_long_lived_command("docker compose up -d")
    assert not is_long_lived_command("npm install")
    assert not is_long_lived_command("cd backend && npm install")
    assert not is_long_lived_command("pytest")
    assert not is_long_lived_command("echo hello")


def test_normalize_strips_background_wrappers():
    assert normalize_terminal_command("nohup npm run dev &") == "npm run dev"
    assert normalize_terminal_command("vite > /dev/null 2>&1") == "vite"
    assert normalize_terminal_command("  npm run start  ") == "npm run start"
    assert normalize_terminal_command("cd backend && npm run dev") == "cd backend && npm run dev"
