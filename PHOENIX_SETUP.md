# Phoenix Tracing Setup Guide

This guide explains how to set up and use Arize Phoenix for tracing and observing your CheqMate agent's LLM calls and execution.

## What is Phoenix?

Phoenix is an open-source AI observability platform that provides:
- **LLM Call Tracing**: See all prompts, responses, token usage, and latency
- **Agent Execution Flow**: Visualize agent iterations and tool executions
- **Performance Monitoring**: Track API costs, response times, and error rates
- **Debugging**: Deep dive into specific traces to debug issues

## Quick Start

### 1. Install Dependencies

The Phoenix dependencies are already in `pyproject.toml`. Install them with:

```bash
uv sync
```

This installs:
- `arize-phoenix-otel` - Phoenix OpenTelemetry integration
- `openinference-instrumentation-anthropic` - Auto-instrumentation for Anthropic API
- `opentelemetry-sdk` and `opentelemetry-exporter-otlp` - Core OpenTelemetry libraries

### 2. Start Phoenix Server

Using Docker Compose (recommended):

```bash
docker compose up -d phoenix
```

This starts Phoenix with:
- **UI**: http://localhost:6006
- **gRPC Collector**: http://localhost:4317 (for traces)
- **HTTP Collector**: http://localhost:6006/v1/traces (alternative)
- **Persistent Storage**: SQLite database in Docker volume `phoenix_data`

Check Phoenix is running:
```bash
docker compose ps phoenix
curl http://localhost:6006/healthz
```

### 3. Configure Environment

Phoenix is enabled by default. To customize, update your `.env` file:

```bash
# Phoenix Tracing (Observability)
PHOENIX_ENABLED=True
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:4317
```

To disable tracing (e.g., for testing):
```bash
PHOENIX_ENABLED=False
```

### 4. Run Your Bot

```bash
uv run python main.py
```

You should see in the logs:
```
INFO - Initializing Phoenix tracing with endpoint: http://localhost:4317
INFO - Phoenix tracer provider configured successfully
INFO - Anthropic SDK auto-instrumentation enabled
INFO - Phoenix tracing initialized successfully. View traces at http://localhost:6006
```

### 5. View Traces

Open http://localhost:6006 in your browser to see:
- Real-time traces as the agent runs
- Full conversation history with prompts and responses
- Token usage and costs per API call
- Timing information for performance analysis
- Error traces with full context

## What Gets Traced?

Phoenix automatically traces all Anthropic API calls in your application:

### 1. Agent Orchestrator (src/agent/orchestrator.py)
- Agent loop iterations (line 107)
- System prompts and user messages
- Tool use decisions
- Response generation

### 2. Receipt OCR (src/services/anthropic_service.py)
- Vision API calls with receipt images (line 198)
- Structured JSON extraction
- OCR parsing logic

### 3. Bill Splitting (src/services/anthropic_service.py)
- Initial split creation (line 360)
- Split refinement (line 551)
- Verification logic

### 4. LLM Processing Tools (src/tools/llm_processing.py)
- `extract_receipt_ocr` - Receipt image analysis
- `create_initial_bill_split` - Participant assignment
- `refine_split_with_llm` - Error correction

## Advanced Usage

### Custom Spans for Agent Iterations

You can add custom spans to trace specific operations:

```python
from src.observability.phoenix import get_tracer

tracer = get_tracer()

# Trace a custom operation
with tracer.start_as_current_span("agent_iteration") as span:
    span.set_attribute("iteration_number", iteration)
    span.set_attribute("tool_count", len(tool_use_blocks))
    # Your code here
```

### Tracing Tool Executions

Add instrumentation to `_execute_single_tool` in orchestrator.py:

```python
from src.observability.phoenix import get_tracer

tracer = get_tracer()

async def _execute_single_tool(self, tool_block, tool_context):
    with tracer.start_as_current_span(f"tool.{tool_block.name}") as span:
        span.set_attribute("tool.name", tool_block.name)
        span.set_attribute("tool.input", json.dumps(tool_block.input))

        result = await self._execute_tool_once(...)

        span.set_attribute("tool.result_size", len(str(result)))
        return result
```

