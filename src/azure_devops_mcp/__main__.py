"""Entry point for `python -m azure_devops_mcp` and the `azure-devops-mcp` CLI command."""

import os
import sys


def main():
    args = sys.argv[1:]

    # Subcommand: azure-devops-mcp auth login|status
    if len(args) >= 1 and args[0] == "auth":
        from azure_devops_mcp.auth import login, status

        if len(args) >= 2 and args[1] == "login":
            login()
        elif len(args) >= 2 and args[1] == "status":
            status()
        else:
            print("Usage: azure-devops-mcp auth <login|status>")
            print()
            print("Commands:")
            print("  login   Log in via device code flow (interactive)")
            print("  status  Show current auth method and token validity")
            sys.exit(1)
        return

    # Default: run the MCP server
    # Validate required config before starting
    from dotenv import load_dotenv

    load_dotenv()

    if not os.getenv("AZURE_DEVOPS_ORG_URL"):
        print(
            "Error: AZURE_DEVOPS_ORG_URL is not set.\n"
            "\n"
            "Quick start:\n"
            "  1. export AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org\n"
            "  2. azure-devops-mcp auth login\n"
            "  3. Add the server to your AI editor\n"
            "\n"
            "Or set it in your .env file or MCP client config.",
            file=sys.stderr,
        )
        sys.exit(1)

    from azure_devops_mcp.server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
