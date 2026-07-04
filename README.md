# nepremicnine-bot

## Setup

1. Create a virtual environment.
2. Install dependencies: `pip install -e .[dev]`
3. Copy `.env.example` to `.env` and fill in Telegram credentials.

## Commands

- `nepremicnine-bot poll`
- `nepremicnine-bot digest`
- `nepremicnine-bot bot`

## Windows Task Scheduler

- Realtime poll: every 5 minutes, run `python -m nepremicnine_bot.cli poll`
- Daily digest: once per day, run `python -m nepremicnine_bot.cli digest`
