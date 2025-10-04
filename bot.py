import os
import discord
from discord import app_commands
from discord.ext import commands
import asyncpg

print("discord.py version:", discord.__version__)


TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ITEM_TYPES = ["Armor", "Crafting", "Consumable", "Misc", "Weapon"]
WEAPON_SUBTYPES = ["Axe", "Battle Axe", "Bow", "Dagger", "Great Scythe", "Great Sword", "Long Sword", "Mace", "Maul", "Scimitar", "Scythe", "Short Sword", "Spear", "Trident", "Warhammer" ]
ARMOR_SUBTYPES = ["Chain", "Cloth", "Leather", "Plate", "Shield"]
CONSUMABLE_SUBTYPES = ["Drink", "Food", "Other", "Potion", "Scroll"]
CRAFTING_SUBTYPES = ["Unknown", "Raw", "Refined"]
MISC_SUBTYPES = ["Quest Item", "Unknown"]

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
        
        # Add debugging
        print(f"DEBUG: SubtypeSelect init - item_type: {self.parent_view.item_type}")
        
        # Add safety check
        if not self.parent_view.item_type:
            print("ERROR: item_type is None!")
            options = [discord.SelectOption(label="Error", value="error")]
        elif self.parent_view.item_type == "Weapon":
            options = [discord.SelectOption(label=s, value=s) for s in WEAPON_SUBTYPES]
        elif self.parent_view.item_type == "Armor":
            options = [discord.SelectOption(label=s, value=s) for s in ARMOR_SUBTYPES]
        elif self.parent_view.item_type == "Crafting":
            options = [discord.SelectOption(label=s, value=s) for s in CRAFTING_SUBTYPES]
        elif self.parent_view.item_type == "Consumable":
            options = [discord.SelectOption(label=s, value=s) for s in CONSUMABLE_SUBTYPES]
        else:
            options = [discord.SelectOption(label=s, value=s) for s in MISC_SUBTYPES]

        # ✅ Mark selected subtype as default
        for opt in options:
            if opt.label == self.parent_view.subtype:
                opt.default = True

        super().__init__(placeholder="Select Subtype", options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            print(f"DEBUG: SubtypeSelect callback - values: {self.values}")
            self.parent_view.subtype = self.values[0]
            # update which option is default so it stays highlighted
            for opt in self.options:
                opt.default = (opt.label == self.values[0])
            await interaction.response.edit_message(view=self.parent_view)
        except Exception as e:
            print(f"ERROR in SubtypeSelect callback: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
            except:
                pass

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

class ItemDetailsModal(discord.ui.Modal):
    def __init__(self, view: ItemEntryView):
        super().__init__(title=f"{view.item_type} Details")
        self.view = view

        if view.item_type == "Weapon":
            # Required fields
            self.item_name = discord.ui.TextInput(label="Item Name", default=view.item_name, placeholder="Example: Short Sword of the Ykesha", required=True)
            self.attack_delay = discord.ui.TextInput(label="Attack / Delay", default="", placeholder="Format: Attack/Delay | Example: 8/24" , required=True)
           
            # Optional fields
            self.attributes = discord.ui.TextInput(
                label="Stats", default="", placeholder="Example: +3 str, -1 cha, +5 sv fire", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default="", placeholder="Example: Ykesha: briefly stun and cause 75 dmg - lvl 37", required=False, style=discord.TextStyle.paragraph
            )

            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.attack_delay)
            self.add_item(self.attributes)
            self.add_item(self.effects)

        elif view.item_type == "Armor":
            self.item_name = discord.ui.TextInput(label="Item Name", placeholder="Example: Fungus Covered Scale Tunic", default=view.item_name, required=True)
            self.armor_class = discord.ui.TextInput(label="Armor Class", default="", placeholder="Example: 21", required=True)
            
           
            # Optional fields
            self.attributes = discord.ui.TextInput(
                label="Stats", default="", placeholder="Example: +2 str, -10 dex, +2 int, -10 int ", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default="", placeholder="Example: +15 HP Regen", required=False, style=discord.TextStyle.paragraph
            )

            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.armor_class)
            self.add_item(self.attributes)
            self.add_item(self.effects)
            
        elif view.item_type == "Crafting":
            self.item_name = discord.ui.TextInput(label="Item Name", placeholder="Example: Cloth Scraps", default=view.item_name, required=True)
            self.info = discord.ui.TextInput(label="Info", default="", placeholder="Example: Used primarily for tailor and sub-compoints for other tradeskills", required=False)
            

            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.info)

        elif view.item_type == "Consumable":
            self.item_name = discord.ui.TextInput(label="Item Name", placeholder="Example: Dinner Gift Basket", default=view.item_name, required=True)
                    
           
            # Optional fields
            self.attributes = discord.ui.TextInput(
                label="Stats", default="", placeholder="Example: +5 str, +5 dex, +5 sta, + 5 agi, +30 hp, +30 mana ", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default="", placeholder="Example: This is a miraculous meal", required=False, style=discord.TextStyle.paragraph
            )

            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.attributes)
            self.add_item(self.effects)

        else:
            self.item_name = discord.ui.TextInput(label="Item Name", default=view.item_name, required=True)
            self.stats = discord.ui.TextInput(
                label="Stats", default=view.stats, style=discord.TextStyle.paragraph
            )
            self.add_item(self.item_name)
            self.add_item(self.stats)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.item_name = self.item_name.value
    
        if self.view.item_type == "Weapon":
            # Start with Attack/Delay
            stats_parts = [f"Attack/Delay: {self.attack_delay.value}"]
    
            # Add optional fields if filled
            if self.attributes.value.strip():
                stats_parts.append(f"Stats: {self.attributes.value.strip()}")
            if self.effects.value.strip():
                stats_parts.append(f"Effects: {self.effects.value.strip()}")
    
            # Combine into one stats string
            self.view.stats = "\n  ".join(stats_parts)
    
        elif self.view.item_type == "Armor":
            self.view.stats = f"Armor Class: {self.armor_class.value}"
            
            # Add optional fields if filled
            if self.attributes.value.strip():
                stats_parts.append(f"Stats: {self.attributes.value.strip()}")
            if self.effects.value.strip():
                stats_parts.append(f"Effects: {self.effects.value.strip()}")
    
            # Combine into one stats string
            self.view.stats = "\n  ".join(stats_parts)

        
        elif self.view.item_type == "Crafting":
            self.view.stats = f"Info: {self.info.value}"

        elif self.view.item_type == "Consumable":
            
            # Add optional fields if filled
            if self.attributes.value.strip():
                stats_parts.append(f"Stats: {self.attributes.value.strip()}")
            if self.effects.value.strip():
                stats_parts.append(f"Effects: {self.effects.value.strip()}")
            if stats_parts == null():
               stats_parts = [f" "]
            # Combine into one stats string
            self.view.stats = "\n  ".join(stats_parts)
    
        else:
            self.view.stats = self.stats.value
    
        await interaction.response.send_message(
            "✅ Details saved. Click Submit when ready.", ephemeral=True
        )




