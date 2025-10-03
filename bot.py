import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncpg

# -------------------------------
# Bot Setup
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

async def get_all_items():
    async with db_pool.acquire() as conn:
        return await conn.fetch('SELECT id, name, type, subtype, stats, classes FROM inventory ORDER BY name ASC')

async def remove_item_db(item_id):
    async with db_pool.acquire() as conn:
        await conn.execute('DELETE FROM inventory WHERE id=$1', item_id)

# -------------------------------
# Modal for Item Details
# -------------------------------
class ItemDetailsModal(discord.ui.Modal, title="Item Details"):
    name = discord.ui.TextInput(label="Item Name", required=True)
    attack = discord.ui.TextInput(label="Attack", required=False)
    delay = discord.ui.TextInput(label="Delay", required=False)
    defense = discord.ui.TextInput(label="Defense", required=False)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.item_name = self.name.value
        stats_list = []
        if self.attack.value or self.delay.value:
            stats_list.append(f"Attack: {self.attack.value} | Delay: {self.delay.value}")
        if self.defense.value:
            stats_list.append(f"Defense: {self.defense.value}")
        self.parent_view.stats = " | ".join(stats_list)
        await interaction.response.send_message("Item details saved.", ephemeral=True)

# -------------------------------
# Item Entry View with Drop-downs and Buttons
# -------------------------------
class ItemEntryView(discord.ui.View):
    def __init__(self, author, item_type=None, item_id=None):
        super().__init__(timeout=None)
        self.author = author
        self.item_type = item_type
        self.subtype = None
        self.usable_classes = []
        self.item_name = ""
        self.stats = ""
        self.item_id = item_id  # For editing

        # Subtype dropdown (single select)
        self.subtype_select = discord.ui.Select(
            placeholder="Select Subtype",
            min_values=1,
            max_values=1,
            options=[]
        )
        self.subtype_select.callback = self.select_subtype
        self.add_item(self.subtype_select)

        # Classes multi-select
        class_options = [discord.SelectOption(label="All")] + [discord.SelectOption(label=c) for c in CLASSES]
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

    # Only allow the original author to interact
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.author

    # Subtype selection
    async def select_subtype(self, interaction: discord.Interaction):
        self.subtype = interaction.values[0]  # store selection
        await interaction.response.edit_message(view=self)  # keep dropdowns active

    # Classes multi-select
    async def select_classes(self, interaction: discord.Interaction):
        selected = interaction.values
        if "All" in selected:
            self.usable_classes = ["All"]
        else:
            self.usable_classes = selected
        await interaction.response.edit_message(view=self)  # keep dropdowns active

    # Open modal for item name and stats
    async def open_item_details(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ItemDetailsModal(self))

    # Submit the item to the database
    async def submit_item(self, interaction: discord.Interaction):
        classes_str = ", ".join(self.usable_classes)
        if self.item_id:  # Editing existing item
            async with db_pool.acquire() as conn:
                await conn.execute('''
                    UPDATE inventory
                    SET name=$1, type=$2, subtype=$3, stats=$4, classes=$5, updated_at=NOW()
                    WHERE id=$6
                ''', self.item_name, self.item_type, self.subtype, self.stats, classes_str, self.item_id)
            await interaction.response.send_message(f"✅ Updated **{self.item_name}**.", ephemeral=True)
        else:  # New item
            await add_item_db(self.item_name, self.item_type, self.subtype, self.stats, classes_str)
            await interaction.response.send_message(f"✅ Added **{self.item_name}** to the Guild Bank.", ephemeral=True)
        self.stop()

    # Reset entry
    async def reset_entry(self, interaction: discord.Interaction):
        await interaction.response.send_message("Entry canceled and reset.", ephemeral=True)
        self.stop()



# -------------------------------
# Slash Commands
# -------------------------------
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
@app_commands.describe(item_type="Choose the item type")
@app_commands.choices(item_type=[app_commands.Choice(name=t, value=t) for t in ITEM_TYPES])
async def add_item(interaction: discord.Interaction, item_type: app_commands.Choice[str]):
    view = ItemEntryView(interaction.user, item_type.value)
    # Populate subtype options
    view.subtype_select.options = [discord.SelectOption(label=s) for s in SUBTYPES[item_type.value]]
    await interaction.response.send_message(f"Adding item of type **{item_type.value}**:", view=view, ephemeral=True)

@bot.tree.command(name="view_bank", description="View all items in the Guild Bank")
async def view_bank(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild Bank is empty.", ephemeral=True)
        return
    lines = [f"{row['name']} | {row['type']}:{row['subtype']} | Stats: {row['stats']} | Usable by: {row['classes']}" for row in rows]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@bot.tree.command(name="edit_item", description="Edit an existing item in the Guild Bank")
async def edit_item(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild Bank is empty.", ephemeral=True)
        return

    options = [discord.SelectOption(label=row["name"], value=str(row["id"])) for row in rows]

    class EditSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="Select item to edit", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            item_id = int(self.values[0])
            item = next(r for r in rows if r["id"] == item_id)
            view = ItemEntryView(interaction.user, item_type=item["type"], item_id=item_id)
            view.item_name = item["name"]
            view.subtype = item["subtype"]
            view.usable_classes = item["classes"].split(", ")
            view.stats = item["stats"]
            view.subtype_select.options = [discord.SelectOption(label=s) for s in SUBTYPES[item["type"]]]
            await interaction.response.edit_message(content=f"Editing **{item['name']}**:", view=view)

    class EditView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(EditSelect())

    await interaction.response.send_message("Select an item to edit:", view=EditView(), ephemeral=True)

@bot.tree.command(name="remove_item", description="Remove an item from the Guild Bank")
async def remove_item(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild Bank is empty.", ephemeral=True)
        return

    options = [discord.SelectOption(label=row["name"], value=str(row["id"])) for row in rows]

    class RemoveSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="Select item to remove", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            item_id = int(self.values[0])
            await remove_item_db(item_id)
            await interaction.response.send_message("✅ Item removed from Guild Bank.", ephemeral=True)
            self.view.stop()

    class RemoveView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(RemoveSelect())

    await interaction.response.send_message("Select an item to remove:", view=RemoveView(), ephemeral=True)

# -------------------------------
# Bot Ready Event
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

# -------------------------------
# Run Bot
# -------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)


