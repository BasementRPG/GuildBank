import os
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
import datetime
import asyncpg 

active_views = {}

print("discord.py version:", discord.__version__)


TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ITEM_TYPE_EMOJIS = {
    "Weapon": "⚔️",
    "Crafting": "⚒️",
    "Armor": "🛡️",
    "Consumable": "🧪",
    "Misc": "🔑",
    "Funds": "💰"
}


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

async def add_item_db(guild_id, name, type_, subtype=None, stats=None, classes=None, image=None, donated_by=None, qty=None, added_by=None):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO inventory (guild_id, name, type, subtype, stats, classes, image, donated_by, qty, added_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ''', guild_id, name, type_, subtype, stats, classes, image, donated_by, qty, added_by)


async def get_all_items(guild_id):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, type, subtype, stats, classes, image, donated_by FROM inventory WHERE guild_id=$1 ORDER BY id", guild_id)
    return rows

async def get_item_by_name(guild_id, name):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM inventory WHERE guild_id=$1 AND name=$2", guild_id, name)
    return row

async def update_item_db(guild_id, item_id, name, type_, subtype, stats, classes):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            UPDATE inventory
            SET name=$1, type=$2, subtype=$3, stats=$4, classes=$5
            WHERE guild_id=$6 AND id=$7
        ''', name, type_, subtype, stats, classes, guild_id, item_id)

async def delete_item_db(guild_id, item_id):
    # Reduce qty by 1
    item = await db.fetch_one("SELECT qty FROM items WHERE guild_id=? AND id=?", (guild_id, item_id))
    if not item:
        return
    if item['qty'] > 1:
        await db.execute("UPDATE items SET qty = qty - 1 WHERE id = ?", (item_id,))
    else:
        await db.execute("DELETE FROM items WHERE id = ?", (item_id,))


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
        self.donated_by = ""

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

 
        self.details_button = discord.ui.Button(label="Manual Entry", style=discord.ButtonStyle.secondary)
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
        donor=self.donated_by or "Anonymous"
        # default donor to the user running the command
        added_by = getattr(self, "added_by", str(interaction.user))
    
        if self.item_id:  # editing
            await update_item_db(
                guild_id=interaction.guild.id,
                item_id=self.item_id,
                name=self.item_name,
                type_=self.item_type,
                subtype=self.subtype,
                stats=self.stats,
                classes=classes_str,
                donated_by=donor,
                
                added_by=added_by
            )
            await interaction.response.send_message(
                f"✅ Updated **{self.item_name}**.",
                ephemeral=True
            )
        else:  # adding new
            await add_item_db(
                guild_id=interaction.guild.id,
                name=self.item_name,
                type_=self.item_type,
                subtype=self.subtype,
                stats=self.stats,
                classes=classes_str,
                donated_by=self.donated_by,  # <-- new
                qty=1,
                added_by=added_by
            )
            await interaction.response.send_message(
                f"✅ Added **{self.item_name}** to the Guild Bank.",
                ephemeral=True
            )
    
        self.stop()


    async def reset_entry(self, interaction: discord.Interaction):
        self.subtype = None
        self.usable_classes = []
        self.item_name = ""
        self.stats = ""
        await interaction.response.send_message("Entry canceled and reset.", ephemeral=True)
        self.stop()

