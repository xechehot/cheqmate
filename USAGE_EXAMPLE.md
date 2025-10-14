# Phoenix Usage Example

## Step-by-Step: Start Tracing Your Agent

### 1. Start Phoenix

```bash
# Start Phoenix in background
docker compose up -d phoenix

# Check it's running
docker compose ps phoenix
```

Expected output:
```
NAME                IMAGE                           STATUS
cheqmate-phoenix    arizephoenix/phoenix:latest     Up 5 seconds (healthy)
```

### 2. Open Phoenix UI

Open your browser to http://localhost:6006

You should see the Phoenix dashboard with "No traces yet" message.

### 3. Start Your Bot

```bash
# Make sure your .env has Phoenix enabled
echo "PHOENIX_ENABLED=True" >> .env

# Start the bot
uv run python main.py
```

You should see these logs:
```
INFO - Initializing Phoenix tracing with endpoint: http://localhost:4317
INFO - Phoenix tracer provider configured successfully
INFO - Anthropic SDK auto-instrumentation enabled
INFO - Phoenix tracing initialized successfully. View traces at http://localhost:6006
INFO - Starting CheqMate bot application
```

### 4. Send a Test Message

In Telegram:
1. Start your bot with `/start`
2. Send `/new_bill`
3. Upload a receipt photo
4. Provide participant description

### 5. View Traces in Phoenix

Go back to http://localhost:6006 and you'll see:

#### Traces List View
```
┌─────────────────────────────────────────────────────────────┐
│ Trace ID          │ Start Time │ Duration │ Status │ Tokens  │
├─────────────────────────────────────────────────────────────┤
│ agent_orchestrator│ 14:32:15   │ 3.2s     │ OK     │ 2,341   │
│ extract_receipt   │ 14:32:16   │ 1.8s     │ OK     │ 1,523   │
│ create_split      │ 14:32:18   │ 1.1s     │ OK     │ 892     │
└─────────────────────────────────────────────────────────────┘
```

#### Click on a Trace to See Details

**Agent Orchestrator Trace:**
```
├─ Agent Loop (3.2s)
│  ├─ Anthropic API Call #1 (0.8s)
│  │  ├─ Model: claude-sonnet-4-20250514
│  │  ├─ Prompt Tokens: 1,234
│  │  ├─ Response Tokens: 156
│  │  ├─ System Prompt: "You are a bill splitting agent..."
│  │  ├─ User Message: "User uploaded receipt: <image>"
│  │  ├─ Response: Tool use: extract_receipt_ocr
│  │  └─ Cost: $0.0123
│  │
│  ├─ Tool Execution: extract_receipt_ocr (1.8s)
│  │  └─ Result: ReceiptData with 8 items
│  │
│  ├─ Anthropic API Call #2 (0.6s)
│  │  ├─ User Message: Tool result: {"items": [...]}
│  │  ├─ Response: Tool use: create_initial_bill_split
│  │  └─ Cost: $0.0089
│  │
│  └─ Tool Execution: create_initial_bill_split (1.1s)
│     └─ Result: BillSplit with 3 participants
└─ Total Cost: $0.0347
```

**Receipt OCR Trace:**
```
├─ extract_receipt_ocr (1.8s)
│  ├─ Vision API Call (1.8s)
│  │  ├─ Model: claude-sonnet-4-20250514
│  │  ├─ Input: Image (245 KB) + Text prompt
│  │  ├─ System Prompt: "Analyze this receipt..."
│  │  ├─ Prompt Tokens: 1,523
│  │  ├─ Response Tokens: 234
│  │  ├─ Response: JSON with currency, items, totals
│  │  └─ Cost: $0.0156
│  │
│  └─ Parsed Result:
│     {
│       "currency": "USD",
│       "items": [
│         {"name": "Pizza", "price": 12.50, "quantity": 2},
│         {"name": "Salad", "price": 8.00, "quantity": 1}
│       ],
│       "total": 33.00
│     }
```

### 6. Analyze Performance

Phoenix automatically tracks:

**Token Usage by Operation:**
```
┌────────────────────────────────────────────────────────┐
│ Operation          │ Calls │ Avg Tokens │ Total Cost  │
├────────────────────────────────────────────────────────┤
│ agent_orchestrator │   12  │   2,341    │ $0.45       │
│ extract_receipt    │   12  │   1,523    │ $0.28       │
│ create_split       │   12  │     892    │ $0.16       │
│ refine_split       │    3  │   1,234    │ $0.07       │
└────────────────────────────────────────────────────────┘
Total: $0.96 over 39 API calls
```

**Latency Distribution:**
```
P50: 0.8s
P95: 2.1s
P99: 3.4s
Max: 5.2s
```

**Error Rate:**
```
Success: 36/39 (92.3%)
Errors:  3/39 (7.7%)
  - Rate limit: 2
  - Timeout: 1
```

### 7. Debug an Error

Click on a failed trace to see:

```
❌ Error in extract_receipt_ocr
├─ Error Type: APIError
├─ Status Code: 400
├─ Message: "Invalid image format"
├─ Full Context:
│  ├─ Image Size: 12.3 MB (exceeds 5 MB limit)
│  ├─ Image Type: image/jpeg
│  ├─ Timestamp: 2025-10-15 14:32:16
│  └─ Chat ID: 123456789
└─ Stack Trace: [...]
```

This helps you quickly identify and fix issues!

### 8. Compare Prompts

Phoenix lets you compare different prompt versions:

