import os
import discord
from discord import app_commands
from discord.ext import commands
import asyncpg

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ITEM_TYPES = ["Weapon", "Armor", "Consumable", "Misc"]
WEAPON_SUBTYPES = ["Axe", "Battle Axe", "Bow", "Dagger", "Great Scythe", "Great Sword", "Long Sword", "Mace", "Maul", "Scimitar", "Scythe", "Short Sword", "Spear", "Trident", "Warhammer" ]
ARMOR_SUBTYPES = ["Chain", "Cloth", "Leather", "Plate", "Shield"]
CONSUMABLE_SUBTYPES = ["Drink", "Food", "Potion", "Scroll"]
MISC_SUBTYPES = ["Quest Item", "Material"]

CLASS_OPTIONS = ["Archer", "Bard", "Beastmaster", "Cleric", "Druid", "Elementalist", "Enchanter", "Fighter", "Inquisitor", "Monk", "Necromancer", "Paladin", "Ranger", "Rogue", "Shadow Knight", "Shaman", "Spellblade", "Wizard"]

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
db_pool: asyncpg.Pool = None

# ---------- DB Helpers ----------

async def add_item_db(name, type_, subtype, stats, classes):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO inventory (name, type, subtype, stats, classes)
            VALUES ($1, $2, $3, $4, $5)
        ''', name, type_, subtype, stats, classes)

async def get_all_items():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, type, subtype, stats, classes FROM inventory ORDER BY id")
    return rows

async def get_item_by_name(name):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM inventory WHERE name=$1", name)
    return row

async def update_item_db(id_, name, type_, subtype, stats, classes):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE inventory
            SET name=$1, type=$2, subtype=$3, stats=$4, classes=$5
            WHERE id=$6
        ''', name, type_, subtype, stats, classes, id_)

async def delete_item_db(id_):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM inventory WHERE id=$1", id_)

# ---------- UI Components ----------

class SubtypeSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = []
        if self.parent_view.item_type == "Weapon":
            options = [discord.SelectOption(label=s) for s in WEAPON_SUBTYPES]
        elif self.parent_view.item_type == "Armor":
            options = [discord.SelectOption(label=s) for s in ARMOR_SUBTYPES]
        elif self.parent_view.item_type == "Consumable":
            options = [discord.SelectOption(label=s) for s in CONSUMABLE_SUBTYPES]
        else:
            options = [discord.SelectOption(label=s) for s in MISC_SUBTYPES]

        # preselect if editing
        super().__init__(placeholder="Select Subtype", options=options)
        if self.parent_view.subtype:
            self.default = True

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.subtype = self.values[0]
        await interaction.response.defer()

class ClassesSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view
        options = []

        # Decide what to show in the dropdown
        if self.parent_view.usable_classes == ["All"]:
            options = [discord.SelectOption(label="All")]
        else:
            options = [discord.SelectOption(label=c) for c in CLASS_OPTIONS]

        super().__init__(
            placeholder="Select usable classes (multi)",
            options=options,
            min_values=0,
            max_values=len(options)
        )

        # Pre-select currently stored classes if not empty
        if self.parent_view.usable_classes:
            self.default = True

    async def callback(self, interaction: discord.Interaction):
        # If All selected, store only All
        if "All" in self.values:
            self.view.usable_classes = ["All"]
        else:
            self.view.usable_classes = self.values

        # Update dropdown options dynamically for next view
        self.options.clear()
        if self.view.usable_classes == ["All"]:
            self.options.append(discord.SelectOption(label="All"))
        else:
            for c in CLASS_OPTIONS:
                self.options.append(discord.SelectOption(label=c))

        await interaction.response.edit_message(view=self.view)



class ItemEntryView(discord.ui.View):
    def __init__(self, author, item_type=None, item_id=None, existing_data=None):
        super().__init__(timeout=None)
        self.author = author
        self.item_type = item_type
        self.subtype = None
        self.usable_classes = []
        self.item_name = ""
        self.stats = ""
        self.item_id = item_id

        # preload existing if editing
        if existing_data:
            self.item_name = existing_data['name']
            self.item_type = existing_data['type']
            self.subtype = existing_data['subtype']
            self.stats = existing_data['stats']
            self.usable_classes = existing_data['classes'].split(", ") if existing_data['classes'] else []

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
        modal = ItemDetailsModal(self)
        await interaction.response.send_modal(modal)

    async def submit_item(self, interaction: discord.Interaction):
        classes_str = ", ".join(self.usable_classes)
        if self.item_id:  # editing
            await update_item_db(self.item_id, self.item_name, self.item_type, self.subtype, self.stats, classes_str)
            await interaction.response.send_message(f"✅ Updated **{self.item_name}**.", ephemeral=True)
        else:  # adding
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


