import discord
from discord.ext import commands
from discord import app_commands
import asyncpg
import os

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────── DB POOL ─────────────
db_pool: asyncpg.Pool = None

async def add_item_db(name, type_, subtype, stats, classes):
    async with db_pool.acquire() as conn:
        await conn.execute(
            '''
            INSERT INTO inventory (name, type, subtype, stats, classes)
            VALUES ($1, $2, $3, $4, $5)
            ''',
            name, type_, subtype, stats, classes
        )

# ─────────── CONFIG DATA ─────────────
ITEM_TYPES = ["Weapon", "Armor", "Consumable"]  # top-level types shown in /add_item

SUBTYPES = {
    "Weapon": ["Sword", "Axe", "Bow"],
    "Armor": ["Plate", "Leather", "Cloth"],
    "Consumable": ["Potion", "Food"],
}

CLASSES = ["Fighter", "Paladin", "Mage", "Rogue"]

# ─────────── UI COMPONENTS ─────────────
class SubtypeSelect(discord.ui.Select):
    def __init__(self, view):
        self.view_ref = view
        options = [
            discord.SelectOption(label=s, default=(s == view.subtype))
            for s in SUBTYPES.get(view.item_type, [])
        ]
        super().__init__(
            placeholder="Select Subtype",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.subtype = self.values[0]
        self.options = [
            discord.SelectOption(label=s, default=(s == self.view_ref.subtype))
            for s in SUBTYPES.get(self.view_ref.item_type, [])
        ]
        await interaction.response.edit_message(view=self.view_ref)


class ClassesSelect(discord.ui.Select):
    def __init__(self, view):
        self.view_ref = view
        options = [
            discord.SelectOption(label=c, default=(c in view.usable_classes))
            for c in ["All"] + CLASSES
        ]
        super().__init__(
            placeholder="Select Usable Classes",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if "All" in self.values:
            self.view_ref.usable_classes = ["All"]
        else:
            self.view_ref.usable_classes = self.values
        self.options = [
            discord.SelectOption(label=c, default=(c in self.view_ref.usable_classes))
            for c in ["All"] + CLASSES
        ]
        await interaction.response.edit_message(view=self.view_ref)


class ItemDetailsModal(discord.ui.Modal, title="Item Details"):
    item_name = discord.ui.TextInput(label="Item Name", placeholder="Enter item name")
    stats = discord.ui.TextInput(label="Stats", placeholder="Example: Attack:10, Delay:2")

    def __init__(self, view):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.item_name = self.item_name.value
        self.view_ref.stats = self.stats.value
        await interaction.response.send_message("✅ Details saved.", ephemeral=True)


class ItemEntryView(discord.ui.View):
    def __init__(self, author, item_type=None, item_id=None):
        super().__init__(timeout=None)
        self.author = author
        self.item_type = item_type
        self.subtype = None
        self.usable_classes = []
        self.item_name = ""
        self.stats = ""
        self.item_id = item_id

        self.subtype_select = SubtypeSelect(self)
        self.add_item(self.subtype_select)

        self.classes_select = ClassesSelect(self)
        self.add_item(self.classes_select)

        self.details_button = discord.ui.Button(label="Item Details", style=discord.ButtonStyle.secondary)
        self.details_button.callback = self.open_item_details
        self.add_item(self.details_button)

        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.success)
        self.submit_button.callback = self.submit_item
        self.add_item(self.submit_button)

        self.reset_button = discord.ui.Button(label="Reset", style=discord.ButtonStyle.danger)
        self.reset_button.callback = self.reset_entry
        self.add_item(self.reset_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    async def open_item_details(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ItemDetailsModal(self))

    async def submit_item(self, interaction: discord.Interaction):
        classes_str = ", ".join(self.usable_classes)
        await add_item_db(self.item_name, self.item_type, self.subtype, self.stats, classes_str)
        await interaction.response.send_message(f"✅ Added **{self.item_name}** to the Guild Bank.", ephemeral=True)
        self.stop()

    async def reset_entry(self, interaction: discord.Interaction):
        self.subtype = None
        self.usable_classes = []
        self.item_name = ""
        self.stats = ""
        await interaction.response.send_message("Entry canceled and reset.", ephemeral=True)
        self.stop()

# ─────────── COMMANDS ─────────────
@bot.tree.command(name="add_item", description="Add an item to the guild bank.")
@app_commands.describe(item_type="Select the type of item")
@app_commands.choices(item_type=[app_commands.Choice(name=t, value=t) for t in ITEM_TYPES])
async def add_item(interaction: discord.Interaction, item_type: app_commands.Choice[str]):
    chosen_type = item_type.value
    view = ItemEntryView(interaction.user, item_type=chosen_type)
    await interaction.response.send_message("Fill out the item details:", view=view, ephemeral=True)

@bot.tree.command(name="view_bank", description="View all items in the guild bank.")
async def view_bank(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, type, subtype, stats, classes FROM inventory")
    if not rows:
        await interaction.response.send_message("The bank is empty.", ephemeral=True)
        return
    msg = ""
    for r in rows:
        msg += f"**{r['name']}** | {r['type']}: {r['subtype']} | Stats: {r['stats']} | Usable by: {r['classes']}\n"
    await interaction.response.send_message(msg, ephemeral=True)

# ─────────── SETUP ─────────────
@bot.event
async def on_ready():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    await bot.tree.sync()
    print(f"Logged in as {bot.user} and synced {len(bot.tree.get_commands())} commands.")

bot.run(TOKEN)
