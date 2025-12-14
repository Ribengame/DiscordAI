import discord
import asyncio
import os
from datetime import datetime, timedelta
from openai import OpenAI

# ===================== CONFIG =====================

DISCORD_TOKEN = "PASTE_DISCORD_BOT_TOKEN"
OPENAI_API_KEY = "PASTE_OPENAI_API_KEY"

SCAN_INTERVAL_MINUTES = 15
MAX_MESSAGES_PER_CHANNEL = 200  # limit for tokens
MODEL = "gpt-5.1-nano"

# ================================================

client = OpenAI(api_key=OPENAI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = discord.Client(intents=intents)

last_scan_time = None
next_scan_time = None

stats = {
    "total": 0,
    "positive": 0,
    "negative": 0,
    "neutral": 0
}


# ===================== UTILS =====================

def time_left():
    if not next_scan_time:
        return "⏳"
    delta = next_scan_time - datetime.utcnow()
    minutes = max(0, int(delta.total_seconds() // 60))
    return f"{minutes}m"


async def update_status():
    status = (
        f"⏱ next scan: {time_left()} | "
        f"📨 {stats['total']} msgs | "
        f"🙂{stats['positive']} "
        f"😐{stats['neutral']} "
        f"☠️{stats['negative']}"
    )
    await bot.change_presence(activity=discord.Game(name=status))


# ===================== OPENAI =====================

def analyze_messages(messages: list[str]):
    """
    Minimal-token prompt.
    Returns dict with sentiment counts.
    """

    prompt = f"""
Analyze Discord chat messages.
Return ONLY valid JSON.

Messages count: {len(messages)}

Classify sentiment:
- positive
- neutral
- negative

Return format:
{{
  "positive": number,
  "neutral": number,
  "negative": number
}}

Messages:
""" + "\n".join(messages)

    response = client.responses.create(
        model=MODEL,
        input=prompt,
        max_output_tokens=100  # HARD LIMIT
    )

    text = response.output_text.strip()
    return eval(text)  # trusted model output format


# ===================== SCANNER =====================

async def scan_all_channels():
    global stats, last_scan_time

    collected_messages = []

    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                async for msg in channel.history(
                    limit=MAX_MESSAGES_PER_CHANNEL,
                    after=last_scan_time
                ):
                    if not msg.author.bot and msg.content.strip():
                        collected_messages.append(msg.content.strip())
            except Exception:
                continue

    if not collected_messages:
        print("[SCAN] No new messages – skipping OpenAI call.")
        return False

    print(f"[SCAN] Analyzing {len(collected_messages)} messages")

    result = analyze_messages(collected_messages)

    stats["total"] += len(collected_messages)
    stats["positive"] += result.get("positive", 0)
    stats["neutral"] += result.get("neutral", 0)
    stats["negative"] += result.get("negative", 0)

    return True


# ===================== LOOP =====================

async def scanner_loop():
    global last_scan_time, next_scan_time

    await bot.wait_until_ready()
    last_scan_time = datetime.utcnow()

    while not bot.is_closed():
        next_scan_time = datetime.utcnow() + timedelta(minutes=SCAN_INTERVAL_MINUTES)
        await update_status()

        await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

        success = await scan_all_channels()
        last_scan_time = datetime.utcnow()

        await update_status()

        if success:
            print("[SCAN] Completed & API used")
        else:
            print("[SCAN] Completed without API call")


# ===================== EVENTS =====================

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.loop.create_task(scanner_loop())
    await update_status()


# ===================== START =====================

bot.run(DISCORD_TOKEN)