# ---------- Read-Only Modal ----------
class ReadOnlyDetailsModal(discord.ui.Modal):
    def __init__(self, item_row):
        super().__init__(title=item_row['name'])

        
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
            label="Details",
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
        modal = ReadOnlyDetailsModal(item_row=self.item_row)
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

# ---------- /add_item Command ----------

@bot.tree.command(name="add_item", description="Add a new item to the guild bank.")
@app_commands.describe(item_type="Type of the item")
@app_commands.choices(item_type=[
    
    app_commands.Choice(name="Armor", value="Armor"),
    app_commands.Choice(name="Crafting", value="Crafting"),
    app_commands.Choice(name="Consumable", value="Consumable"),
    app_commands.Choice(name="Misc", value="Misc"),
    app_commands.Choice(name="Weapon", value="Weapon")
])
async def add_item(interaction: discord.Interaction, item_type: str):  # Change this line
    try:
        # Now item_type is already a string, no need for .value
        view = ItemEntryView(interaction.user, item_type=item_type)
        await interaction.response.send_message(
            f"Adding a new {item_type}:", 
            view=view, 
            ephemeral=True
        )
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
        except:
            pass



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
    
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user}")
        print(f"Synced {len(synced)} command(s)")
        for cmd in synced:
            print(f"  - {cmd.name}")
    except Exception as e:
        print(f"Error syncing commands: {e}")
        import traceback
        traceback.print_exc()

@bot.event
async def on_error(event, *args, **kwargs):
    import traceback
    traceback.print_exc()

bot.run(TOKEN)





