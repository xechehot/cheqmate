# Phoenix Tracing Integration - Quick Start

## What's Been Set Up

Phoenix tracing is now fully integrated into CheqMate to provide visibility into your agent's LLM calls and execution flow.

### Files Created/Modified

1. **docker-compose.yml** - Phoenix server configuration
2. **src/observability/phoenix.py** - Phoenix instrumentation module
3. **src/config/settings.py** - Added Phoenix configuration settings
4. **main.py** - Initialized Phoenix tracing at startup
5. **.env.example** - Added Phoenix environment variables
6. **pyproject.toml** - Added Phoenix dependencies

### Dependencies Installed

```
arize-phoenix-otel==0.13.1
openinference-instrumentation-anthropic==0.1.20
opentelemetry-sdk==1.37.0
opentelemetry-exporter-otlp==1.37.0
+ supporting OpenTelemetry libraries
```

## Quick Start (3 Steps)

### 1. Update Your .env File

Add these lines to your `.env`:

```bash
# Phoenix Tracing
PHOENIX_ENABLED=True
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:4317
```

### 2. Start Phoenix

```bash
docker compose up -d phoenix
```

Verify it's running:
```bash
docker compose ps phoenix
# Should show: Up X seconds (healthy)
```

### 3. Run Your Bot

```bash
uv run python main.py
```

Look for these logs:
```
INFO - Initializing Phoenix tracing with endpoint: http://localhost:4317
INFO - Anthropic SDK auto-instrumentation enabled
INFO - Phoenix tracing initialized successfully. View traces at http://localhost:6006
```

## View Traces

Open http://localhost:6006 in your browser.

Send a message to your Telegram bot and watch traces appear in real-time!

## What You'll See

Phoenix automatically traces:

- **Agent orchestrator** (src/agent/orchestrator.py:107)
  - Agent loop iterations
  - Tool selection decisions
  - System prompts and user messages

- **Receipt OCR** (src/services/anthropic_service.py:198)
  - Vision API calls with images
  - Structured JSON extraction

- **Bill splitting** (src/services/anthropic_service.py:360, 551)
  - Initial split creation
  - Split refinement and verification

For each trace you'll see:
- Full prompts sent to Claude
- Complete responses
- Token usage (input/output)
- Latency (per API call)
- Cost estimates
- Error traces with context

## Detailed Documentation

For more information:
- **PHOENIX_SETUP.md** - Complete setup guide with troubleshooting
- **USAGE_EXAMPLE.md** - Step-by-step usage examples and advanced features

## Stopping Phoenix

```bash
docker compose stop phoenix
```

To remove Phoenix and its data:
```bash
docker compose down phoenix
docker volume rm cheqmate_phoenix_data
```

## Disabling Tracing

To disable tracing (e.g., for testing):

```bash
# In .env
PHOENIX_ENABLED=False
```

The app will start normally but won't send traces to Phoenix.

## Troubleshooting

### Phoenix UI Not Loading

```bash
# Check container status
docker compose ps phoenix

# Check logs
docker compose logs phoenix

# Restart Phoenix
docker compose restart phoenix
```

### No Traces Appearing

1. Verify Phoenix is enabled: `grep PHOENIX_ENABLED .env`
2. Check endpoint: `grep PHOENIX_COLLECTOR_ENDPOINT .env`
3. Look for errors: `uv run python main.py 2>&1 | grep -i phoenix`

### Port Already in Use

If port 6006 is already in use, modify `docker-compose.yml`:

```yaml
ports:
  - "6007:6006"  # Changed from 6006:6006
```

Then access Phoenix at http://localhost:6007

## Next Steps

1. Test the integration by sending a message to your bot
2. Explore the Phoenix UI to understand trace structure
3. Read USAGE_EXAMPLE.md for advanced features
4. Consider adding custom spans for specific operations

Enjoy your new observability superpowers! 🔍✨
