import os
import discord
from discord.ext import commands
import asyncpg

# -------- CONFIG --------
TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# -------- DISCORD BOT --------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ITEM_TYPES = ["Weapon", "Armor", "Potion", "Misc"]
CLASSES = ["Warrior", "Mage", "Rogue", "Cleric"]

# -------- DATABASE SETUP --------
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        user_id TEXT,
        item_name TEXT,
        item_type TEXT,
        item_class TEXT,
        photo_url TEXT
    )
    """)
    return conn

loop = asyncio.get_event_loop()
db_conn = loop.run_until_complete(init_db())







