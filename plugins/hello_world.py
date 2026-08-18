PLUGIN_TITLE = "Hello tool"
PLUGIN_DESCRIPTION = "Example plugin that registers a hello_world tool. Drop extra *.py files here to extend Code Agent."


def register(registry) -> None:
    from langchain_core.tools import tool

    @tool
    def hello_world(name: str = "developer") -> str:
        """Demo plugin tool. Returns a greeting. Safe no-op."""
        return f"Hello {name} from a Code Agent plugin."

    registry.register_tool(hello_world, source="plugin:hello_world", modes=("ask", "agent", "plan"))
