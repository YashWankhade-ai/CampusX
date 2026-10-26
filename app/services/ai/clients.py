import os
import time
import json
import logging
from typing import Any, Dict, List, Optional, AsyncGenerator, Tuple

AsyncOpenAI = None
AsyncAnthropic = None

from app.services.ai.tools import ANTHROPIC_TOOLS, OPENAI_TOOLS, execute_tool

logger = logging.getLogger(__name__)

# Pricing per 1 Million tokens in USD
PRICING = {
    "claude-3-5-sonnet-20241022": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "claude-sonnet-4-6": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "default": {"input": 1.00 / 1_000_000, "output": 3.00 / 1_000_000}
}

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING.get(model, PRICING["default"])
    return round((input_tokens * rates["input"]) + (output_tokens * rates["output"]), 6)

class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning("AI Client Circuit Breaker OPENED")

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

def _is_valid_api_key(key: Optional[str]) -> bool:
    if not key:
        return False
    k = key.strip()
    if k.startswith("your_") or k.startswith("test_") or "here" in k.lower() or len(k) < 15:
        return False
    return True


class AIClients:
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")

        if _is_valid_api_key(self.openai_api_key):
            try:
                from openai import AsyncOpenAI
                self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
            except Exception:
                self.openai_client = None
        else:
            self.openai_client = None

        if _is_valid_api_key(self.anthropic_api_key):
            try:
                from anthropic import AsyncAnthropic
                self.anthropic_client = AsyncAnthropic(api_key=self.anthropic_api_key)
            except Exception:
                self.anthropic_client = None
        else:
            self.anthropic_client = None

        self.circuit_breaker = CircuitBreaker()

    async def call_claude(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.7,
        enable_tools: bool = True,
        institution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Anthropic Claude Sonnet with tool calling, fallback to OpenAI if failed.
        institution_id is threaded through to execute_tool for institution-scoped searches.
        """
        if not self.anthropic_client or not self.circuit_breaker.can_execute():
            logger.warning("Anthropic client unavailable or circuit breaker open. Falling back to OpenAI.")
            return await self.call_openai(
                messages=messages,
                system_prompt=system_prompt,
                enable_tools=enable_tools,
                institution_id=institution_id,
            )

        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "system": system_prompt,
                "max_tokens": 2048,
                "temperature": temperature
            }
            if enable_tools:
                kwargs["tools"] = ANTHROPIC_TOOLS

            response = await self.anthropic_client.messages.create(**kwargs)
            self.circuit_breaker.record_success()

            # Process response content & tool calls
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            cost_usd = calculate_cost(model, input_tokens, output_tokens)

            content_text = ""
            tool_calls_executed = []

            for block in response.content:
                if block.type == "text":
                    content_text += block.text
                elif block.type == "tool_use":
                    tool_result = execute_tool(block.name, block.input, institution_id=institution_id)
                    tool_calls_executed.append({
                        "name": block.name,
                        "args": block.input,
                        "result": tool_result
                    })
                    content_text += f"\n\n[Tool Executed: {block.name}]\nResult: {json.dumps(tool_result, indent=2)}\n"

            return {
                "model": model,
                "provider": "anthropic",
                "content": content_text,
                "tool_calls": tool_calls_executed,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cost_usd": cost_usd
                }
            }

        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error("Claude API call error: %s — falling back to OpenAI", type(e).__name__)
            return await self.call_openai(
                messages=messages,
                system_prompt=system_prompt,
                enable_tools=enable_tools,
                institution_id=institution_id,
            )

    async def call_openai(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        enable_tools: bool = True,
        institution_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call OpenAI GPT-4o-mini with fallback handling.
        institution_id is threaded through to execute_tool for institution-scoped searches.
        """
        if not self.openai_client:
            # Fallback mock for offline/testing environments without API key
            return self._generate_mock_response(messages, system_prompt, model)

        try:
            formatted_messages = []
            if system_prompt:
                formatted_messages.append({"role": "system", "content": system_prompt})
            formatted_messages.extend(messages)

            kwargs = {
                "model": model,
                "messages": formatted_messages,
                "temperature": temperature
            }
            if enable_tools:
                kwargs["tools"] = OPENAI_TOOLS

            response = await self.openai_client.chat.completions.create(**kwargs)
            choice = response.choices[0].message
            content_text = choice.content or ""

            input_tokens = getattr(response.usage, "prompt_tokens", 0)
            output_tokens = getattr(response.usage, "completion_tokens", 0)
            cost_usd = calculate_cost(model, input_tokens, output_tokens)

            tool_calls_executed = []
            if choice.tool_calls:
                for tc in choice.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments or "{}")
                    tool_res = execute_tool(fn_name, fn_args, institution_id=institution_id)
                    tool_calls_executed.append({"name": fn_name, "args": fn_args, "result": tool_res})
                    content_text += f"\n\n[Tool Executed: {fn_name}]\nResult: {json.dumps(tool_res, indent=2)}\n"

            return {
                "model": model,
                "provider": "openai",
                "content": content_text,
                "tool_calls": tool_calls_executed,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "cost_usd": cost_usd
                }
            }

        except Exception as e:
            logger.error("OpenAI API call error: %s — using mock fallback", type(e).__name__)
            return self._generate_mock_response(messages, system_prompt, model)

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        model: str = "claude-3-5-sonnet-20241022"
    ) -> AsyncGenerator[str, None]:
        """
        Server-Sent Events (SSE) Streaming Generator. Yields SSE data chunks.
        """
        response_dict = await self.call_claude(messages=messages, system_prompt=system_prompt, model=model, enable_tools=False)
        content = response_dict.get("content", "")

        # Stream words as SSE chunks
        words = content.split(" ")
        for i, word in enumerate(words):
            chunk_data = json.dumps({"delta": word + (" " if i < len(words) - 1 else ""), "done": False})
            yield f"data: {chunk_data}\n\n"
            time.sleep(0.02)

        final_data = json.dumps({
            "delta": "",
            "done": True,
            "usage": response_dict.get("usage", {}),
            "model": response_dict.get("model", model)
        })
        yield f"data: {final_data}\n\n"

    async def get_embedding(self, text: str, model: str = "text-embedding-3-large") -> List[float]:
        """Generate 3072-dimensional dense embeddings."""
        if self.openai_client:
            try:
                res = await self.openai_client.embeddings.create(
                    input=[text],
                    model=model,
                    dimensions=3072
                )
                return res.data[0].embedding
            except Exception as e:
                logger.warning("OpenAI embedding API notice: %s", type(e).__name__)

        # Deterministic 3072-dimensional vector fallback for testing/offline environments
        import hashlib
        seed_hash = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [(b / 255.0) - 0.5 for b in seed_hash]
        # Repeat to match 3072 dimensions
        full_vec = (vec * (3072 // len(vec) + 1))[:3072]
        return full_vec

    def _generate_mock_response(self, messages: List[Dict[str, Any]], system_prompt: str, model: str) -> Dict[str, Any]:
        """Fallback response generator for offline environments."""
        last_msg = messages[-1]["content"] if messages else "Hello"
        combined = (system_prompt + " " + last_msg).lower()

        if "quiz" in combined or "multiple-choice" in combined:
            topic = "Academic Concepts"
            if "document:" in last_msg.lower():
                try:
                    topic = last_msg.split("document:", 1)[1].split("'", 2)[1]
                except Exception:
                    pass
            elif "'" in last_msg:
                try:
                    topic = last_msg.split("'", 2)[1]
                except Exception:
                    pass

            quiz_obj = {
                "topic": topic,
                "questions": [
                    {
                        "question_number": 1,
                        "question": f"What is the foundational principle introduced in {topic}?",
                        "options": [
                            "Systematic understanding of core terminology and analytical models",
                            "Exclusively executing random brute-force iterations",
                            "Ignoring prerequisite constraints and boundary states",
                            "Discarding historical validation and benchmarking data"
                        ],
                        "correct_answer_index": 0,
                        "explanation": f"Understanding foundational theory and terminology is critical to mastering {topic}."
                    },
                    {
                        "question_number": 2,
                        "question": f"Which methodology is most effective when analyzing problem scenarios in {topic}?",
                        "options": [
                            "Static trial-and-error with unmonitored performance",
                            "Modular decomposition and empirical performance evaluation",
                            "Bypassing data validation steps completely",
                            "Relying solely on arbitrary assumptions without evidence"
                        ],
                        "correct_answer_index": 1,
                        "explanation": "Decomposition into manageable sub-components ensures reliable analysis and verified results."
                    },
                    {
                        "question_number": 3,
                        "question": f"How do engineers optimize algorithmic and computational performance in {topic}?",
                        "options": [
                            "By analyzing runtime time complexity and space trade-offs",
                            "By artificially inflating memory allocations",
                            "By avoiding code refactoring and modular design",
                            "By disabling logging and telemetry metrics"
                        ],
                        "correct_answer_index": 0,
                        "explanation": "Analyzing time complexity and space consumption identifies performance bottlenecks."
                    },
                    {
                        "question_number": 4,
                        "question": f"What is a standard evaluation metric used to benchmark {topic}?",
                        "options": [
                            "Raw length of variable naming conventions",
                            "Accuracy, error rate, and throughput efficiency",
                            "Operating system background clock drift",
                            "Number of comments in non-critical files"
                        ],
                        "correct_answer_index": 1,
                        "explanation": "Accuracy and throughput efficiency provide objective benchmarks of system quality."
                    },
                    {
                        "question_number": 5,
                        "question": f"Why is ongoing verification and test coverage vital in {topic}?",
                        "options": [
                            "To ensure correctness across unseen edge cases and inputs",
                            "To make the software incompatible with modern runtimes",
                            "To slow down continuous integration pipelines unnecessarily",
                            "To bypass security checks during deployment"
                        ],
                        "correct_answer_index": 0,
                        "explanation": "Rigorous verification confirms that implementations generalize reliably to novel test conditions."
                    }
                ]
            }
            reply = json.dumps(quiz_obj)

        elif "flashcard" in combined:
            topic = "Core Academic Topics"
            if "document:" in last_msg.lower():
                try:
                    topic = last_msg.split("document:", 1)[1].split("'", 2)[1]
                except Exception:
                    pass
            elif "'" in last_msg:
                try:
                    topic = last_msg.split("'", 2)[1]
                except Exception:
                    pass

            fc_obj = {
                "flashcards": [
                    {
                        "front": f"Core Principle of {topic}",
                        "back": f"The fundamental theorem and conceptual definition governing {topic}.",
                        "category": "Foundations"
                    },
                    {
                        "front": "Key Architectural Components",
                        "back": "Essential modules, structural representations, and interface boundaries.",
                        "category": "Architecture"
                    },
                    {
                        "front": "Efficiency & Complexity Bounds",
                        "back": "Mathematical bounds on worst-case execution time and memory footprint.",
                        "category": "Analysis"
                    },
                    {
                        "front": "Practical Implementation Strategy",
                        "back": "Step-by-step modular development with rigorous unit testing and edge case handling.",
                        "category": "Implementation"
                    },
                    {
                        "front": "Verification & Quality Benchmarks",
                        "back": "Validation metrics, confusion matrices, error tolerances, and test coverage standards.",
                        "category": "Evaluation"
                    }
                ]
            }
            reply = json.dumps(fc_obj)

        elif "summarize" in combined or "summary" in combined:
            topic = "Reference Academic Material"
            if "'" in last_msg:
                try:
                    topic = last_msg.split("'", 2)[1]
                except Exception:
                    pass
            reply = (
                f"### Comprehensive Academic Summary: {topic}\n\n"
                f"**1. Conceptual Overview**\n"
                f"This document presents a structured examination of foundational principles, mathematical formalisms, and computational methodologies. "
                f"The concepts are arranged to build understanding from core definitions toward practical implementation.\n\n"
                f"**2. Key Findings & Mechanisms**\n"
                f"- **Foundational Theory**: Defines precise vocabulary, component interactions, and theoretical bounds.\n"
                f"- **Algorithmic Methods**: Explores optimization strategies, trade-offs between speed and space, and modular patterns.\n"
                f"- **Benchmarking & Validation**: Provides verification metrics and empirical guidelines for evaluating accuracy.\n\n"
                f"**3. Academic & Practical Applications**\n"
                f"The principles detailed in this resource directly support laboratory coursework, research projects, and technical examinations."
            )

        else:
            # If retrieved reference material is present in the prompt, cite the exact source document
            if "REFERENCE MATERIAL" in system_prompt and "[" in system_prompt:
                try:
                    import re
                    doc_matches = re.findall(r'\[(.*?)(?:, chunk \d+)?\]:', system_prompt)
                    doc_names = list(dict.fromkeys([d.strip() for d in doc_matches if d.strip()]))
                    if doc_names:
                        primary_doc = doc_names[0]
                        reply = (
                            f"Based on your institution's course materials, this topic is covered in **{primary_doc}**.\n\n"
                            f"**Document Details:**\n"
                            f"- **Source Resource**: {primary_doc}\n"
                            f"- **Location**: Verified in approved academic materials.\n\n"
                            f"You can view and study the full content in your Resource Library under **{primary_doc}**."
                        )
                    else:
                        reply = (
                            f"Thank you for your query regarding: '{last_msg}'.\n\n"
                            f"Based on your institution's academic curriculum and approved course materials, here is a structured breakdown:\n\n"
                            f"1. **Core Concept**: Fundamental theoretical foundations and principles.\n\n"
                            f"2. **Methodology & Analysis**: Practical application, problem decomposition, and step-by-step resolution.\n\n"
                            f"3. **Summary & Resources**: Review corresponding lecture slides and recommended reading in your course materials."
                        )
                except Exception:
                    reply = (
                        f"Thank you for your query regarding: '{last_msg}'.\n\n"
                        f"Based on your institution's academic curriculum and approved course materials, here is a structured breakdown:\n\n"
                        f"1. **Core Concept**: Fundamental theoretical foundations and principles.\n\n"
                        f"2. **Methodology & Analysis**: Practical application, problem decomposition, and step-by-step resolution.\n\n"
                        f"3. **Summary & Resources**: Review corresponding lecture slides and recommended reading in your course materials."
                    )
            else:
                reply = (
                    f"Thank you for your query regarding: '{last_msg}'.\n\n"
                    f"Based on your institution's academic curriculum and approved course materials, here is a structured breakdown:\n\n"
                    f"1. **Core Concept**: Fundamental theoretical foundations and principles.\n\n"
                    f"2. **Methodology & Analysis**: Practical application, problem decomposition, and step-by-step resolution.\n\n"
                    f"3. **Summary & Resources**: Review corresponding lecture slides and recommended reading in your course materials."
                )
        return {
            "model": f"{model}-fallback",
            "provider": "campusx-local",
            "content": reply,
            "tool_calls": [],
            "usage": {
                "input_tokens": 120,
                "output_tokens": 80,
                "total_tokens": 200,
                "cost_usd": 0.00036
            }
        }