#-----IMAGE UPLOAD ----



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
            self.donated_by = discord.ui.TextInput(label="Donated by", default="", placeholder="Example: Thieron or Raid Dropped", required=False)

            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.attack_delay)
            self.add_item(self.attributes)
            self.add_item(self.effects)
            self.add_item(self.donated_by)

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
            self.donated_by = discord.ui.TextInput(label="Donated by", default="", placeholder="Example: Thieron or Raid Dropped", required=False)
            
            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.armor_class)
            self.add_item(self.attributes)
            self.add_item(self.effects)
            self.add_item(self.donated_by)

        
        elif view.item_type == "Crafting":
            self.item_name = discord.ui.TextInput(label="Item Name", placeholder="Example: Cloth Scraps", default=view.item_name, required=True)
            self.info = discord.ui.TextInput(label="Info", default="", placeholder="Example: Used primarily for tailor and sub-compoints for other tradeskills", required=False)
            
            self.donated_by = discord.ui.TextInput(label="Donated by", default="", placeholder="Example: Thieron or Raid Dropped", required=False)
            
            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.info)
            self.add_item(self.donated_by)

        elif view.item_type == "Consumable":
            self.item_name = discord.ui.TextInput(label="Item Name", placeholder="Example: Dinner Gift Basket", default=view.item_name, required=True)
                    
           
            # Optional fields
            self.attributes = discord.ui.TextInput(
                label="Stats", default="", placeholder="Example: +5 str, +5 dex, +5 sta, + 5 agi, +30 hp, +30 mana ", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default="", placeholder="Example: This is a miraculous meal", required=False, style=discord.TextStyle.paragraph
            )

            self.donated_by = discord.ui.TextInput(label="Donated by", default="", placeholder="Example: Thieron or Raid Dropped", required=False)
            
            # Add fields to modal
            self.add_item(self.item_name)
            self.add_item(self.attributes)
            self.add_item(self.effects)
            self.add_item(self.donated_by)

        else:
            self.item_name = discord.ui.TextInput(label="Item Name", placeholder="Example: Deathfist Slashed Belt", default=view.item_name, required=True)
            self.stats = discord.ui.TextInput(
                label="Info", placeholder="Example: Can be turned in for xp", default=view.stats, style=discord.TextStyle.paragraph
            )

            self.donated_by = discord.ui.TextInput(label="Donated by", default="", placeholder="Example: Thieron or Raid Dropped", required=False)
            
            self.add_item(self.item_name)
            self.add_item(self.stats)
            self.add_item(self.donated_by)

    async def on_submit(self, interaction: discord.Interaction):
        self.view.item_name = self.item_name.value
        self.view.donated_by = self.donated_by.value or "Anonymous"
        if self.view.item_type == "Weapon":
             
            # Start with Attack/Delay
            stats_parts = [f"Attack/Delay: {self.attack_delay.value}"]
    
            # Add optional fields if filled
            if self.attributes.value.strip():
                stats_parts.append(f"Stats: {self.attributes.value.strip()}")
            if self.effects.value.strip():
                stats_parts.append(f"Effects: {self.effects.value.strip()}")
            if self.donated_by.value.strip():
                stats_parts.append(f"Donated By: {self.donated_by.value.strip()}")
                 
            # Combine into one stats string
            self.view.stats = "\n".join(stats_parts)
    
        elif self.view.item_type == "Armor":
            
            stats_parts = [f"Armor Class: {self.armor_class.value}"]
            
            # Add optional fields if filled
            if self.attributes.value.strip():
                stats_parts.append(f"Stats: {self.attributes.value.strip()}")
            if self.effects.value.strip():
                stats_parts.append(f"Effects: {self.effects.value.strip()}")
            if self.donated_by.value.strip():
                stats_parts.append(f"Donated By: {self.donated_by.value.strip()}")
                 
    
            # Combine into one stats string
            self.view.stats = "\n".join(stats_parts)

        
        elif self.view.item_type == "Crafting":
            stats_parts = [f"Info: {self.info.value}"]
                 
            if self.donated_by.value.strip():
                stats_parts.append(f"Donated By: {self.donated_by.value.strip()}")
                 
            self.view.stats = "\n".join(stats_parts)

        elif self.view.item_type == "Consumable":
            stats_parts = [""]
            # Add optional fields if filled
            if self.attributes.value.strip():
                stats_parts.append(f"Stats: {self.attributes.value.strip()}")
            if self.effects.value.strip():
                stats_parts.append(f"Effects: {self.effects.value.strip()}")
            if self.donated_by.value.strip():
                stats_parts.append(f"Donated By: {self.donated_by.value.strip()}")
                 
            
            self.view.stats = "\n".join(stats_parts)
    
        else:
            stats_parts = [f"Info: {self.stats.value}"]

            if self.donated_by.value.strip():
                stats_parts.append(f"Donated By: {self.donated_by.value.strip()}")
                 
            
            self.view.stats = "\n".join(stats_parts)
    
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

# ---------- /view_bank Command ----------

