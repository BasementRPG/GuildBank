import os
import discord
from discord.ext import commands
import asyncpg

# ---------------- CONFIG ----------------
TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

# ---------------- DISCORD BOT ----------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ITEM_TYPES = ["Weapon", "Armor", "Potion", "Misc"]
CLASSES = ["Warrior", "Mage", "Rogue", "Cleric"]

db_conn = None  # Will be initialized in on_ready

# ---------------- COMMANDS ----------------

@bot.tree.command(name="add_item", description="Add an item to your inventory")
async def add_item(interaction: discord.Interaction, name: str, type: str, cls: str):
    global db_conn
    if type not in ITEM_TYPES or cls not in CLASSES:
        await interaction.response.send_message("Invalid type or class.", ephemeral=True)
        return
    await db_conn.execute(
        "INSERT INTO inventory(user_id,item_name,item_type,item_class,photo_url) VALUES($1,$2,$3,$4,$5)",
        str(interaction.user.id), name, type, cls, None
    )
    await interaction.response.send_message(f"✅ Added **{name}** to your inventory.", ephemeral=True)

@bot.tree.command(name="view_items", description="View your inventory")
async def view_items(interaction: discord.Interaction):
    global db_conn
    rows = await db_conn.fetch(
        "SELECT item_name,item_type,item_class FROM inventory WHERE user_id=$1",
        str(interaction.user.id)
    )
    if not rows:
        await interaction.response.send_message("Your inventory is empty.", ephemeral=True)
        return
    desc = "\n".join([f"- {r['item_name']} ({r['item_type']} - {r['item_class']})" for r in rows])
    embed = discord.Embed(title=f"{interaction.user.name}'s Inventory", description=desc)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete_item", description="Delete an item from your inventory")
async def delete_item(interaction: discord.Interaction, item_name: str):
    global db_conn
    await db_conn.execute(
        "DELETE FROM inventory WHERE user_id=$1 AND item_name=$2",
        str(interaction.user.id), item_name
    )
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}**.", ephemeral=True)

@bot.tree.command(name="update_item", description="Update an item")
async def update_item(interaction: discord.Interaction, old_name: str, new_name: str, new_type: str, new_class: str):
    global db_conn
    if new_type not in ITEM_TYPES or new_class not in CLASSES:
        await interaction.response.send_message("Invalid type or class.", ephemeral=True)
        return
    await db_conn.execute(
        """UPDATE inventory
           SET item_name=$1, item_type=$2, item_class=$3
           WHERE user_id=$4 AND item_name=$5""",
        new_name, new_type, new_class, str(interaction.user.id), old_name
    )
    await interaction.response.send_message(f"🔄 Updated **{old_name}** to **{new_name}**.", ephemeral=True)

# ---------------- READY EVENT ----------------
@bot.event
async def on_ready():
    global db_conn
    if db_conn is None:
        db_conn = await asyncpg.connect(DATABASE_URL)
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                user_id TEXT,
                item_name TEXT,
                item_type TEXT,
                item_class TEXT,
                photo_url TEXT
            )
        """)
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
