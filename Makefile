.PHONY: claude claudecontinue test fix format pyright all-check run install_globally

## Start Claude Code with MCP configuration
claude:
	@test -f .mcp.json || (echo "Error: .mcp.json not found. Please create it first." && exit 1)
	PATH="$(HOME)/.bun/bin:$(PATH)" CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 TELEGRAM_STATE_DIR=$(PWD)/.claude/channels/telegram claude --dangerously-skip-permissions --mcp-config .mcp.json --chrome --channels plugin:telegram@claude-plugins-official

## Continue previous Claude Code session
claudecontinue:
	@test -f .mcp.json || (echo "Error: .mcp.json not found. Please create it first." && exit 1)
	PATH="$(HOME)/.bun/bin:$(PATH)" CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 TELEGRAM_STATE_DIR=$(PWD)/.claude/channels/telegram claude --dangerously-skip-permissions --mcp-config .mcp.json --continue --chrome --channels plugin:telegram@claude-plugins-official

test:
	uv run pytest tests -v --tb=short

format:
	uv run ruff format src tests skills

fix:
	uv run ruff check --fix src tests skills
	uv run ruff format src tests skills

pyright:
	uv run pyright src tests skills

all-check:
	uv run ruff check src tests skills
	uv run ruff format --check src tests skills
	uv run pyright src tests skills
	uv run pytest tests -v --tb=short

run:
	uv run eval-banana run

install_globally:
	uv tool install --editable "$(CURDIR)"
