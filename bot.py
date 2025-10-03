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

# ---------------- ITEM ADD VIEW ----------------
class AddItemView(discord.ui.View):
    def __init__(self, name):
        super().__init__(timeout=60)  # User has 60s to interact
        self.name = name
        self.type_selected = None
        self.class_selected = None

    @discord.ui.select(
        placeholder="Choose Item Type",
        options=[discord.SelectOption(label=t) for t in ITEM_TYPES]
    )
    async def select_type(self, select, interaction: discord.Interaction):
        self.type_selected = select.values[0]
        await interaction.response.send_message(f"Item type selected: {self.type_selected}", ephemeral=True)
        self.check_complete(interaction)

    @discord.ui.select(
        placeholder="Choose Class",
        options=[discord.SelectOption(label=c) for c in CLASSES]
    )
    async def select_class(self, select, interaction: discord.Interaction):
        self.class_selected = select.values[0]
        await interaction.response.send_message(f"Class selected: {self.class_selected}", ephemeral=True)
        self.check_complete(interaction)

    def check_complete(self, interaction):
        if self.type_selected and self.class_selected:
            # Save to database
            async def save():
                await db_conn.execute(
                    "INSERT INTO inventory(user_id,item_name,item_type,item_class,photo_url) VALUES($1,$2,$3,$4,$5)",
                    str(interaction.user.id), self.name, self.type_selected, self.class_selected, None
                )
            bot.loop.create_task(save())
            # Disable view
            for child in self.children:
                child.disabled = True
            bot.loop.create_task(interaction.followup.send(f"✅ Added **{self.name}** ({self.type_selected} - {self.class_selected}) to your inventory.", ephemeral=True))
            self.stop()

# ---------------- COMMANDS ----------------
@bot.tree.command(name="add_item", description="Add an item to your inventory")
async def add_item(interaction: discord.Interaction, name: str):
    """Starts a dropdown interaction to select type and class."""
    view = AddItemView(name)
    await interaction.response.send_message(f"Adding item: **{name}**. Choose type and class:", view=view, ephemeral=True)

@bot.tree.command(name="view_items", description="View your inventory")
async def view_items(interaction: discord.Interaction):
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
    await db_conn.execute(
        "DELETE FROM inventory WHERE user_id=$1 AND item_name=$2",
        str(interaction.user.id), item_name
    )
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}**.", ephemeral=True)

@bot.tree.command(name="update_item", description="Update an item")
async def update_item(interaction: discord.Interaction, old_name: str, new_name: str, new_type: str, new_class: str):
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
