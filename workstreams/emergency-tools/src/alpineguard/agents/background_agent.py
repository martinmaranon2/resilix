"""
Background agent: prepares an incident for the human operator with Gemini function calling.

Architecture
------------
While the voice agent talks to the caller, the background agent works through the
incident: it calls tools from the ``ToolRegistry`` (role BACKGROUND), reads their
results and decides the next step, until it writes a short summary for the operator.
- Model: ``Config.BACKGROUND_AGENT_MODEL`` (Gemini, function calling).
- The loop runs tools itself (automatic function calling is off), so every call goes
  through the registry: argument checks, approval gate and audit trail.
- Approval-tier tools only create pending actions; the agent cannot act on the world.
- Phone numbers are removed from transcripts before they are sent to the model.
- Every Gemini call is logged with model, prompt summary, configuration and output.
``google-genai`` is imported only when the agent runs, so the rest of the package works
without it.

Use cases
---------
1. A 144 call reports a collapsed person: the agent prepares incident card, protocol,
   nearest AED, ambulance and first-responder proposals for the operator.
2. Several 118 calls report a forest fire: the agent merges the reports, predicts the
   spread, finds people and trains at risk, plans a route and proposes actions.
"""

import os
from typing import Any, Dict, List, Optional, Sequence

from alpineguard.audit import AuditLog, log_genai_call
from alpineguard.config import Config
from alpineguard.models.agent_runs import AgentRunResult, AgentStopReason, ToolCallRecord
from alpineguard.models.tooling import AgentRole
from alpineguard.simulation.world import SimulatedWorld
from alpineguard.time_utils import to_iso
from alpineguard.tools.privacy import scrub_pii
from alpineguard.tools.registry import ToolRegistry

SYSTEM_INSTRUCTION = """You are the background agent of a Swiss emergency centre (112, 117, 118, 144).
A voice agent talks to the caller. You work in the background and prepare the incident for a human operator.

Rules:
1. Use the tools to get facts. Never invent positions, units, times, people counts or instructions.
2. You cannot act on the world. propose_dispatch, alert_first_responders, draft_public_alert and
   request_infra_action only create pending actions that the operator approves or rejects.
   Never say that such an action has happened.
3. Instructions for callers come only from get_protocol.
4. Do not write names or phone numbers into the incident card, messages or reasons.
5. Give every proposed action a short, specific reason with the facts that support it.
6. If facts conflict, if you are unsure, or if no protocol exists, call handoff_to_operator.
7. Records marked is_simulated are exercise data. Treat them as real for this exercise.
8. When you are done, write a short summary for the operator in English, whatever the language of
   the call: the incident, the key facts with numbers, the pending actions with their action ids,
   and open questions. Texts for the public (alerts) use the languages the tools require."""


def build_incident_task(world: SimulatedWorld, call_ids: Optional[Sequence[str]] = None) -> str:
    """
    Build the task message for the background agent from scenario calls.

    Parameters:
        world: Simulated world with the calls.
        call_ids: Calls to include; all calls when None.

    Returns:
        Task text with scenario time, call metadata, scrubbed transcripts and the operator goal.

    Raises:
        ValueError: If a call id is unknown.
    """
    selected = []
    for call in world.calls():
        if call_ids is None or call.call_id in call_ids:
            selected.append(call)
    if call_ids is not None and len(selected) != len(set(call_ids)):
        raise ValueError(f"Unknown call ids in {list(call_ids)}")
    lines = [f"Scenario time: {to_iso(world.now())}. Canton: {world.canton}."]
    for call in selected:
        lines.append(
            f"\nNew call {call.call_id} on {call.centre.value}, received {to_iso(call.received_at)}, "
            f"language {call.language.value}, address hint: {call.address_hint}. Transcript so far:"
        )
        lines.extend(f"  {scrub_pii(line)}" for line in call.transcript)
    lines.append(f"\nOperator goal: {world.operator_goal}")
    return "\n".join(lines)