## Troubleshooting

### Phoenix UI Not Loading

Check if Phoenix container is running:
```bash
docker compose ps phoenix
docker compose logs phoenix
```

Restart Phoenix:
```bash
docker compose restart phoenix
```

### No Traces Appearing

1. **Check Phoenix is enabled**:
   ```bash
   grep PHOENIX_ENABLED .env
   # Should show: PHOENIX_ENABLED=True
   ```

2. **Check endpoint is correct**:
   ```bash
   grep PHOENIX_COLLECTOR_ENDPOINT .env
   # Should show: PHOENIX_COLLECTOR_ENDPOINT=http://localhost:4317
   ```

3. **Check bot logs for errors**:
   ```bash
   uv run python main.py 2>&1 | grep -i phoenix
   ```

4. **Verify network connectivity**:
   ```bash
   # From inside your app container/process
   curl -v http://localhost:4317
   ```

### Traces Not Flushing

Ensure proper shutdown:
- The app calls `shutdown_phoenix()` on exit (already configured in main.py)
- Wait a few seconds after stopping the bot for traces to flush

### High Memory Usage

Phoenix batches spans for performance. If memory is a concern, you can:
1. Reduce batch size in `phoenix.py` (modify `BatchSpanProcessor` settings)
2. Use HTTP exporter instead of gRPC (change endpoint to `http://localhost:6006/v1/traces`)
3. Disable tracing in production: `PHOENIX_ENABLED=False`

## Performance Impact

Phoenix tracing adds minimal overhead:
- **Agent calls**: ~2-5ms per trace
- **Network**: Async batching prevents blocking
- **Memory**: ~10-20MB for typical sessions

For production with high traffic, consider:
- Using a dedicated Phoenix instance
- Sampling traces (trace 10% of requests)
- Disabling detailed spans for non-critical paths

## Docker Compose Reference

### Start Phoenix
```bash
docker compose up -d phoenix
```

### View Logs
```bash
docker compose logs -f phoenix
```

### Stop Phoenix
```bash
docker compose stop phoenix
```

### Remove Phoenix (including data)
```bash
docker compose down phoenix
docker volume rm cheqmate_phoenix_data
```

### Backup Traces
```bash
# Copy SQLite database from container
docker compose cp phoenix:/mnt/data/phoenix.db ./phoenix_backup.db
```

## Production Deployment

For production environments:

### 1. Use External Postgres

Update `docker-compose.yml` to use PostgreSQL:

```yaml
services:
  phoenix:
    image: arizephoenix/phoenix:latest
    environment:
      - PHOENIX_SQL_DATABASE_URL=postgresql://user:pass@postgres:5432/phoenix
    depends_on:
      - postgres

  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=phoenix
      - POSTGRES_PASSWORD=your_secure_password
      - POSTGRES_DB=phoenix
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

### 2. Enable Authentication

Phoenix supports OAuth and basic auth. See [Phoenix docs](https://docs.arize.com/phoenix/) for details.

### 3. Scale Phoenix

For high-volume tracing:
- Use dedicated Phoenix instance
- Configure multiple collectors with load balancing
- Enable trace sampling

## Learn More

- [Phoenix Documentation](https://docs.arize.com/phoenix/)
- [OpenInference Specification](https://github.com/Arize-ai/openinference)
- [OpenTelemetry Python](https://opentelemetry.io/docs/instrumentation/python/)

## Example Phoenix UI Screenshots

When you open http://localhost:6006, you'll see:

1. **Traces List**: All agent runs with timing and status
2. **Trace Details**: Full conversation flow with prompts and responses
3. **Spans Timeline**: Waterfall chart showing API call timing
4. **Token Usage**: Cost breakdown per API call
5. **Error Traces**: Failed requests with full error context

Try it out by running a bill split through your bot and watching the traces appear in real-time!