```
Version A (baseline):
"Analyze this receipt and extract items"
→ Success rate: 87%, Avg tokens: 1,523

Version B (improved):
"Analyze this receipt image and extract all items with their prices and currency..."
→ Success rate: 95%, Avg tokens: 1,489

🎯 Version B: +8% success rate, -2% tokens
```

## Advanced Features

### Custom Spans for Agent Iterations

Add this to `src/agent/orchestrator.py`:

```python
from src.observability.phoenix import get_tracer

class AgentOrchestrator:
    def __init__(self):
        # ... existing code ...
        self.tracer = get_tracer("cheqmate.agent")

    async def run(self, agent_context, new_message=None):
        # Wrap the entire agent run in a span
        with self.tracer.start_as_current_span("agent_run") as span:
            span.set_attribute("chat_id", agent_context.chat_id)
            span.set_attribute("turn_number", agent_context.session.turn_number)

            # ... existing loop code ...

            # Track iteration count
            span.set_attribute("iterations", iteration)
            span.set_attribute("success", iteration < MAX_ITERATIONS)
```

Now you'll see structured agent runs in Phoenix:

```
├─ agent_run (chat_id=123456, turn=5, iterations=3) [3.2s]
│  ├─ iteration_1 [0.9s]
│  │  ├─ API call
│  │  └─ Tool: extract_receipt_ocr
│  ├─ iteration_2 [1.2s]
│  │  ├─ API call
│  │  └─ Tool: create_split
│  └─ iteration_3 [1.1s]
│     ├─ API call
│     └─ Tool: send_formatted_split
```

### Track Tool Performance

Add spans for individual tools:

```python
async def _execute_single_tool(self, tool_block, tool_context):
    with self.tracer.start_as_current_span(f"tool.{tool_block.name}") as span:
        span.set_attribute("tool.name", tool_block.name)
        span.set_attribute("tool.input_size", len(str(tool_block.input)))

        result = await self._execute_tool_once(...)

        span.set_attribute("tool.result_size", len(str(result)))
        span.set_attribute("tool.success", True)
        return result
```

View tool execution times in Phoenix:

```
Tool Performance:
┌────────────────────────────────────────────────────────┐
│ Tool                      │ Calls │ P50   │ P95   │ P99  │
├────────────────────────────────────────────────────────┤
│ extract_receipt_ocr       │  12   │ 1.8s  │ 2.4s  │ 3.1s │
│ download_telegram_photo   │  12   │ 0.3s  │ 0.6s  │ 1.2s │
│ create_initial_bill_split │  12   │ 1.1s  │ 1.5s  │ 2.0s │
│ send_formatted_split      │  11   │ 0.2s  │ 0.3s  │ 0.5s │
│ refine_split_with_llm     │   3   │ 1.3s  │ 1.9s  │ 2.1s │
└────────────────────────────────────────────────────────┘
```

## Real-World Example

Here's what a complete bill split looks like in Phoenix:

```
📊 Trace: Bill Split Session (chat_123456, turn_5)
Duration: 8.7s | Cost: $0.034 | Status: ✓ Success

Timeline:
00:00 │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│ 8.7s
      │ │
      │ ├─ [Agent Iteration 1] (0.9s)
      │ │  └─ Request receipt photo (Telegram API: 0.2s)
      │ │
      │ ├─ [User uploads photo] (2.1s user delay)
      │ │
      │ ├─ [Agent Iteration 2] (3.8s)
      │ │  ├─ Download photo (0.4s)
      │ │  ├─ OCR extraction (1.9s) 💰 $0.015
      │ │  │  └─ Vision API: 1,523 tokens
      │ │  └─ Ask for participant description (0.3s)
      │ │
      │ ├─ [User provides description] (1.2s user delay)
      │ │
      │ └─ [Agent Iteration 3] (2.7s)
      │    ├─ Create initial split (1.2s) 💰 $0.009
      │    │  └─ Claude API: 892 tokens
      │    ├─ Calculate totals (0.1s)
      │    ├─ Check accuracy (0.05s)
      │    ├─ Refine split (1.3s) 💰 $0.010
      │    │  └─ Claude API: 1,234 tokens
      │    └─ Send formatted split (0.2s)
      │
      └─ Total: 3 iterations, 39 spans, $0.034

Prompts Used:
1. System Prompt (2,341 chars):
   "You are a bill splitting agent that helps users split restaurant bills..."

2. User Message (iteration 1):
   "New bill split requested"

3. User Message (iteration 2):
   "Tool result: downloaded image (245 KB)"

4. User Message (iteration 3):
   "Tool result: OCR extracted 8 items - Pizza $25.00, Salad $8.00..."

API Calls:
• Anthropic Claude (Iteration 2): 1,523 tokens, 1.9s, $0.015
• Anthropic Claude (Iteration 3.1): 892 tokens, 1.2s, $0.009
• Anthropic Claude (Iteration 3.2): 1,234 tokens, 1.3s, $0.010

Tools Executed:
✓ request_receipt_photo → Success
✓ download_telegram_photo → 245 KB
✓ extract_receipt_ocr → 8 items
✓ request_participant_description → Success
✓ create_initial_bill_split → 3 participants
✓ calculate_total_discrepancy → 0.05 difference
✓ refine_split_with_llm → Updated split
✓ send_formatted_split → Sent to user
```

This level of visibility makes debugging and optimization much easier!

## Next Steps

- Explore the Phoenix UI to understand your agent's behavior
- Add custom spans for domain-specific operations
- Set up alerts for high latency or error rates
- Export traces for analysis in notebooks
- Compare different prompt versions

Happy tracing! 🔍