class BackgroundIncidentAgent:
    """Gemini agent that prepares incidents with the tool registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        model: str = Config.BACKGROUND_AGENT_MODEL,
        client: Any = None,
        max_turns: int = Config.BACKGROUND_AGENT_MAX_TURNS,
        audit: Optional[AuditLog] = None,
    ) -> None:
        """
        Create the agent.

        Parameters:
            registry: Tool registry (the agent uses role BACKGROUND).
            model: Gemini model id.
            client: Existing ``google.genai.Client``; created from the API key when None.
            max_turns: Maximum number of model turns.
            audit: Audit trail for Gemini calls; the registry's audit trail when None.
        """
        self.registry = registry
        self.model = model
        self.max_turns = max_turns
        self._client = client
        self._audit = audit or registry.ctx.audit

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai
            from google.genai import types

            api_key = os.environ.get(Config.GEMINI_API_KEY_ENV)
            if not api_key:
                raise RuntimeError(f"Environment variable {Config.GEMINI_API_KEY_ENV} is not set")
            self._client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3)),
            )
        return self._client

    def _config(self) -> Any:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(
                name=d["name"], description=d["description"], parameters_json_schema=d["parameters"]
            )
            for d in self.registry.declarations(AgentRole.BACKGROUND)
        ]
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(function_declarations=declarations)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def run(self, task: str) -> AgentRunResult:
        """
        Work on a task until the model writes its final summary.

        Parameters:
            task: Task message (see ``build_incident_task``).

        Returns:
            Final text, tool call records, number of turns and stop reason.
        """
        from google.genai import types

        client = self._get_client()
        config = self._config()
        tool_names = [d["name"] for d in self.registry.declarations(AgentRole.BACKGROUND)]
        contents: List[Any] = [types.Content(role="user", parts=[types.Part.from_text(text=task)])]
        records: List[ToolCallRecord] = []
        prompt_summary: Any = task

        for turn in range(1, self.max_turns + 1):
            try:
                response = client.models.generate_content(model=self.model, contents=contents, config=config)
            except Exception as exc:  # network or API errors end the run with a clear record
                log_genai_call(self._audit, "background_agent", self.model, prompt_summary,
                               {"tools": len(tool_names)}, {"error": f"{type(exc).__name__}: {exc}"})
                return AgentRunResult(self.model, "", turn, AgentStopReason.ERROR, records,
                                      error=f"{type(exc).__name__}: {exc}")

            candidate = response.candidates[0] if response.candidates else None
            content = candidate.content if candidate is not None else None
            parts = list(content.parts or []) if content is not None else []
            calls = [p.function_call for p in parts if p.function_call is not None]
            text = "".join(p.text for p in parts if p.text and not p.thought)
            usage = response.usage_metadata
            log_genai_call(
                self._audit, "background_agent", self.model, prompt_summary,
                {"tools": len(tool_names), "turn": turn,
                 "prompt_tokens": getattr(usage, "prompt_token_count", None),
                 "output_tokens": getattr(usage, "candidates_token_count", None)},
                {"text": text, "function_calls": [{"name": c.name, "args": dict(c.args or {})} for c in calls],
                 "finish_reason": str(getattr(candidate, "finish_reason", None))},
            )
            if content is None:
                return AgentRunResult(self.model, "", turn, AgentStopReason.ERROR, records,
                                      error="The model returned no content")
            contents.append(content)  # keeps thought signatures for the next turn
            if not calls:
                return AgentRunResult(self.model, text, turn, AgentStopReason.FINISHED, records)

            response_parts = []
            for call in calls:
                arguments: Dict[str, Any] = dict(call.args or {})
                result = self.registry.execute(call.name, arguments, AgentRole.BACKGROUND)
                records.append(ToolCallRecord(turn=turn, name=call.name, arguments=arguments,
                                              status=str(result.get("status")), action_id=result.get("action_id")))
                response_parts.append(types.Part(function_response=types.FunctionResponse(
                    id=call.id, name=call.name, response=result)))
            contents.append(types.Content(role="user", parts=response_parts))
            prompt_summary = {"function_results": [(r.name, r.status) for r in records if r.turn == turn]}

        return AgentRunResult(self.model, "", self.max_turns, AgentStopReason.MAX_TURNS, records)