@bot.tree.command(name="view_bank", description="View all items in the guild bank.")
async def view_bank(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM items WHERE guild_id=$1 AND qty=1 ORDER BY name",
            interaction.guild.id
        )
   
    if not rows:
        await interaction.response.send_message("Guild bank is empty.", ephemeral=True)
        return

    # Split items into ones with and without images
    items_with_image = sorted([r for r in rows if r['image']], key=lambda r: r['name'].lower())
    items_without_image = sorted([r for r in rows if not r['image']], key=lambda r: r['name'].lower())

    # First, send items with images
    
    for row in sorted(items_with_image, key=lambda r: r['name'].lower()):
        donated_by = row.get('donated_by') or "Anonymous"
        embed = discord.Embed(color=discord.Color.blue())
        embed.set_image(url=row['image'])
        embed.set_footer(text=f"Donated By: {donated_by} | {row['name']} ")
        await interaction.channel.send(embed=embed)  # ✅ inside async function

    
    # Then, send items without images
    for row in items_without_image:
        emoji = ITEM_TYPE_EMOJIS.get(row['type'], "")
        embed = discord.Embed(
            title=f"{emoji} {row['name']}",
            description=f"{row['type']} | {row['subtype']}\nDonated By: {row.get('donated_by', 'Unknown')}",
            color=discord.Color.blue()
        )
        view = discord.ui.View()
        view.add_item(ViewDetailsButton(item_row=row))
        await interaction.channel.send(embed=embed, view=view)

    await interaction.response.send_message(f"✅ Sent {len(rows)} items.", ephemeral=True)




# ---------- /add_item Command ----------

@bot.tree.command(name="add_item", description="Add a new item to the guild bank.")
@app_commands.describe(item_type="Type of the item", image="Optional image upload")
@app_commands.choices(item_type=[
    app_commands.Choice(name="Armor", value="Armor"),
    app_commands.Choice(name="Crafting", value="Crafting"),
    app_commands.Choice(name="Consumable", value="Consumable"),
    app_commands.Choice(name="Misc", value="Misc"),
    app_commands.Choice(name="Weapon", value="Weapon")
])
async def add_item(interaction: discord.Interaction, item_type: str, image: discord.Attachment = None):

    view = ItemEntryView(interaction.user, item_type=item_type)
    active_views[interaction.user.id] = view  # Track this view for image messages

    # If an image was uploaded via slash command
    if image:
    
        view.image = image.url
        view.waiting_for_image = False
    
        # Optional: open a minimal modal for donated_by and item name
        class ImageDetailsModal(discord.ui.Modal):
            def __init__(self):
                super().__init__(title="Image Item Details")
                self.item_name = discord.ui.TextInput(label="Item Name", required=True)
                self.donated_by = discord.ui.TextInput(label="Donated By", required=False)
                self.add_item(self.item_name)
                self.add_item(self.donated_by)

            async def on_submit(self, modal_interaction: discord.Interaction):
                item_name = self.item_name.value
                donated_by = self.donated_by.value or "Anonymous"

                # Make sure the image was set in the view
                if not view.image:
                    await modal_interaction.response.send_message(
                        "❌ No image provided. Send an attachment or a link in chat.", ephemeral=True
                    )
                    return

                # Save to DB
                await add_item_db(
                    guild_id=interaction.guild.id,
                    name=item_name,
                    type_=item_type,
                    subtype="Image",
                    stats="",
                    classes="All",
                    image=view.image,
                    donated_by=donated_by,
                    qty=1
                )

                active_views.pop(interaction.user.id, None)  # remove from active_views
                await modal_interaction.response.send_message(
                    f"✅ Image item **{item_name}** added to the guild bank!", ephemeral=True
                )

        await interaction.response.send_modal(ImageDetailsModal())
        return

    # Otherwise, open the normal item entry view
    await interaction.response.send_message(
        f"Adding a new {item_type}:", view=view, ephemeral=True
    )




@bot.event
async def on_message(message):
    # Ignore bot messages
    if message.author.bot:
        return

    view = active_views.get(message.author.id)
    if view and getattr(view, "waiting_for_image", False):
        if message.attachments:
            view.image = message.attachments[0].url
        else:
            view.image = message.content  # assume it's a link
        view.waiting_for_image = False
        await message.channel.send(
            "📷 Got your image. Fill out the modal and click Submit to save it.", delete_after=5
        )


