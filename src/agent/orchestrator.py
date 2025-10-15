"""Agent orchestrator implementing ReAct pattern for bill splitting.

This module provides the main agent loop that:
1. Reasons about current state using Claude
2. Acts by executing selected tools
3. Observes results and decides whether to continue or terminate
"""

import asyncio
import base64
import json
import logging
import time
from decimal import Decimal
from typing import Any

from anthropic import AsyncAnthropic

from src.agent.context_builder import (
    AgentContext,
    build_system_prompt,
    build_user_prompt,
)
from src.agent.tool_registry import TOOLS
from src.config import settings
from src.models.bill import BillSplit, ReceiptData

logger = logging.getLogger(__name__)

# Configuration
MAX_ITERATIONS = 15  # Prevent infinite loops
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


class AgentOrchestrator:
    """Orchestrates the bill splitting workflow using Claude agent with tools."""

    def __init__(self):
        """Initialize the orchestrator with async Anthropic client."""
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key is required")
        # Initialize async client with 60 second timeout to prevent hanging
        # Using AsyncAnthropic enables true non-blocking I/O for concurrent request handling
        self.client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=60.0,  # 60 second timeout for API calls
        )

        # Performance monitoring metrics
        self.metrics = {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "total_iterations": 0,
            "total_duration_s": 0.0,
        }
        logger.info("Agent orchestrator initialized with 60s timeout")

    async def run(
        self,
        agent_context: AgentContext,
        new_message: str | None = None,
    ) -> None:
        """
        Run the agent loop to process a bill splitting request.

        This implements the ReAct pattern:
        - Reason: Call Claude to decide what to do
        - Act: Execute selected tools
        - Observe: Process results and continue or terminate

        Args:
            agent_context: Rich context with session state and Telegram data
            new_message: Optional new text message or description of user action
        """
        chat_id = agent_context.chat_id
        agent_start_time = time.time()
        logger.info(f"Starting agent orchestration for chat {chat_id}")

        # Increment turn counter
        agent_context.session.increment_turn()

        # Build conversation messages
        messages: list[dict[str, Any]] = []

        # Initial user message with state
        user_prompt = build_user_prompt(agent_context, new_message)
        messages.append({"role": "user", "content": user_prompt})

        # ReAct loop
        iteration = 0
        while iteration < MAX_ITERATIONS:
            iteration += 1
            iteration_start_time = time.time()
            logger.info(
                f"Agent iteration {iteration}/{MAX_ITERATIONS} for chat {chat_id}"
            )

            try:
                # 1. REASON: Call Claude with tools (async, non-blocking)
                # Log conversation size for debugging
                total_size = sum(len(str(msg)) for msg in messages)
                logger.info(
                    f"Calling Claude API: {len(messages)} messages, "
                    f"~{total_size} chars total"
                )

                # Async API call - enables concurrent request handling
                response = await self.client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=4096,
                    system=build_system_prompt(),
                    messages=messages,
                    tools=TOOLS,
                )

                logger.info(f"Claude API returned: stop_reason={response.stop_reason}")
                logger.debug(f"Claude response stop_reason: {response.stop_reason}")

                # Check for final answer (no tool use)
                if response.stop_reason == "end_turn":
                    # Agent finished - extract final text if any
                    final_text = ""
                    for block in response.content:
                        if block.type == "text":
                            final_text += block.text

                    if final_text:
                        logger.info(
                            f"Agent completed task for chat {chat_id} with message"
                        )
                        # Agent provided final message, but tools should have handled communication
                        # Log it for debugging
                        logger.debug(f"Agent final message: {final_text}")
                    else:
                        logger.info(f"Agent completed task silently for chat {chat_id}")

                    # Task complete
                    break

                # Extract tool use blocks
                tool_use_blocks = [
                    block for block in response.content if block.type == "tool_use"
                ]
                text_blocks = [
                    block for block in response.content if block.type == "text"
                ]

                # Log agent reasoning
                for block in text_blocks:
                    logger.debug(f"Agent reasoning: {block.text}")

                if not tool_use_blocks:
                    logger.warning(
                        "No tool use but not end_turn - treating as completion"
                    )
                    break

                # 2. ACT: Execute tools in parallel
                tool_results = await self._execute_tools(
                    tool_use_blocks=tool_use_blocks,
                    agent_context=agent_context,
                )

                # 3. OBSERVE: Add assistant message and tool results to conversation
                messages.append({"role": "assistant", "content": response.content})

                messages.append({"role": "user", "content": tool_results})

                # Log iteration duration
                iteration_duration = time.time() - iteration_start_time
                logger.info(
                    f"Iteration {iteration} completed in {iteration_duration:.2f}s"
                )
                if iteration_duration > 10.0:
                    logger.warning(
                        f"Slow iteration detected: {iteration_duration:.2f}s (threshold: 10s)"
                    )

            except Exception as e:
                logger.error(
                    f"Error in agent loop for chat {chat_id}: {e}", exc_info=True
                )

                # Record error in session
                agent_context.session.record_error(str(e))

                # Send error to user
                from src.tools.user_interaction import send_error_message

                await send_error_message(
                    chat_id=chat_id,
                    error=str(e),
                    context=agent_context.telegram_context,
                )

                # Reset session
                agent_context.session.reset()
                break

        if iteration >= MAX_ITERATIONS:
            logger.error(
                f"Agent hit max iterations ({MAX_ITERATIONS}) for chat {chat_id}"
            )
            from src.tools.user_interaction import send_error_message

            await send_error_message(
                chat_id=chat_id,
                error="Processing took too many steps. Please try again with /new_bill",
                context=agent_context.telegram_context,
            )
            agent_context.session.reset()

        # Log total agent run duration
        total_duration = time.time() - agent_start_time

        # Update performance metrics
        self.metrics["total_runs"] += 1
        self.metrics["total_iterations"] += iteration
        self.metrics["total_duration_s"] += total_duration

        # Determine if run was successful (completed normally, not hit max iterations or error)
        if iteration < MAX_ITERATIONS:
            self.metrics["successful_runs"] += 1
            success_status = "SUCCESS"
        else:
            self.metrics["failed_runs"] += 1
            success_status = "FAILED"

        # Calculate running averages
        avg_iterations = self.metrics["total_iterations"] / self.metrics["total_runs"]
        avg_duration = self.metrics["total_duration_s"] / self.metrics["total_runs"]
        success_rate = (
            self.metrics["successful_runs"] / self.metrics["total_runs"]
        ) * 100

        logger.info(
            f"Agent orchestration completed for chat {chat_id}: {success_status} "
            f"in {total_duration:.2f}s ({iteration} iterations)"
        )
        logger.info(
            f"Performance metrics: success_rate={success_rate:.1f}%, "
            f"avg_iterations={avg_iterations:.1f}, avg_duration={avg_duration:.1f}s "
            f"(total_runs={self.metrics['total_runs']})"
        )

        # Alert on performance degradation
        if success_rate < 50 and self.metrics["total_runs"] >= 5:
            logger.warning(
                f"⚠️  Low success rate detected: {success_rate:.1f}% over {self.metrics['total_runs']} runs"
            )
        if avg_duration > 30 and self.metrics["total_runs"] >= 5:
            logger.warning(
                f"⚠️  Slow execution detected: avg {avg_duration:.1f}s over {self.metrics['total_runs']} runs"
            )

    async def _execute_tools(
        self,
        tool_use_blocks: list[Any],
        agent_context: AgentContext,
    ) -> list[dict[str, Any]]:
        """
        Execute tool calls from Claude's response in parallel.

        Args:
            tool_use_blocks: Tool use content blocks from Claude
            agent_context: Agent context with session and Telegram data

        Returns:
            List of tool result blocks for next message to Claude
        """
        tool_results = []

        # Prepare tool context for execution
        tool_context = agent_context.to_tool_context()

        # Execute tools in parallel
        tasks = []
        for tool_block in tool_use_blocks:
            task = self._execute_single_tool(tool_block, tool_context)
            tasks.append(task)

        # Wait for all tools to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Format results for Claude
        for tool_block, result in zip(tool_use_blocks, results):
            if isinstance(result, Exception):
                logger.error(f"Tool {tool_block.name} failed: {result}")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": f"Error: {str(result)}",
                        "is_error": True,
                    }
                )
            else:
                result_str = str(result)
                result_size = len(result_str)

                # Log result size for monitoring
                if result_size > 10000:
                    logger.debug(
                        f"Tool {tool_block.name} returned large result: {result_size} bytes "
                        f"({result_size / 1024:.1f} KB)"
                    )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result_str,
                    }
                )

        return tool_results

    async def _execute_single_tool(
        self,
        tool_block: Any,
        tool_context: dict[str, Any],
    ) -> str:
        """
        Execute a single tool call with retry logic for transient errors.

        Retries up to 3 times with exponential backoff (1s, 2s, 4s) for:
        - API errors (rate limits, timeouts, 500s)
        - Connection errors

        Args:
            tool_block: Tool use block from Claude containing name and input
            tool_context: Context data for tool execution

        Returns:
            Tool result as string

        Raises:
            ValueError: If tool is unknown or execution fails after all retries
        """
        tool_name = tool_block.name
        tool_input = tool_block.input

        tool_start_time = time.time()
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Tool input: {tool_input}")

        # Retry logic for transient errors
        max_retries = 3
        backoff = 1.0
        last_error = None

        for attempt in range(max_retries):
            try:
                return await self._execute_tool_once(
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_context=tool_context,
                    tool_start_time=tool_start_time,
                )
            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                # Check if error is retryable
                is_retryable = self._is_retryable_error(e)

                if is_retryable and attempt < max_retries - 1:
                    logger.warning(
                        f"Tool {tool_name} failed with {error_type} (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {backoff}s... Error: {str(e)[:100]}"
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                else:
                    # Not retryable or final attempt - raise error
                    if is_retryable:
                        logger.error(
                            f"Tool {tool_name} failed after {max_retries} attempts: {e}\n"
                            f"Tool input: {tool_input}\n"
                            f"Error type: {error_type}"
                        )
                    else:
                        logger.error(
                            f"Tool {tool_name} failed with non-retryable error: {e}\n"
                            f"Tool input: {tool_input}\n"
                            f"Error type: {error_type}"
                        )
                    raise

        # Should never reach here, but just in case
        raise last_error if last_error else RuntimeError("Tool execution failed")

    def _is_retryable_error(self, error: Exception) -> bool:
        """
        Determine if an error is retryable (transient).

        Retryable errors:
        - API rate limits (429)
        - Server errors (500, 503)
        - Connection/timeout errors
        - Overloaded errors

        Non-retryable errors:
        - Bad requests (400)
        - Authentication errors
        - ValueError from business logic

        Args:
            error: The exception to check

        Returns:
            True if error is retryable, False otherwise
        """
        error_str = str(error).lower()
        error_type = type(error).__name__

        # Import anthropic exceptions
        try:
            from anthropic import (
                APIError,
                APIConnectionError,
                APITimeoutError,
                RateLimitError,
            )

            # Anthropic-specific retryable errors
            if isinstance(error, (RateLimitError, APITimeoutError, APIConnectionError)):
                return True

            if isinstance(error, APIError):
                # Check status code if available
                if hasattr(error, "status_code"):
                    # Retry on 429, 500, 502, 503, 504
                    if error.status_code in [429, 500, 502, 503, 504]:
                        return True
                    # Don't retry on 400-level errors (except 429)
                    if 400 <= error.status_code < 500:
                        return False
        except ImportError:
            pass

        # Generic retryable error patterns
        retryable_patterns = [
            "timeout",
            "connection",
            "rate limit",
            "overloaded",
            "service unavailable",
            "internal server error",
            "502",
            "503",
            "504",
        ]

        for pattern in retryable_patterns:
            if pattern in error_str:
                return True

        # Specific non-retryable errors
        non_retryable_types = [
            "ValueError",
            "KeyError",
            "AttributeError",
            "TypeError",
        ]

        if error_type in non_retryable_types:
            return False

        # Default to not retrying if unsure
        return False

    def _validate_tool_input(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> str | None:
        """
        Validate that tool_input contains all required parameters from tool schema.

        Args:
            tool_name: Name of the tool to validate
            tool_input: Input parameters from Claude

        Returns:
            None if valid, error message string if validation fails
        """
        # Look up tool schema from TOOLS registry
        tool_schema = None
        for tool in TOOLS:
            if tool["name"] == tool_name:
                tool_schema = tool
                break

        if not tool_schema:
            # Tool not in registry (shouldn't happen)
            return None

        # Get required parameters from schema
        input_schema = tool_schema.get("input_schema", {})
        required_params = input_schema.get("required", [])

        # Check if all required params are present
        missing_params = []
        for param in required_params:
            if param not in tool_input:
                missing_params.append(param)

        if missing_params:
            return (
                f"Missing required parameter(s): {', '.join(missing_params)}. "
                f"Required: {', '.join(required_params)}"
            )

        return None

    async def _execute_tool_once(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_context: dict[str, Any],
        tool_start_time: float,
    ) -> str:
        """
        Execute a single tool call once (called by _execute_single_tool with retry logic).

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters from Claude
            tool_context: Context data for tool execution
            tool_start_time: Start time for logging

        Returns:
            Tool result as string

        Raises:
            ValueError: If tool is unknown
            Exception: Any error from tool execution
        """

        # Import tools dynamically
        from src.tools import (
            # User interaction
            ask_clarification_question,
            download_telegram_photo,
            extract_file_id_from_message,
            get_latest_text_message,
            request_participant_description,
            request_receipt_photo,
            send_error_message,
            send_formatted_receipt,
            send_formatted_split,
            send_message,
            send_processing_status,
            # State management
            get_participant_description,
            get_receipt_file_id,
            save_participant_description,
            save_receipt_file_id,
            # LLM processing
            create_initial_bill_split,
            extract_receipt_ocr,
            refine_split_with_llm,
            # Calculations
            calculate_all_participant_totals,
            calculate_total_discrepancy,
            check_accuracy_threshold,
            find_unassigned_items,
        )

        # Tool dispatch map
        TOOL_MAP = {
            # User interaction
            "send_message": send_message,
            "request_participant_description": request_participant_description,
            "request_receipt_photo": request_receipt_photo,
            "ask_clarification_question": ask_clarification_question,
            "send_processing_status": send_processing_status,
            "send_error_message": send_error_message,
            "send_formatted_receipt": send_formatted_receipt,
            "send_formatted_split": send_formatted_split,
            "download_telegram_photo": download_telegram_photo,
            "get_latest_text_message": get_latest_text_message,
            "extract_file_id_from_message": extract_file_id_from_message,
            # State management
            "get_participant_description": get_participant_description,
            "get_receipt_file_id": get_receipt_file_id,
            "save_participant_description": save_participant_description,
            "save_receipt_file_id": save_receipt_file_id,
            # LLM processing
            "extract_receipt_ocr": extract_receipt_ocr,
            "create_initial_bill_split": create_initial_bill_split,
            "refine_split_with_llm": refine_split_with_llm,
            # Calculations
            "calculate_all_participant_totals": calculate_all_participant_totals,
            "calculate_total_discrepancy": calculate_total_discrepancy,
            "check_accuracy_threshold": check_accuracy_threshold,
            "find_unassigned_items": find_unassigned_items,
        }

        tool_func = TOOL_MAP.get(tool_name)
        if not tool_func:
            raise ValueError(f"Unknown tool: {tool_name}")

        # Call tool with appropriate argument mapping
        result = await self._call_tool(
            tool_func=tool_func,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_context=tool_context,
        )

        # Log tool execution duration
        tool_duration = time.time() - tool_start_time
        logger.info(f"Tool {tool_name} completed in {tool_duration:.2f}s")
        if tool_duration > 5.0:
            logger.warning(
                f"Slow tool execution detected: {tool_name} took {tool_duration:.2f}s (threshold: 5s)"
            )

        return result

    async def _call_tool(
        self,
        tool_func: Any,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_context: dict[str, Any],
    ) -> str:
        """
        Call a tool function with appropriate argument mapping.

        This handles the translation between Claude's tool call parameters
        and the actual Python function signatures.

        Args:
            tool_func: The tool function to call
            tool_name: Name of the tool (for logging)
            tool_input: Input parameters from Claude
            tool_context: Context including chat_id, update, telegram_context, session

        Returns:
            Tool result formatted as string for Claude

        Raises:
            Exception: Any error from tool execution
        """
        import inspect

        # Validate tool input has all required parameters
        validation_error = self._validate_tool_input(tool_name, tool_input)
        if validation_error:
            raise ValueError(validation_error)

        chat_id = tool_context["chat_id"]
        update = tool_context["update"]
        telegram_context = tool_context["telegram_context"]

        # Determine arguments based on tool signature
        sig = inspect.signature(tool_func)
        kwargs = {}

        # Map common parameters
        if "chat_id" in sig.parameters:
            kwargs["chat_id"] = chat_id
        if "context" in sig.parameters:
            kwargs["context"] = telegram_context
        if "update" in sig.parameters:
            kwargs["update"] = update

        # Map tool-specific parameters from tool_input
        for param_name, param_value in tool_input.items():
            # Special handling for base64 encoded bytes
            if param_name == "image_bytes_base64" and isinstance(param_value, str):
                # Decode base64 to bytes
                kwargs["image_bytes"] = base64.b64decode(param_value)
            # Special handling for JSON strings
            elif param_name.endswith("_json") and isinstance(param_value, str):
                # Remove _json suffix for actual parameter name
                actual_param = param_name.replace("_json", "")
                if actual_param == "receipt_data":
                    kwargs[actual_param] = ReceiptData.model_validate_json(param_value)
                elif actual_param == "bill_split":
                    kwargs[actual_param] = BillSplit.model_validate_json(param_value)
                else:
                    # Generic JSON parsing
                    kwargs[actual_param] = json.loads(param_value)
            else:
                # Check if function parameter expects Decimal and value is numeric
                if param_name in sig.parameters:
                    param_type = sig.parameters[param_name].annotation
                    # Convert numeric types to Decimal if function expects it
                    if param_type == Decimal and isinstance(param_value, (int, float)):
                        kwargs[param_name] = Decimal(str(param_value))
                        logger.debug(
                            f"Converted {param_name} from {type(param_value).__name__} "
                            f"to Decimal: {param_value} -> {kwargs[param_name]}"
                        )
                    else:
                        kwargs[param_name] = param_value
                else:
                    kwargs[param_name] = param_value

        # Call tool (handle both sync and async)
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**kwargs)
        else:
            result = tool_func(**kwargs)

        # Format result for Claude
        if result is None:
            return "Success (no return value)"
        elif isinstance(result, (str, int, float, bool)):
            return str(result)
        elif isinstance(result, (ReceiptData, BillSplit)):
            # Return JSON for complex objects
            return result.model_dump_json()
        elif isinstance(result, bytes):
            # Don't return base64 to avoid bloating conversation history
            # Binary data should be cached in session instead
            size_kb = len(result) / 1024
            return f"Binary data received and cached ({size_kb:.1f} KB)"
        elif isinstance(result, dict):
            # Handle dict with Decimal values
            def decimal_default(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                raise TypeError

            return json.dumps(result, default=decimal_default)
        elif isinstance(result, list):
            # Format list items
            if result and isinstance(result[0], (ReceiptData, BillSplit)):
                return json.dumps([item.model_dump() for item in result])
            else:
                return json.dumps([str(item) for item in result])
        else:
            return str(result)


# Global orchestrator instance
orchestrator = AgentOrchestrator()
