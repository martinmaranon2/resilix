"""
Voice agent: talks to the caller with the Gemini Live API and the five fast voice tools.

Architecture
------------
One ``VoiceCallSession`` is one phone call. It opens a Gemini Live session (audio out,
transcription on) with the function declarations of role VOICE from the ``ToolRegistry``:
locate_caller, update_incident, get_protocol, find_aed, handoff_to_operator.
- Tool calls are run through the registry (argument checks, audit trail) and answered at
  once. Probe on 2026-10-10: ``gemini-3.8-live`` stays silent between a tool call and its
  result, also with NON_BLOCKING, so voice tools must be fast; slow work belongs to the
  background agent.
- ``push_update`` sends facts from the background agent or the operator into the call
  (for example "ambulance approved, ETA 3 min"), marked as a system update.
- The model must not promise help that the operator has not approved: in the probe a
  Live model said "I've dispatched emergency services" without any dispatch.
- Callbacks receive audio (24 kHz 16-bit mono PCM) and the transcript of the agent.
``google-genai`` is imported only when a session starts.

Use cases
---------
1. Demo: a scripted caller (text) and the agent's spoken answers saved as WAV.
2. Later: phone audio in via ``send_realtime_input`` and audio out to the caller.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from alpineguard.audit import AuditLog, log_genai_call
from alpineguard.config import Config
from alpineguard.models.tooling import AgentRole
from alpineguard.tools.privacy import scrub_pii
from alpineguard.tools.registry import ToolRegistry

VOICE_SYSTEM_INSTRUCTION = """You are the voice agent of a Swiss emergency centre. You talk to a caller on the phone.
Speak the caller's language. Use short, calm sentences. Ask one question at a time.

Rules:
1. At the start, call locate_caller with the call id you are given.
2. As soon as you know the kind of emergency, call get_protocol and follow it: ask its questions
   and give only its instructions. Never give medical or safety advice that is not in the protocol.
3. Create the incident card early with update_incident, and update it when you learn more.
   Never put names or phone numbers into it.
4. For a cardiac arrest, call find_aed and tell the caller where the nearest AED is, so that a
   second person can fetch it while the caller keeps pushing.
5. You cannot send help. A human operator decides. Never say that an ambulance, fire brigade or
   police is on the way, unless a message marked [SYSTEM UPDATE] says that the operator approved it.
   When such an update arrives, tell the caller in one short sentence what is coming and when
   (for example "The ambulance arrives in about 3 minutes"), then continue with the protocol.
6. If the caller's situation is not covered by the protocol, or you are unsure, call
   handoff_to_operator and tell the caller that a person will speak with them now.
