# Pretty Good AI — Voice Bot Tester

Automated testing system that calls Pretty Good AI's medical office voice bot using AI-powered phone calls. It simulates real patients with different personas, records every call, and analyzes the bot's responses for bugs.

## What It Does

- Makes outbound phone calls to the target bot via the **VAPI** API
- Uses **GPT-4o** to power realistic patient personas that have natural back-and-forth conversations
- Runs **chained multi-step scenarios** (e.g. schedule → reschedule → cancel an appointment)
- Downloads call **recordings** (WAV) and saves **transcripts** (JSON)
- Analyzes each call for **bugs, quality issues, and information gaps**
- Tracks **cost** per call and across the full run
- Generates a final **bug report** summarizing all findings

## Project Structure

```
src/
  run_one_call.py       # Main entry point — runs single calls or full sequences
  assistant_factory.py  # All patient personas and chained scenario definitions
  vapi_client.py        # VAPI API client (create assistants, make calls, poll status)
  storage.py            # Saves transcripts, recordings, analysis, and cost logs
runs/                   # Created at runtime (gitignored)
  transcripts/          # Call data + transcripts (JSON)
  recordings/           # Call audio files (WAV)
  analysis/             # Per-call bug analysis (JSON)
  reports/              # Final aggregated bug reports (JSON)
  cost_log.json         # Running cost tracker across all calls
```

## Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd prettygoodai-bot
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up environment variables

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

Then edit `.env` with your actual values:

```env
# VAPI AI Configuration
VAPI__PRIVATE_API_KEY=your_vapi_private_key_here
VAPI__PUBLIC_API_KEY=your_vapi_public_key_here
VAPI_PHONE_NUMBER_ID=your_vapi_phone_number_id_here

# Target Configuration
TARGET_PHONE_NUMBER=+18054398008
```

You'll need:
- A [VAPI](https://vapi.ai) account with API keys
- A VAPI phone number (used as the caller ID for outbound calls)
- The target phone number of the bot you want to test

## Usage

Make sure the virtual environment is activated before running:

```bash
source .venv/bin/activate
```

### Run a single test call

```bash
python3 src/run_one_call.py single appointment
```

Available personas: `appointment`, `elderly`, `urgent`, `insurance`, `random`

### Run a full test sequence

```bash
python3 src/run_one_call.py sequence 12
```

This runs 12 calls in order:
1. **Schedule Chain** (3 calls) — Schedule → Reschedule → Cancel appointment
2. **Medication Chain** (2 calls) — Request insulin refill → Check refill status
3. **New Patient Chain** (2 calls) — New patient inquiry → Schedule first visit
4. **Standalone calls** (5 calls) — Individual personas cycling through appointment, elderly, urgent, insurance

Each call waits 20-30 seconds between calls to avoid overlap.

### Run a follow-up call

```bash
python3 src/run_one_call.py followup appointment_scheduling
```

## Output

After a run completes, check the `runs/` directory:

- **Transcripts** → `runs/transcripts/call_01_chain_schedule.json`
- **Recordings** → `runs/recordings/call_01_chain_schedule.wav`
- **Analysis** → `runs/analysis/call_01_chain_schedule_analysis.json`
- **Cost log** → `runs/cost_log.json` (cumulative across all calls)
- **Bug report** → `runs/reports/bug_report_<timestamp>.json`

## Configuration

Key settings you can adjust in `src/vapi_client.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `maxDurationSeconds` | 420 | Max call length (7 minutes) |
| `silenceTimeoutSeconds` | 30 | Hang up after 30s of silence |
| `model` | gpt-4o | OpenAI model for conversation |
| `temperature` | 0.7 | Creativity of responses |

Voice settings are in `src/assistant_factory.py` — all personas use the same ElevenLabs voice for consistency.

## Tech Stack

- **VAPI** — Voice AI platform for outbound phone calls
- **OpenAI GPT-4o** — Powers the patient conversation AI
- **ElevenLabs** — Text-to-speech (voice: "Will")
- **Python 3.12** — asyncio + aiohttp for async API calls
