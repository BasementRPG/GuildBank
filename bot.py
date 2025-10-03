import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncpg

# -------------------------------
# Bot setup
# -------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = None

# -------------------------------
# Constants
# -------------------------------
ITEM_TYPES = ["Armor", "Crafting", "Misc", "Quest", "Potion", "Weapon"]

SUBTYPES = {
    "Armor": ["Cloth", "Leather", "Chain", "Plate"],
    "Crafting": ["Alchemy", "Smithing", "Tailoring"],
    "Misc": ["General", "Other"],
    "Quest": ["Quest Item"],
    "Potion": ["Health", "Mana"],
    "Weapon": ["Sword", "Axe", "Bow", "Dagger"],
}

CLASSES = [
    "Archer", "Bard", "Beastmaster", "Cleric", "Druid", "Elementalist",
    "Enchanter", "Fighter", "Inquisitor", "Monk", "Necromancer", "Paladin",
    "Ranger", "Rogue", "Shadow Knight", "Shaman", "Spellblade", "Wizard"
]

# -------------------------------
# PostgreSQL DB functions
# -------------------------------
async def init_db():
    """Initialize PostgreSQL connection and create table if needed."""
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                subtype TEXT NOT NULL,
                stats TEXT,
                classes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
        ''')

async def add_item_db(name, type_, subtype, stats, classes):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO inventory (name, type, subtype, stats, classes)
            VALUES ($1, $2, $3, $4, $5)
        ''', name, type_, subtype, stats, classes)

async def get_all_items():
    async with db_pool.acquire() as conn:
        return await conn.fetch('''
            SELECT id, name, type, subtype, stats, classes
            FROM inventory
            ORDER BY name ASC
        ''')

# -------------------------------
# Add Item Command
# -------------------------------
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
@app_commands.describe(item_type="Choose the item type")
@app_commands.choices(item_type=[app_commands.Choice(name=t, value=t) for t in ITEM_TYPES])
async def add_item(interaction: discord.Interaction, item_type: app_commands.Choice[str]):
    await interaction.response.send_message(f"Adding item of type **{item_type.value}**...", ephemeral=True)
    
    def check(m):
        return m.author == interaction.user and isinstance(m.channel, discord.DMChannel)
    
    # Ask for item name
    await interaction.user.send("Enter Item Name:")
    try:
        name_msg = await bot.wait_for("message", check=check, timeout=60)
        item_name = name_msg.content
    except:
        await interaction.user.send("Timed out.")
        return
    
    # Ask for subtype
    subtypes = SUBTYPES[item_type.value]
    await interaction.user.send(f"Choose Subtype ({', '.join(subtypes)}):")
    try:
        subtype_msg = await bot.wait_for("message", check=check, timeout=60)
        item_subtype = subtype_msg.content
        if item_subtype not in subtypes:
            await interaction.user.send(f"Invalid subtype, defaulting to {subtypes[0]}")
            item_subtype = subtypes[0]
    except:
        item_subtype = subtypes[0]
    
    # Ask for stats
    stats_prompt = ""
    if item_type.value == "Weapon":
        stats_prompt = "Enter Attack:"
        await interaction.user.send(stats_prompt)
        try:
            attack_msg = await bot.wait_for("message", check=check, timeout=60)
            attack = attack_msg.content
        except:
            attack = "0"
        await interaction.user.send("Enter Delay:")
        try:
            delay_msg = await bot.wait_for("message", check=check, timeout=60)
            delay = delay_msg.content
        except:
            delay = "0"
        stats = f"Attack: {attack} | Delay: {delay}"
    elif item_type.value == "Armor":
        await interaction.user.send("Enter Defense:")
        try:
            defense_msg = await bot.wait_for("message", check=check, timeout=60)
            defense = defense_msg.content
        except:
            defense = "0"
        stats = f"Defense: {defense}"
    else:
        stats = ""
    
    # Usable classes
    await interaction.user.send(f"Enter usable classes separated by comma (or 'All'):\nOptions: {', '.join(CLASSES)}")
    try:
        classes_msg = await bot.wait_for("message", check=check, timeout=60)
        classes_input = classes_msg.content
        if classes_input.lower() == "all":
            classes = "All"
        else:
            classes = ", ".join([c.strip() for c in classes_input.split(",") if c.strip() in CLASSES])
    except:
        classes = "All"
    
    # Save to DB
    await add_item_db(item_name, item_type.value, item_subtype, stats, classes)
    await interaction.user.send(f"✅ Added **{item_name}** | {item_type.value}:{item_subtype} | Stats: {stats} | Usable by: {classes}")

# -------------------------------
# View Bank Command
# -------------------------------
@bot.tree.command(name="view_bank", description="View all items in the Guild Bank")
async def view_bank(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild Bank is empty.", ephemeral=True)
        return
    
    lines = []
    for row in rows:
        lines.append(f"{row['name']} | {row['type']}:{row['subtype']} | Stats: {row['stats']} | Usable by: {row['classes']}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

# -------------------------------
# Run Bot
# -------------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await init_db()
    try:
        await bot.tree.sync()
        print("Commands synced!")
    except Exception as e:
        print(e)

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
