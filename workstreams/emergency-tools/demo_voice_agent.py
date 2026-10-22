"""
Demo: the Gemini Live voice agent talks to a scripted caller.

Architecture
------------
1. Load the cardiac arrest scenario (or another scenario with a "voice_script").
2. Open a Live session with the five fast voice tools.
3. Play the script: caller lines are sent as text; "system" lines are sent as
   [SYSTEM UPDATE] (for example the operator's approval of an ambulance).
4. Print the agent's transcript and tool calls, save the agent's speech as a WAV file.

Use cases
---------
    python demo_voice_agent.py
    python demo_voice_agent.py --scenario cardiac_arrest_zurich_hb --model gemini-3.8-live
Needs GEMINI_API_KEY in the environment.
"""

import argparse
import asyncio
import os
import sys
import wave

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from alpineguard import SimulatedWorld, ToolContext, build_registry
from alpineguard.agents.voice_agent import VoiceCallSession
from alpineguard.config import Config


def parse_args() -> argparse.Namespace:
    """
    Read command line options.

    Returns:
        Parsed options.
    """
    parser = argparse.ArgumentParser(description="Run the AlpineGuard voice agent with a scripted caller.")
    parser.add_argument("--scenario", default="cardiac_arrest_zurich_hb")
    parser.add_argument("--model", default=Config.VOICE_AGENT_MODEL)
    return parser.parse_args()


async def run(scenario_id: str, model: str) -> int:
    """
    Play the scenario's voice script.

    Parameters:
        scenario_id: Scenario with a voice script.
        model: Gemini Live model id.

    Returns:
        Process exit code: 0 when every turn got an answer.
    """
    world = SimulatedWorld.load(scenario_id)
    if not world.voice_script:
        print(f"Scenario {scenario_id} has no voice_script")
        return 1
    ctx = ToolContext.for_world(world)
    registry = build_registry(ctx)
    audio = bytearray()

    print("=" * 80)
    print(f"VOICE CALL: {world.title}  (model: {model})")
    print("=" * 80)
    async with VoiceCallSession(registry, world.trigger_call_ids[0], model=model, on_audio=audio.extend) as call:
        for step in world.voice_script:
            if step["speaker"] == "system":
                print(f"\n[SYSTEM UPDATE] {step['text']}")
                turn = await call.push_update(step["text"])
            else:
                print(f"\nCALLER: {step['text']}")
                turn = await call.say(step["text"])
            if turn.tool_calls:
                print(f"  (tools: {', '.join(turn.tool_calls)})")
            print(f"AGENT:  {turn.agent_text.strip() or '(no answer)'}")

    Config.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = Config.ARTIFACT_DIR / f"voice-{world.scenario_id}.wav"
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(Config.VOICE_AUDIO_SAMPLE_RATE)
        handle.writeframes(bytes(audio))
    print("\n" + "-" * 80)
    print(f"Incidents: {[(i.id, i.category.value, i.status.value) for i in ctx.incidents.values()]}")
    print(f"Hand-offs: {[h.reason for h in world.handoffs]}")
    print(f"Agent speech: {wav_path} ({len(audio) / 2 / Config.VOICE_AUDIO_SAMPLE_RATE:.1f} s)")
    return 0 if all(t.agent_text.strip() for t in call.turns) else 1


if __name__ == "__main__":
    options = parse_args()
    sys.exit(asyncio.run(run(options.scenario, options.model)))
