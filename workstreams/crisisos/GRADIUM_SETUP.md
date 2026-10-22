# Gradium setup guide — Tech: Europe Agentic AI Hack Zürich

As of 10 Oct 2026.

## Overview

In about 10 minutes you get your own Gradium account with 100,000 free hackathon credits, an API key, and a tested setup. Gradium is a voice API: TTS (text-to-speech) turns text into audio, and STT (speech-to-text) turns audio into text. It supports English, French, Spanish, Portuguese and German.

You need:

- A GitHub account, or a Google account that you keep after the event.
- Your hackathon check-in and an account on [hackathons.techeurope.io](https://hackathons.techeurope.io/login). The check-in email links to it.
- A clone of `ixsanpe/hackathon-tech-europe`, and `curl`.
- Python 3.10 or newer, only for the SDK step.

If you do not want your own account, see "Sharing one key instead" at the end.

## Step 1: Create a Gradium Studio account

Sign in to Gradium Studio with GitHub. Gradium creates the account at your first sign-in.

**Caution:** do not use the temporary hackathon Google account from the "Agentic AI Hack Account Information" email. Google deletes that account the day after the event, and you would then lose the login to your Gradium account.

1. Open [studio.gradium.ai](https://studio.gradium.ai/).
2. Click **Continue with GitHub**. Google, or an email address with a password, also works.
3. On GitHub, choose your account and click **Authorize gradium-ai**. Gradium asks only for read-only access to your email addresses and profile.
4. If a Cloudflare check box appears, tick it.
5. Gradium Studio opens. A new account is on the Free plan with 45,000 credits.

## Step 2: Redeem the hackathon credits

The hackathon coupon adds 100,000 credits to your Gradium account. There is one code for everyone at the event, and it is on the hackathon platform. Gradium Studio labels in this guide are quoted from its German interface, with the English meaning in brackets.

1. Log in to [hackathons.techeurope.io](https://hackathons.techeurope.io/login) with the email address of your hackathon registration. The platform emails you an 8-digit sign-in code.
2. If the platform says you have no account, click **Create an account**, enter the same email address and the code, then fill in the short profile (name and city are required).
3. Open the [Partners tab of the Agentic AI Hack](https://hackathons.techeurope.io/dashboard/hackathons/tech-europe-agentic-ai-hack-3?tab=resources).
4. On the **Gradium** card, click **Show credit code**. The code is a link that starts with `https://studio.gradium.ai/coupon-redeem/`.
5. Open that link in the browser where you are logged in to Gradium Studio.
6. In the dialog **Gutschein einlösen** (redeem coupon), the code is already filled in. Click **Einlösen** (redeem).
7. Check for the message "100.000 Credits wurden Ihrem Konto hinzugefügt" (100,000 credits added). Your balance is now 145,000 credits.

## Step 3: Create an API key and put it in .env

Gradium Studio shows a new API key only once, so copy it straight into the `.env` file of your repo clone.

**Caution:** never commit the key, and never paste it into a chat, Discord or this file. The repo's `.gitignore` already keeps `.env` out of git.

1. In Gradium Studio, in the sidebar under **Plattform** (platform), click **API-Schlüssel** (API keys).
2. Click **+ Erstellen** (create).
3. Optional: in **Schlüsselname** (key name), enter a name such as `hackathon-<your name>`. Keep the default **Ablaufdatum** (expiry date), which is 3 months from today.
4. Click **Schlüssel erstellen** (create key).
5. Click **Kopieren** (copy). The key starts with `gsk_`.
6. In the root folder of your repo clone, open `.env`. If it does not exist and the branch has `.env.example`, copy that file to `.env` first.
7. Add this line, with your key after the `=`:

```text
GRADIUM_API_KEY=gsk_your_key_here
```

8. Back in Gradium Studio, click **Ich habe ihn sicher gespeichert** (I have saved it safely).

## Step 4: Test the key with curl

Two `curl` commands check the key without installing anything: TTS makes a WAV file, then STT transcribes it. Both together cost about 60 credits.

1. In the repo root, load `.env` into your shell (bash or zsh):

```bash
set -a && . ./.env && set +a
```

2. TTS: make `/tmp/hello.wav`:

```bash
curl -sS -L -X POST https://api.gradium.ai/api/post/speech/tts \
  -H "x-api-key: $GRADIUM_API_KEY" -H "Content-Type: application/json" \
  -d '{"text":"Hello from the Tech Europe hackathon in Zurich.","voice_id":"YTpq7expH9539ERJ","output_format":"wav","only_audio":true}' \
  -o /tmp/hello.wav -w 'HTTP %{http_code}\n'
```

Expected: `HTTP 200`, and `/tmp/hello.wav` is a playable WAV file of about 300 KB.

3. STT: transcribe `/tmp/hello.wav`:

```bash
curl -sS -L -X POST 'https://api.gradium.ai/api/post/speech/asr?json_config=%7B%22language%22%3A%22en%22%7D' \
  -H "x-api-key: $GRADIUM_API_KEY" -H "Content-Type: audio/wav" \
  --data-binary @/tmp/hello.wav
```

Expected: one JSON line per word group, for example `{"type":"text","text":"Hello","start_s":0.4,...}`. The `text` values together read "Hello from the Tech Europe Hackathon in Zurich."

The query `json_config=%7B...%7D` is `{"language":"en"}` in URL-encoded form. Gradium's docs use `--url-query` instead, which needs curl 7.87 or newer.

## Step 5: Use the Python SDK

The `gradium` package needs Python 3.10 or newer and reads `GRADIUM_API_KEY` from the environment. This guide was tested with `gradium` 0.6.4.

1. In the repo root, make a virtual environment and install the SDK:

```bash
uv venv && uv pip install gradium
```

2. Without uv, use `python3 -m venv .venv && .venv/bin/pip install gradium` instead.
3. Load `.env` (Step 4, command 1), then run your code with `.venv/bin/python`.

This example does TTS, saves the audio, then transcribes it again. It prints "Hello from Zurich.":

```python
import asyncio

from gradium import GradiumClient, STTSetup, TTSSetup


async def main() -> None:
    client = GradiumClient()  # Reads GRADIUM_API_KEY from the environment.

    tts_setup: TTSSetup = {"voice_id": "YTpq7expH9539ERJ", "output_format": "wav"}
    speech = await client.tts(setup=tts_setup, text="Hello from Zurich.")
    with open("/tmp/hello.wav", "wb") as f:
        f.write(speech.raw_data)

    stt_setup: STTSetup = {"input_format": "wav", "json_config": {"language": "en"}}
    transcript = await client.stt(setup=stt_setup, audio=speech.raw_data)
    print(transcript.text)


asyncio.run(main())
```

Tristan's `smoke_test.py` runs the same round trip and checks that the transcript matches the input text. It is not in the repo yet. Once it is, run `(set -a && . ./.env && set +a && .venv/bin/python smoke_test.py)`: a log line `PASS` and exit code 0 mean the setup works.

For live audio, such as a microphone or a voice agent, use the streaming methods `client.stt_realtime` and `client.tts_stream` (see Sources).

## Limits, costs and troubleshooting

145,000 credits are enough for about 3 hours of TTS or 13 hours of STT. Gradium Studio shows your balance and its expiry date under **Abonnement** (subscription).

| Item | Value |
| --- | --- |
| TTS cost | 1 credit per character (about 750 credits per minute of audio) |
| STT cost | 3 credits per second of audio |
| Free plan credits | 45,000 per month, plus 100,000 from the hackathon coupon |
| Text per session (free plan) | 1,500 characters at most |
| Session length | 3,000 seconds at most |
| Requests at the same time (free plan) | 3 |
| Languages | English, French, Spanish, Portuguese, German |

| Problem | Cause | Fix |
| --- | --- | --- |
| `ValueError: Missing api-key as cli or as env (GRADIUM_API_KEY)` | `.env` is not loaded in this shell | In the repo root, run `set -a && . ./.env && set +a`, then try again |
| `uv run` stops with "path segment contains separator `:`" | The folder path contains a colon | Run `.venv/bin/python` instead of `uv run` or `source .venv/bin/activate`, or move the repo to a path without a colon |
| `curl: option --url-query: is unknown` | curl is older than 7.87 | Use the encoded URL from Step 4 |
| TTS text is longer than 1,500 characters | Free-plan limit per session | Split the text into several requests |

## Sharing one key instead

If you do not want your own account, ask Tristan for the team key. You then use Tristan's 145,000 credits, and the free-plan limit of 3 requests at the same time applies to both of you together.

1. Ask for the key in a private message, for example in Signal or a password manager. Never in a group chat, in git or in this file.
2. Put the key in your `.env` as in Step 3.
3. Run the tests in Step 4.

## Sources

- [Gradium docs: installation](https://docs.gradium.ai/guides/installation)
- [Gradium API reference: authentication and server URL](https://docs.gradium.ai/api-reference/introduction)
- [Text-to-Speech (REST)](https://docs.gradium.ai/guides/text-to-speech-rest)
- [Speech-to-Text (REST)](https://docs.gradium.ai/guides/speech-to-text-rest)
- [Speech-to-Text streaming with the SDK](https://docs.gradium.ai/guides/speech-to-text)
- [Text-to-Speech streaming with the SDK](https://docs.gradium.ai/guides/text-to-speech)
- [Credits](https://docs.gradium.ai/guides/credits)
- [FAQ: languages and session limits](https://docs.gradium.ai/guides/faq)
- [Gradbot, Gradium's voice-agent framework for prototypes](https://docs.gradium.ai/integrations/agent-frameworks/gradbot)
- Gradium Studio (pages Abonnement and API-Schlüssel) and the Partners tab of the hackathon platform, as seen on 10 Oct 2026.
