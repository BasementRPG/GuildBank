import os
import discord
from discord.ext import commands
import asyncpg

TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

ITEM_TYPES = ["Weapon", "Armor", "Potion", "Misc"]
CLASSES = ["Warrior", "Mage", "Rogue", "Cleric"]

db_conn = None  # Will be initialized in on_ready

# ---------------- VIEW FOR DROPDOWNS ----------------
class AddItemView(discord.ui.View):
    def __init__(self, item_name, author):
        super().__init__(timeout=60)
        self.item_name = item_name
        self.author = author
        self.item_type = None
        self.item_class = None

    @discord.ui.select(
        placeholder="Choose Item Type",
        options=[discord.SelectOption(label=t) for t in ITEM_TYPES],
        custom_id="select_type"
    )
    async def select_type(self, select, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("This is not your selection!", ephemeral=True)
        self.item_type = select.values[0]
        await interaction.response.send_message(f"Item type selected: {self.item_type}", ephemeral=True)
        await self.check_complete(interaction)

    @discord.ui.select(
        placeholder="Choose Class",
        options=[discord.SelectOption(label=c) for c in CLASSES],
        custom_id="select_class"
    )
    async def select_class(self, select, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("This is not your selection!", ephemeral=True)
        self.item_class = select.values[0]
        await interaction.response.send_message(f"Class selected: {self.item_class}", ephemeral=True)
        await self.check_complete(interaction)

    async def check_complete(self, interaction):
        if self.item_type and self.item_class:
            # Save to database as bot-owned item
            await db_conn.execute(
                "INSERT INTO inventory(item_name,item_type,item_class,photo_url) VALUES($1,$2,$3,$4)",
                self.item_name, self.item_type, self.item_class, None
            )
            # Disable dropdowns
            for child in self.children:
                child.disabled = True
            await interaction.followup.send(
                f"✅ Added **{self.item_name}** ({self.item_type} - {self.item_class}) to the bot's inventory.",
                ephemeral=True
            )
            self.stop()

# ---------------- COMMANDS ----------------
@bot.tree.command(name="add_item", description="Add an item to the bot's inventory")
async def add_item(interaction: discord.Interaction, name: str):
    view = AddItemView(name, interaction.user)
    await interaction.response.send_message(f"Adding item: **{name}**. Choose type and class:", view=view, ephemeral=True)

@bot.tree.command(name="view_items", description="View the bot's inventory")
async def view_items(interaction: discord.Interaction):
    rows = await db_conn.fetch(
        "SELECT item_name,item_type,item_class FROM inventory"
    )
    if not rows:
        await interaction.response.send_message("The bot's inventory is empty.", ephemeral=True)
        return
    desc = "\n".join([f"- {r['item_name']} ({r['item_type']} - {r['item_class']})" for r in rows])
    embed = discord.Embed(title=f"Bot Inventory", description=desc)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete_item", description="Delete an item from the bot's inventory")
async def delete_item(interaction: discord.Interaction, item_name: str):
    await db_conn.execute(
        "DELETE FROM inventory WHERE item_name=$1",
        item_name
    )
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}** from the bot's inventory.", ephemeral=True)

@bot.tree.command(name="update_item", description="Update an item in the bot's inventory")
async def update_item(interaction: discord.Interaction, old_name: str, new_name: str, new_type: str, new_class: str):
    if new_type not in ITEM_TYPES or new_class not in CLASSES:
        await interaction.response.send_message("Invalid type or class.", ephemeral=True)
        return
    await db_conn.execute(
        """UPDATE inventory
           SET item_name=$1, item_type=$2, item_class=$3
           WHERE item_name=$4""",
        new_name, new_type, new_class, old_name
    )
    await interaction.response.send_message(f"🔄 Updated **{old_name}** to **{new_name}** in the bot's inventory.", ephemeral=True)

# ---------------- READY EVENT ----------------
@bot.event
async def on_ready():
    global db_conn
    if db_conn is None:
        db_conn = await asyncpg.connect(DATABASE_URL)
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                item_name TEXT,
                item_type TEXT,
                item_class TEXT,
                photo_url TEXT
            )
        """)
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
