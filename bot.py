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

        if self.parent_view.item_type == "Weapon":
            options = [discord.SelectOption(label=s) for s in WEAPON_SUBTYPES]
        elif self.parent_view.item_type == "Armor":
            options = [discord.SelectOption(label=s) for s in ARMOR_SUBTYPES]
        elif self.parent_view.item_type == "Consumable":
            options = [discord.SelectOption(label=s) for s in CONSUMABLE_SUBTYPES]
        else:
            options = [discord.SelectOption(label=s) for s in MISC_SUBTYPES]

        # ✅ Mark selected subtype as default
        for opt in options:
            if opt.label == self.parent_view.subtype:
                opt.default = True

        super().__init__(placeholder="Select Subtype", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.subtype = self.values[0]
        # update which option is default so it stays highlighted
        for opt in self.options:
            opt.default = (opt.label == self.values[0])
        await interaction.response.edit_message(view=self.parent_view)
        

class ClassesSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view

        # Always show all options
        options = [discord.SelectOption(label="All")] + [discord.SelectOption(label=c) for c in CLASS_OPTIONS]

        super().__init__(
            placeholder="Select usable classes (multi)",
            options=options,
            min_values=0,
            max_values=len(options)
        )

        # Preselect current classes
        if self.parent_view.usable_classes:
            self.default = True

    async def callback(self, interaction: discord.Interaction):
        # If All is selected, ignore other selections
        if "All" in self.values:
            self.view.usable_classes = ["All"]
        else:
            # If other classes selected while All is in previous selection, remove All
            self.view.usable_classes = self.values

        # Update the dropdown so selections are visible
        for option in self.options:
            option.default = option.label in self.view.usable_classes

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

# ---------- Read-Only Modal ----------
class ReadOnlyDetailsModal(discord.ui.Modal):
    def __init__(self, item_row):
        super().__init__(title=title_text)

        
        # Hard text display (read-only)
        self.type_field = discord.ui.TextInput(
            label="Type | Subtype",
            style=discord.TextStyle.short,
            default=f"{item_row['type']} | {item_row['subtype']}",
            required=False
        )
        self.type_field.disabled = True
        self.add_item(self.type_field)

        # Read-only field for Stats
        self.stats_field = discord.ui.TextInput(
            label="Stats",
            style=discord.TextStyle.paragraph,
            default=item_row['stats'],
            required=False
        )
        self.stats_field.disabled = True
        self.add_item(self.stats_field)

        # Read-only field for Classes
        self.classes_field = discord.ui.TextInput(
            label="Classes",
            style=discord.TextStyle.short,
            default=item_row['classes'],
            required=False
        )
        self.classes_field.disabled = True
        self.add_item(self.classes_field)

        # Single-line input field at bottom (does nothing)
        self.fake_input = discord.ui.TextInput(
            label="Input (ignored)", 
            style=discord.TextStyle.short,
            required=False,
            placeholder="Type here if you want...",
            max_length=100
        )
        self.add_item(self.fake_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Just close the modal; no need to process input
        await interaction.response.send_message("✅ Closed.", ephemeral=True)


# ---------- Button ----------
class ViewDetailsButton(discord.ui.Button):
    def __init__(self, item_row):
        super().__init__(label="View Details", style=discord.ButtonStyle.secondary)
        self.item_row = item_row  # store the DB row

    async def callback(self, interaction: discord.Interaction):
        if not self.item_row:
            await interaction.response.send_message("Error: no data available.", ephemeral=True)
            return

        details_text = (
            f"Type: {self.item_row['type']} | Subtype: {self.item_row['subtype']}\n"
            f"Classes: {self.item_row['classes']}\n"
            f"Stats:\n{self.item_row['stats']}"
        )
        modal = ReadOnlyDetailsModal(item_row1=self.item_row)
        await interaction.response.send_modal(modal)

# ---------- /view_bank Command ----------
@bot.tree.command(name="view_bank", description="View all items in the guild bank.")
async def view_bank(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild bank is empty.", ephemeral=True)
        return

    # Sort items alphabetically
    sorted_rows = sorted(rows, key=lambda r: r['name'].lower())

    # Send one message per item
    for row in sorted_rows:
        embed = discord.Embed(
            title=row["name"],
            description=f"{row['type']} | {row['subtype']}",
            color=discord.Color.blue()
        )
        view = discord.ui.View()
        view.add_item(ViewDetailsButton(item_row=row))

        await interaction.channel.send(embed=embed, view=view)
    
    # Optionally, acknowledge the command ephemerally
    await interaction.response.send_message(f"✅ Sent {len(sorted_rows)} items.", ephemeral=True)



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

import asyncio



@bot.event
async def on_ready():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)