@bot.tree.command(name="edit_item", description="Edit an existing item in the guild bank.")
@app_commands.describe(item_name="Name of the item to edit")
async def edit_item(interaction: discord.Interaction, item_name: str):
    item = await get_item_by_name(interaction.guild.id, item_name)
    if not item:
        await interaction.response.send_message("Item not found.", ephemeral=True)
        return
    view = ItemEntryView(interaction.user, item_type=item['type'], item_id=item['id'], existing_data=item)
    await interaction.response.send_message(f"Editing **{item_name}**:", view=view, ephemeral=True)



@bot.tree.command(name="remove_item", description="Remove an item from the guild bank.")
@app_commands.describe(item_name="Name of the item to remove")
async def remove_item(interaction: discord.Interaction, item_name: str):
    # Fetch the item with qty = 1 (active) to remove
    item = await db.fetch_one(
        "SELECT * FROM items WHERE guild_id=? AND name=? AND qty=1",
        (interaction.guild.id, item_name)
    )
    
    if not item:
        await interaction.response.send_message("Item not found or already removed.", ephemeral=True)
        return

    # Set qty to 0 instead of deleting
    await db.execute(
        "UPDATE items SET qty=0 WHERE id=?",
        (item['id'],)
    )

    await interaction.response.send_message(f"🗑️ Removed **{item_name}** from the Guild Bank.", ephemeral=True)









# ---------- Funds DB Helpers ----------


# ----------------- Currency Helpers -----------------
# Convert from 4-part currency to total copper
def currency_to_copper(plat=0, gold=0, silver=0, copper=0):
    # 1 Platinum = 100 Gold = 10,000 Silver = 1,000,000 Copper
    # 1 Gold = 100 Silver = 10,000 Copper
    # 1 Silver = 100 Copper
    total_copper = (
        plat * 100 * 100 * 100 +  # Plat to Copper
        gold * 100 * 100 +        # Gold to Copper
        silver * 100 +            # Silver to Copper
        copper                     # Copper
    )
    return total_copper


# Convert total copper back to 4-part currency
def copper_to_currency(total_copper):
    plat = total_copper // (100*100*100)
    remainder = total_copper % (100*100*100)
    
    gold = remainder // (100*100)
    remainder = remainder % (100*100)
    
    silver = remainder // 100
    copper = remainder % 100
    
    return plat, gold, silver, copper


# ----------------- DB Helpers -----------------
async def add_funds_db(guild_id, type_, total_copper, donated_by=None, donated_at=None):
    """Insert a donation or spend entry."""
    donated_at = donated_at or date.today.datetime()  # Use today if not provided
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO funds (guild_id, type, total_copper, donated_by, donated_at)
            VALUES ($1, $2, $3, $4, $5)
        ''',guild_id, type_, total_copper, donated_by, donated_at)

async def get_fund_totals(guild_id):
    """Get total donated and spent copper."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT
                SUM(CASE WHEN type='donation' THEN total_copper ELSE 0 END) AS donated,
                SUM(CASE WHEN type='spend' THEN total_copper ELSE 0 END) AS spent
            FROM funds
            WHERE guild_id=$1
        ''', guild_id)
    return row