7. Messages marked [SYSTEM UPDATE] come from the emergency centre, not from the caller."""


@dataclass
class VoiceTurn:
    """What the caller said and what the agent answered in one turn."""

    caller_text: str
    agent_text: str = ""
    tool_calls: List[str] = field(default_factory=list)


def answer_tool_calls(registry: ToolRegistry, function_calls: List[Any]) -> List[Dict[str, Any]]:
    """
    Run the voice agent's tool calls through the registry.

    Parameters:
        registry: Tool registry (the calls run with role VOICE).
        function_calls: Function calls from the Live API (with id, name, args).

    Returns:
        One dictionary per call with "id", "name" and "response" (the tool result).
    """
    answers = []
    for call in function_calls:
        result = registry.execute(call.name, dict(call.args or {}), AgentRole.VOICE)
        answers.append({"id": call.id, "name": call.name, "response": result})
    return answers


class VoiceCallSession:
    """One phone call between a caller and the Gemini Live voice agent."""

    def __init__(
        self,
        registry: ToolRegistry,
        call_id: str,
        model: str = Config.VOICE_AGENT_MODEL,
        client: Any = None,
        on_audio: Optional[Callable[[bytes], None]] = None,
        on_text: Optional[Callable[[str], None]] = None,
        audit: Optional[AuditLog] = None,
    ) -> None:
        """
        Prepare the call session.

        Parameters:
            registry: Tool registry (role VOICE is used).
            call_id: Id of the call in the telephony system / simulated world.
            model: Gemini Live model id.
            client: Existing ``google.genai.Client``; created from the API key when None.
            on_audio: Called with each PCM audio chunk of the agent.
            on_text: Called with each piece of the agent's transcript.
            audit: Audit trail for Gemini call records; the registry's when None.
        """
        self.registry = registry
        self.call_id = call_id
        self.model = model
        self._client = client
        self._on_audio = on_audio
        self._on_text = on_text
        self._audit = audit or registry.ctx.audit
        self._session: Any = None
        self._turn_done = asyncio.Event()
        self._current: Optional[VoiceTurn] = None
        self.turns: List[VoiceTurn] = []

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai

            api_key = os.environ.get(Config.GEMINI_API_KEY_ENV)
            if not api_key:
                raise RuntimeError(f"Environment variable {Config.GEMINI_API_KEY_ENV} is not set")
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _config(self) -> Any:
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(name=d["name"], description=d["description"], parameters_json_schema=d["parameters"])
            for d in self.registry.declarations(AgentRole.VOICE)
        ]
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=f"{VOICE_SYSTEM_INSTRUCTION}\n\nThe current call id is {self.call_id}.",
            tools=[types.Tool(function_declarations=declarations)],
        )

    async def _reader(self) -> None:
        from google.genai import types

        while True:
            async for message in self._session.receive():
                if message.tool_call:
                    calls = list(message.tool_call.function_calls or [])
                    if self._current is not None:
                        self._current.tool_calls.extend(c.name for c in calls)
                    answers = answer_tool_calls(self.registry, calls)
                    await self._session.send_tool_response(function_responses=[
                        types.FunctionResponse(id=a["id"], name=a["name"], response=a["response"]) for a in answers
                    ])
                content = message.server_content
                if content is None:
                    continue
                if content.model_turn:
                    for part in content.model_turn.parts or []:
                        if part.inline_data and part.inline_data.data and self._on_audio:
                            self._on_audio(part.inline_data.data)
                if content.output_transcription and content.output_transcription.text:
                    if self._current is not None:
                        self._current.agent_text += content.output_transcription.text
                    if self._on_text:
                        self._on_text(content.output_transcription.text)
                if content.turn_complete:
                    self._turn_done.set()

    async def say(self, text: str, timeout_s: float = 45.0) -> VoiceTurn:
        """
        Send what the caller says (as text) and wait until the agent has answered.

        Parameters:
            text: Caller words; phone numbers and self-introduced names are removed first.
            timeout_s: Maximum wait for the agent's answer.

        Returns:
            The turn with the agent's transcript and tool calls.

        Raises:
            RuntimeError: If the session is not open.
        """
        if self._session is None:
            raise RuntimeError("The call session is not open")
        from google.genai import types

        clean = scrub_pii(text)
        self._current = VoiceTurn(caller_text=clean)
        self._turn_done.clear()
        await self._session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=clean)]), turn_complete=True
        )
        try:
            # a tool call ends one model turn; the answer after the tool result is the next turn
            while True:
                await asyncio.wait_for(self._turn_done.wait(), timeout=timeout_s)
                self._turn_done.clear()
                if self._current.agent_text.strip():
                    try:
                        await asyncio.wait_for(self._turn_done.wait(), timeout=1.5)
                        self._turn_done.clear()
                        continue
                    except asyncio.TimeoutError:
                        break
        except asyncio.TimeoutError:
            pass
        turn = self._current
        self.turns.append(turn)
        log_genai_call(self._audit, "voice_agent", self.model, {"caller": turn.caller_text},
                       {"tools": [d["name"] for d in self.registry.declarations(AgentRole.VOICE)]},
                       {"agent": turn.agent_text, "tool_calls": turn.tool_calls})
        return turn

    async def push_update(self, text: str, timeout_s: float = 45.0) -> VoiceTurn:
        """
        Give the agent a fact from the emergency centre (operator or background agent).

        Parameters:
            text: The fact, for example "Operator approved ambulance amb-11, ETA 3 min."
            timeout_s: Maximum wait for the agent's reaction.

        Returns:
            The turn in which the agent reacted.
        """
        return await self.say(f"[SYSTEM UPDATE] {text}", timeout_s)

    async def __aenter__(self) -> "VoiceCallSession":
        """Open the Live session and start reading its messages."""
        self._connection = self._get_client().aio.live.connect(model=self.model, config=self._config())
        self._session = await self._connection.__aenter__()
        self._reader_task = asyncio.create_task(self._reader())
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Stop reading and close the Live session."""
        self._reader_task.cancel()
        try:
            await self._reader_task
        except (asyncio.CancelledError, Exception):
            pass
        await self._connection.__aexit__(*exc)
        self._session = None
