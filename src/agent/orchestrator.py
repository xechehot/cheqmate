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

from anthropic import Anthropic

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
        """Initialize the orchestrator with Anthropic client."""
        if not settings.anthropic_api_key:
            raise ValueError("Anthropic API key is required")
        # Initialize client with 60 second timeout to prevent hanging
        self.client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=60.0,  # 60 second timeout for API calls
        )
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
                # 1. REASON: Call Claude with tools
                # Log conversation size for debugging
                total_size = sum(len(str(msg)) for msg in messages)
                logger.info(
                    f"Calling Claude API: {len(messages)} messages, "
                    f"~{total_size} chars total"
                )

                response = self.client.messages.create(
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
        logger.info(
            f"Agent orchestration completed for chat {chat_id} in {total_duration:.2f}s "
            f"({iteration} iterations)"
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

        # Format results for Claude with truncation for large content
        MAX_TOOL_RESULT_SIZE = 10000  # 10KB limit per tool result

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

                # Truncate large results (e.g., base64 images) to prevent conversation bloat
                if result_size > MAX_TOOL_RESULT_SIZE:
                    truncated_content = (
                        f"Success: {tool_block.name} completed. "
                        f"Result size: {result_size} bytes "
                        f"(truncated from conversation history to prevent bloat). "
                        f"Data has been processed successfully."
                    )
                    logger.info(
                        f"Truncated {tool_block.name} result: {result_size} bytes -> "
                        f"{len(truncated_content)} bytes"
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": truncated_content,
                        }
                    )
                else:
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
        Execute a single tool call.

        Args:
            tool_block: Tool use block from Claude containing name and input
            tool_context: Context data for tool execution

        Returns:
            Tool result as string

        Raises:
            ValueError: If tool is unknown or execution fails
        """
        tool_name = tool_block.name
        tool_input = tool_block.input

        tool_start_time = time.time()
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Tool input: {tool_input}")

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
            # Return base64 for binary data
            return base64.b64encode(result).decode("utf-8")
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
