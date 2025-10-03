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

async def update_item_db(item_id, name, type_, subtype, stats, classes):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE inventory
            SET name=$1, type=$2, subtype=$3, stats=$4, classes=$5, updated_at=NOW()
            WHERE id=$6
        ''', name, type_, subtype, stats, classes, item_id)

async def remove_item_db(item_id):
    async with db_pool.acquire() as conn:
        await conn.execute('DELETE FROM inventory WHERE id=$1', item_id)

async def get_all_items():
    async with db_pool.acquire() as conn:
        return await conn.fetch('SELECT id, name, type, subtype, stats, classes FROM inventory ORDER BY name ASC')

async def get_item_by_name(name):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow('SELECT id, name, type, subtype, stats, classes FROM inventory WHERE name=$1', name)

# -------------------------------
# Modal: Item Details
# -------------------------------
class ItemDetailsModal(discord.ui.Modal, title="Enter Item Details"):
    name = discord.ui.TextInput(label="Item Name", placeholder="e.g. BP", required=True)
    attack = discord.ui.TextInput(label="Attack", required=False)
    delay = discord.ui.TextInput(label="Delay", required=False)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.item_name = self.name.value
        self.parent_view.stats = f"Attack: {self.attack.value} | Delay: {self.delay.value}"
        await interaction.response.send_message("Item details saved.", ephemeral=True)

# -------------------------------
# View: Item Entry
# -------------------------------
class ItemEntryView(discord.ui.View):
    def __init__(self, author, item_type, existing_item=None):
        super().__init__(timeout=None)
        self.author = author
        self.item_type = item_type
        self.subtype = existing_item["subtype"] if existing_item else None
        self.usable_classes = existing_item["classes"].split(", ") if existing_item else []
        self.item_name = existing_item["name"] if existing_item else ""
        self.stats = existing_item["stats"] if existing_item else ""
        self.item_id = existing_item["id"] if existing_item else None

        # Subtype select
        options = [discord.SelectOption(label=o, default=(o==self.subtype)) for o in SUBTYPES.get(self.item_type, ["None"])]
        self.subtype_select = discord.ui.Select(
            placeholder="Select Subtype",
            min_values=1, max_values=1,
            options=options
        )
        self.subtype_select.callback = self.select_subtype
        self.add_item(self.subtype_select)

        # Classes multi-select + All
        class_options = [discord.SelectOption(label="All", default=("All" in self.usable_classes))] + \
                        [discord.SelectOption(label=c, default=(c in self.usable_classes)) for c in CLASSES]
        self.classes_select = discord.ui.Select(
            placeholder="Select Usable Classes",
            min_values=1,
            max_values=len(class_options),
            options=class_options
        )
        self.classes_select.callback = self.select_classes
        self.add_item(self.classes_select)

        # Buttons
        self.details_button = discord.ui.Button(label="Add Item Details", style=discord.ButtonStyle.secondary)
        self.details_button.callback = self.open_item_details
        self.add_item(self.details_button)

        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.success)
        self.submit_button.callback = self.submit_item
        self.add_item(self.submit_button)

        self.reset_button = discord.ui.Button(label="Reset", style=discord.ButtonStyle.danger)
        self.reset_button.callback = self.reset_entry
        self.add_item(self.reset_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("You can't edit this entry.", ephemeral=True)
            return False
        return True

    async def select_subtype(self, interaction: discord.Interaction):
        self.subtype = interaction.data["values"][0]
        for option in self.subtype_select.options:
            option.default = option.label == self.subtype
        await interaction.response.edit_message(view=self)

    async def select_classes(self, interaction: discord.Interaction):
        selected = interaction.data["values"]
        if "All" in selected:
            self.usable_classes = ["All"]
            options = [discord.SelectOption(label="All", default=True)] + [discord.SelectOption(label=c) for c in CLASSES]
            self.classes_select.options = options
        else:
            self.usable_classes = selected
            for option in self.classes_select.options:
                option.default = option.label in self.usable_classes
        await interaction.response.edit_message(view=self)

    async def open_item_details(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ItemDetailsModal(self))

    async def submit_item(self, interaction: discord.Interaction):
        classes_str = ", ".join(self.usable_classes)
        if self.item_id:
            await update_item_db(self.item_id, self.item_name, self.item_type, self.subtype, self.stats, classes_str)
            msg = f"Item **{self.item_name}** updated in the Guild Bank."
        else:
            await add_item_db(self.item_name, self.item_type, self.subtype, self.stats, classes_str)
            msg = f"Item **{self.item_name}** added to the Guild Bank."
        await interaction.response.send_message(msg, ephemeral=True)
        self.stop()

    async def reset_entry(self, interaction: discord.Interaction):
        await interaction.response.send_message("Entry reset and canceled.", ephemeral=True)
        self.stop()

# -------------------------------
# Commands
# -------------------------------
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
@app_commands.describe(item_type="Choose the item type")
@app_commands.choices(item_type=[app_commands.Choice(name=t, value=t) for t in ITEM_TYPES])
async def add_item(interaction: discord.Interaction, item_type: app_commands.Choice[str]):
    view = ItemEntryView(interaction.user, item_type.value)
    await interaction.response.send_message(
        f"Fill in the item details for **{item_type.value}** below:",
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="view_bank", description="View all items in the Guild Bank")
async def view_bank(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild Bank is empty.", ephemeral=True)
        return

    lines = []
    for row in rows:
        classes = row["classes"]
        lines.append(f"{row['name']} | {row['type']}:{row['subtype']} | Stats: {row['stats']} | Usable by: {classes}")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@bot.tree.command(name="remove_item", description="Remove an item from the Guild Bank")
@app_commands.describe(item_name="Name of the item to remove")
async def remove_item(interaction: discord.Interaction, item_name: str):
    row = await get_item_by_name(item_name)
    if not row:
        await interaction.response.send_message("Item not found.", ephemeral=True)
        return
    await remove_item_db(row["id"])
    await interaction.response.send_message(f"Removed **{item_name}** from the Guild Bank.", ephemeral=True)

@bot.tree.command(name="edit_item", description="Edit an existing item in the Guild Bank")
@app_commands.describe(item_name="Name of the item to edit")
async def edit_item(interaction: discord.Interaction, item_name: str):
    row = await get_item_by_name(item_name)
    if not row:
        await interaction.response.send_message("Item not found.", ephemeral=True)
        return
    existing_item = {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "subtype": row["subtype"],
        "stats": row["stats"],
        "classes": row["classes"]
    }
    view = ItemEntryView(interaction.user, existing_item["type"], existing_item=existing_item)
    await interaction.response.send_message(f"Editing item **{item_name}**:", view=view, ephemeral=True)

# -------------------------------
# Events
# -------------------------------
@bot.event
async def on_ready():
    global db_pool
    print(f"Logged in as {bot.user}")
    await init_db()  # Connect to PostgreSQL
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

# -------------------------------
# Run Bot
# -------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