async def get_all_donations(guild_id):
    """Get all donations (type='donation')"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT donated_by, total_copper, donated_at
            FROM funds
            WHERE guild_id=$1 AND type='donation'
            ORDER BY donated_at DESC
        ''', guild_id)
    return rows

# ----------------- Modals -----------------
class AddFundsModal(Modal):
    def __init__(self):
        super().__init__(title="Add Donation")
        self.plat = TextInput(label="Platinum", default="0", required=False)
        self.gold = TextInput(label="Gold", default="0", required=False)
        self.silver = TextInput(label="Silver", default="0", required=False)
        self.copper = TextInput(label="Copper", default="0", required=False)
        self.donated_by = TextInput(label="Donated By", placeholder="Optional", required=False)
        self.add_item(self.plat)
        self.add_item(self.gold)
        self.add_item(self.silver)
        self.add_item(self.copper)
        self.add_item(self.donated_by)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            total = currency_to_copper(
                plat=int(self.plat.value or 0),
                gold=int(self.gold.value or 0),
                silver=int(self.silver.value or 0),
                copper=int(self.copper.value or 0)
            )
        except ValueError:
            await interaction.response.send_message("❌ Invalid number entered.", ephemeral=True)
            return

        await add_funds_db(
            guild_id=interaction.guild.id,
            type_='donation',
            total_copper=total,
            donated_by=self.donated_by.value.strip() or None,
            donated_at=datetime.date.today()
        )
        await interaction.response.send_message("✅ Donation added!", ephemeral=True)

class SpendFundsModal(Modal):
    def __init__(self):
        super().__init__(title="Spend Funds")
        self.plat = TextInput(label="Platinum", default="0", required=False)
        self.gold = TextInput(label="Gold", default="0", required=False)
        self.silver = TextInput(label="Silver", default="0", required=False)
        self.copper = TextInput(label="Copper", default="0", required=False)
        self.note = TextInput(label="Note", placeholder="Optional", required=False)
        self.add_item(self.plat)
        self.add_item(self.gold)
        self.add_item(self.silver)
        self.add_item(self.copper)
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            total = currency_to_copper(
                plat=int(self.plat.value or 0),
                gold=int(self.gold.value or 0),
                silver=int(self.silver.value or 0),
                copper=int(self.copper.value or 0)
            )
        except ValueError:
            await interaction.response.send_message("❌ Invalid number entered.", ephemeral=True)
            return

        await add_funds_db(
            guild_id=interaction.guild.id,
            type_='spend',
            total_copper=total,
            donated_by=self.note.value.strip() or None,
            donated_at=datetime.date.today()
        )
        await interaction.response.send_message("✅ Funds spent recorded!", ephemeral=True)


# Modal to show full donation history

class DonationHistoryModal(discord.ui.Modal):
    def __init__(self, guild_id, donations):
        super().__init__(title="📜 Full Donation History")
        self.guild_id = guild_id
        self.donations = donations
        
        total_copper = sum(d['total_copper'] for d in donations)
        t_plat, t_gold, t_silver, t_copper = copper_to_currency(total_copper)
        total_text = f"{t_plat}p {t_gold}g {t_silver}s {t_copper}c"

        # Combine all donations into one string
        history_text = ""
      
        for d in donations:
            total_copper += d['total_copper']
            plat, gold, silver, copper = copper_to_currency(d['total_copper'])
            donor = d['donated_by'] or "Anonymous"
            date = d['donated_at'].strftime("%m-%d-%y")
            history_text += f"{donor} | {plat}p {gold}g {silver}s {copper}c | {date}\n"
        
        # Optional: truncate if too long
        if len(history_text) > 4000:
            history_text = history_text[:3990] + "\n…"
        
        
        self.total_input = discord.ui.TextInput(
            label="💰 Total Donated",
            style=discord.TextStyle.short,
            default=total_text,
            required=False
        )
        self.total_input.disabled = True
        self.add_item(self.total_input)

        
        self.history_input = discord.ui.TextInput(
            label="Donation History",
            style=discord.TextStyle.paragraph,
            default=history_text,
            required=False
        )
        self.history_input.disabled = True
        self.add_item(self.history_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Closed.", ephemeral=True)

class SpendingHistoryModal(discord.ui.Modal):
    def __init__(self, guild_id, spendings):
        super().__init__(title="📜 Full Spending History")
        self.guild_id = guild_id
        self.spendings = spendings
        

        total_copper = sum(s['total_copper'] for s in spendings)
        t_plat, t_gold, t_silver, t_copper = copper_to_currency(total_copper)
        total_text = f"{t_plat}p {t_gold}g {t_silver}s {t_copper}c"
        
        # Combine all spendings into one string
        history_text = ""
        total_copper = 0
        for s in spendings:
            total_copper += s['total_copper']
            plat, gold, silver, copper = copper_to_currency(s['total_copper'])
            spender = s['donated_by'] or "Unknown"
            date = s['donated_at'].strftime("%m-%d-%y")
            history_text += f"{spender} | {plat}p {gold}g {silver}s {copper}c | {date}\n"

        if len(history_text) > 4000:
            history_text = history_text[:3990] + "\n…"

        self.total_input = discord.ui.TextInput(
            label="💰 Total Spending",
            style=discord.TextStyle.short,
            default=total_text,
            required=False
        )
        self.total_input.disabled = True
        self.add_item(self.total_input)

        self.history_input = discord.ui.TextInput(
            label="Spending History",
            style=discord.TextStyle.paragraph,
            default=history_text,
            required=False
        )
        self.history_input.disabled = True
        self.add_item(self.history_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Closed.", ephemeral=True)



    # Button to view full history

class ViewFullHistoryButton(discord.ui.Button):
    def __init__(self, donations):
        super().__init__(label="Donation History", style=discord.ButtonStyle.secondary)
        self.donations = donations  # Already filtered by guild_id

    async def callback(self, interaction: discord.Interaction):
        if not self.donations:
            await interaction.response.send_message("No donations found for this guild.", ephemeral=True)
            return

        modal = DonationHistoryModal(interaction.guild.id, self.donations)
        await interaction.response.send_modal(modal)


class ViewSpendingHistoryButton(discord.ui.Button):
    def __init__(self, spendings):
        super().__init__(label="Spending History", style=discord.ButtonStyle.secondary)
        self.spendings = spendings  # Already filtered by guild_id

    async def callback(self, interaction: discord.Interaction):
        if not self.spendings:
            await interaction.response.send_message("No spending found for this guild.", ephemeral=True)
            return

        modal = SpendingHistoryModal(interaction.guild.id, self.spendings)
        await interaction.response.send_modal(modal)




# ----------------- Slash Commands -----------------
@bot.tree.command(name="add_funds", description="Add a donation to the guild bank.")
async def add_funds(interaction: discord.Interaction):
    await interaction.response.send_modal(AddFundsModal())

@bot.tree.command(name="spend_funds", description="Record spent guild funds.")
async def spend_funds(interaction: discord.Interaction):
    await interaction.response.send_modal(SpendFundsModal())

@bot.tree.command(name="view_funds", description="View current available funds.")
async def view_funds(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    async with db_pool.acquire() as conn:
        all_donations = await conn.fetch('''
            SELECT donated_by, total_copper, donated_at, guild_id
            FROM funds
            WHERE type='donation'
            ORDER BY donated_at DESC
        ''')
        all_spendings = await conn.fetch('''
            SELECT donated_by, total_copper, donated_at, guild_id
            FROM funds
            WHERE type='spend'
            ORDER BY donated_at DESC
        ''')

    # Filter by current guild
    donations = [d for d in all_donations if d['guild_id'] == guild_id]
    spendings = [s for s in all_spendings if s['guild_id'] == guild_id]

    donated = sum(d['total_copper'] for d in donations)
    spent = sum(s['total_copper'] for s in spendings)
    available = donated - spent
    plat, gold, silver, copper = copper_to_currency(available)

    embed = discord.Embed(title="💰 Available Funds", color=discord.Color.gold())
    embed.add_field(name="\u200b", value=f"{plat}p {gold}g {silver}s {copper}c")

    view = discord.ui.View()
    view.add_item(ViewFullHistoryButton(donations))
    view.add_item(ViewSpendingHistoryButton(spendings))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)



@bot.tree.command(name="view_donations", description="View all donations in the guild bank.")
async def view_donations(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    async with db_pool.acquire() as conn:
        donations = await conn.fetch('''
            SELECT donated_by, total_copper, donated_at
            FROM funds
            WHERE type='donation' AND guild_id=$1
            ORDER BY donated_at DESC
        ''', guild_id)

    if not donations:
        await interaction.response.send_message("No donations found for this guild.", ephemeral=True)
        return

    total_copper = sum(d['total_copper'] for d in donations)
    t_plat, t_gold, t_silver, t_copper = copper_to_currency(total_copper)

    embed = discord.Embed(
        title="📜 Donation Records",
        description=f"**Total Funds:** {t_plat}p {t_gold}g {t_silver}s {t_copper}c",
        color=discord.Color.green()
    )

    view = discord.ui.View()
    view.add_item(ViewFullHistoryButton(donations))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)





# ---------------- Bot Setup ----------------

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