# ------ITEM DETAILS ----

class ItemDetailsModal(discord.ui.Modal, title="Item Details"):
    def __init__(self, view: ItemEntryView):
        super().__init__(title=f"{view.item_type} Details")
        self.view = view

        # The modal changes depending on the item type
        if view.item_type == "Weapon":
            self.item_name = discord.ui.TextInput(label="Item Name", default=view.item_name, required=True)
            self.attack = discord.ui.TextInput(label="Attack", default="", required=True)
            self.delay = discord.ui.TextInput(label="Delay", default="", required=True)
            self.add_item(self.item_name)
            self.add_item(self.attack)
            self.add_item(self.delay)

        elif view.item_type == "Armor":
            self.item_name = discord.ui.TextInput(label="Item Name", default=view.item_name, required=True)
            self.armor_class = discord.ui.TextInput(label="Armor Class", default="", required=True)
            self.add_item(self.item_name)
            self.add_item(self.armor_class)

        elif view.item_type == "Potion":
            self.item_name = discord.ui.TextInput(label="Item Name", default=view.item_name, required=True)
            self.effect = discord.ui.TextInput(label="Effect", default="", required=True)
            self.duration = discord.ui.TextInput(label="Duration", default="", required=False)
            self.add_item(self.item_name)
            self.add_item(self.effect)
            self.add_item(self.duration)

        else:  # fallback generic modal
            self.item_name = discord.ui.TextInput(label="Item Name", default=view.item_name, required=True)
            self.stats = discord.ui.TextInput(label="Stats", default=view.stats, style=discord.TextStyle.paragraph)
            self.add_item(self.item_name)
            self.add_item(self.stats)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.item_name = self.item_name.value

        # Save stats depending on type
        if self.view.item_type == "Weapon":
            self.view.stats = f"Attack: {self.attack.value}, Delay: {self.delay.value}"
        elif self.view.item_type == "Armor":
            self.view.stats = f"Armor Class: {self.armor_class.value}"
        elif self.view.item_type == "Potion":
            dur = f", Duration: {self.duration.value}" if self.duration.value else ""
            self.view.stats = f"Effect: {self.effect.value}{dur}"
        else:
            self.view.stats = self.stats.value

        await interaction.response.send_message("✅ Details saved. Click Submit when ready.", ephemeral=True)


# ----------

# ---------- Commands ----------

@bot.event
async def on_ready():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="add_item", description="Add a new item to the guild bank.")
@app_commands.describe(item_type="Type of the item")
@app_commands.choices(item_type=[app_commands.Choice(name=t, value=t) for t in ITEM_TYPES])
async def add_item(interaction: discord.Interaction, item_type: app_commands.Choice[str]):
    view = ItemEntryView(interaction.user, item_type=item_type.value)
    await interaction.response.send_message(f"Adding a new {item_type.value}:", view=view, ephemeral=True)

#-------VIEW BANK --------

@bot.tree.command(name="view_bank", description="View all items in the guild bank.")
async def view_bank(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild bank is empty.", ephemeral=True)
        return

    # Sort items alphabetically by name
    sorted_rows = sorted(rows, key=lambda r: r['name'].lower())

    embed = discord.Embed(title="Guild Bank", color=discord.Color.blue())
    for row in sorted_rows:
        # Sort classes alphabetically
        classes_list = row['classes'].split(", ") if row['classes'] else []
        classes_sorted = ", ".join(sorted(classes_list))

        embed.add_field(
            name=row["name"],
            value=(
                f"Type: {row['type']} | Subtype: {row['subtype']} | Classes: {classes_sorted}\n"
                f"  Stats: {row['stats']}"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

#----------


@bot.tree.command(name="edit_item", description="Edit an existing item in the guild bank.")
@app_commands.describe(item_name="Name of the item to edit")
async def edit_item(interaction: discord.Interaction, item_name: str):
    item = await get_item_by_name(item_name)
    if not item:
        await interaction.response.send_message("Item not found.", ephemeral=True)
        return
    view = ItemEntryView(interaction.user, item_type=item['type'], item_id=item['id'], existing_data=item)
    await interaction.response.send_message(f"Editing **{item_name}**:", view=view, ephemeral=True)

@bot.tree.command(name="remove_item", description="Remove an item from the guild bank.")
@app_commands.describe(item_name="Name of the item to remove")
async def remove_item(interaction: discord.Interaction, item_name: str):
    item = await get_item_by_name(item_name)
    if not item:
        await interaction.response.send_message("Item not found.", ephemeral=True)
        return
    await delete_item_db(item['id'])
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}** from the Guild Bank.", ephemeral=True)

bot.run(TOKEN)










