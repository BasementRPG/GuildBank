import os
import discord
from discord.ext import commands
import asyncio
import psycopg

async def connect_db():
    conn = await psycopg.AsyncConnection.connect(os.environ["DATABASE_URL"])
    return conn

# -------- CONFIG --------
TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# -------- DISCORD BOT --------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -------- DATABASE --------
conn = psycopg.connect(DATABASE_URL, autocommit=True)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    user_id TEXT,
    item_name TEXT,
    item_type TEXT,
    item_class TEXT,
    photo_url TEXT
)
""")

ITEM_TYPES = ["Weapon", "Armor", "Potion", "Misc"]
CLASSES = ["Warrior", "Mage", "Rogue", "Cleric"]

# -------- COMMANDS --------

@bot.tree.command(name="add_item", description="Add an item to your inventory")
async def add_item(interaction: discord.Interaction, name: str, type: str, cls: str):
    if type not in ITEM_TYPES or cls not in CLASSES:
        await interaction.response.send_message("Invalid type or class.", ephemeral=True)
        return
    cur.execute("INSERT INTO inventory VALUES (%s,%s,%s,%s,%s)",
                (str(interaction.user.id), name, type, cls, None))
    await interaction.response.send_message(f"✅ Added **{name}** to your inventory.", ephemeral=True)

@bot.tree.command(name="view_items", description="View your inventory")
async def view_items(interaction: discord.Interaction):
    cur.execute("SELECT item_name, item_type, item_class FROM inventory WHERE user_id=%s", (str(interaction.user.id),))
    rows = cur.fetchall()
    if not rows:
        await interaction.response.send_message("Your inventory is empty.", ephemeral=True)
        return
    desc = "\n".join([f"- {r[0]} ({r[1]} - {r[2]})" for r in rows])
    embed = discord.Embed(title=f"{interaction.user.name}'s Inventory", description=desc)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete_item", description="Delete an item from your inventory")
async def delete_item(interaction: discord.Interaction, item_name: str):
    cur.execute("DELETE FROM inventory WHERE user_id=%s AND item_name=%s",
                (str(interaction.user.id), item_name))
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}** from your inventory.", ephemeral=True)

@bot.tree.command(name="update_item", description="Update an item")
async def update_item(interaction: discord.Interaction, old_name: str, new_name: str, new_type: str, new_class: str):
    if new_type not in ITEM_TYPES or new_class not in CLASSES:
        await interaction.response.send_message("Invalid type or class.", ephemeral=True)
        return
    cur.execute("""UPDATE inventory
                   SET item_name=%s, item_type=%s, item_class=%s
                   WHERE user_id=%s AND item_name=%s""",
                (new_name, new_type, new_class, str(interaction.user.id), old_name))
    await interaction.response.send_message(f"🔄 Updated **{old_name}** to **{new_name}**.", ephemeral=True)

# -------- READY --------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)







