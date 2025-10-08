
import os
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
import datetime
import asyncpg 
from PIL import Image, ImageDraw, ImageFont
import io

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

BG_FILES = {
    "Weapon": "assets/backgrounds/bg_weapon.png",
    "Armor": "assets/backgrounds/bg_weapon.png",
    "Consumable": "assets/backgrounds/bg_weapon.png",
    "Crafting": "assets/backgrounds/bg_weapon.png",
    "Misc": "assets/backgrounds/bg_weapon.png"
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

async def add_item_db(guild_id, name, type_, subtype=None, stats=None, classes=None, image=None, donated_by=None, qty=None, added_by=None, attack=None, effects=None, ac=None, created_images=None):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO inventory (guild_id, name, type, subtype, stats, classes, image, donated_by, qty, added_by, attack, effects, ac, created_images)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
        ''', guild_id, name, type_, subtype, stats, classes, image, donated_by, qty, added_by, attack, effects, ac, created_images)


async def get_all_items(guild_id):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, type, subtype, stats, classes, image, donated_by FROM inventory WHERE guild_id=$1 ORDER BY id", guild_id)
    return rows

async def get_item_by_name(guild_id, name):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM inventory WHERE guild_id=$1 AND name=$2", guild_id, name)
    return row



async def update_item_db(guild_id, item_id, **fields):
    """
    Update an item in the database.
    Only updates the fields provided.
    Automatically updates updated_at.
    """
    if not fields:
        return  # nothing to update

    set_clauses = []
    values = []
    i = 1
    for key, value in fields.items():
        set_clauses.append(f"{key}=${i}")
        values.append(value)
        i += 1

    # Add updated_at
    set_clauses.append(f"updated_at=NOW()")

    values.append(guild_id)
    values.append(item_id)

    sql = f"""
        UPDATE inventory
        SET {', '.join(set_clauses)}
        WHERE guild_id=${i} AND id=${i+1}
    """
    async with db_pool.acquire() as conn:
        await conn.execute(sql, *values)




async def delete_item_db(guild_id, item_id):
    # Reduce qty by 1
    item = await db.fetch_one("SELECT qty FROM items WHERE guild_id=? AND id=?", (guild_id, item_id))
    if not item:
        return
    if item['qty'] > 1:
        await db.execute("UPDATE items SET qty = qty - 1 WHERE id = ?", (item_id,))
    else:
        await db.execute("DELETE FROM items WHERE id = ?", (item_id,))



async def generate_item_image(item_name, item_type, subtype, stats, effects, donated_by):
    # Create a base image
    width, height = 512, 256
    background_color = (30, 30, 30)  # dark gray
    text_color = (255, 255, 255)     # white

    img = Image.new('RGB', (width, height), color=background_color)
    draw = ImageDraw.Draw(img)

    # Optional: load a TTF font
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()

    # Draw text
    y = 10
    line_spacing = 28
    for line in [
        f"Name: {item_name}",
        f"Type: {item_type} | Subtype: {subtype}",
        f"Stats: {stats}",
        f"Effects: {effects}",
        f"Donated by: {donated_by}"
    ]:
        draw.text((10, y), line, fill=text_color, font=font)
        y += line_spacing

    # Save image to BytesIO
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


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
        self.attack = ""
        self.effects = ""
        self.ac = ""

        # preload existing if editing
        if existing_data:
            self.item_name = existing_data['name']
            self.item_type = existing_data['type']
            self.subtype = existing_data['subtype']
            self.stats = existing_data['stats']
            self.ac = existing_data['ac']
            self.attack = existing_data['attack']
            self.effects = existing_data['effects']
            self.donated_by = existing_data['donated_by']
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
        # Ensure all fields are up-to-date from the modal
        classes_str = ", ".join(self.usable_classes)
        donor = self.donated_by or "Anonymous"
        added_by = str(interaction.user)
    
        # Only update fields for this item type
        fields_to_update = {
            "name": self.item_name,
            "type": self.item_type,
            "subtype": self.subtype,
            "stats": self.stats,
            "classes": classes_str,
            "donated_by": donor,
            "added_by": added_by
        }
    
        if self.item_type == "Weapon":
            fields_to_update["attack"] = self.attack
            fields_to_update["effects"] = self.effects
        elif self.item_type == "Armor":
            fields_to_update["ac"] = self.ac
            fields_to_update["effects"] = self.effects
        elif self.item_type == "Consumable":
            fields_to_update["effects"] = self.effects
        # Crafting / Misc uses stats and donated_by only
    
        if self.item_id:  # editing existing item
            await update_item_db(
                guild_id=interaction.guild.id,
                item_id=self.item_id,
                **fields_to_update
            )
            await interaction.response.send_message(
                f"✅ Updated **{self.item_name}**.",
                ephemeral=True
            )
        else:  # adding new item manually

            
            # Select background
            bg_path = BG_FILES.get(self.item_type, BG_FILES["Misc"])
            background = Image.open(bg_path).convert("RGBA")
            
        
            def draw_item_text(background, item_name, item_type, subtype, stats, effects, donated_by):
                draw = ImageDraw.Draw(background)
            
                # Load a fontWry
                # Example fonts
                font_title = ImageFont.truetype("assets/WinthorpeScB.ttf", 26)   # for the item name
                font_type = ImageFont.truetype("assets/Winthorpe.ttf", 24)      # for type/subtype
                font_stats = ImageFont.truetype("assets/Winthorpe.ttf", 20)     # for stats
                font_effects = ImageFont.truetype("assets/Winthorpe.ttf", 18)   # for effects
                font_donor = ImageFont.truetype("assets/Winthorpe.ttf", 16)     # for donated by
            
                width, height = background.size
            
                # Example positions:
                x_margin = 40
                y = 5  # start y
            
                # Name at top
                draw.text((x_margin, y), f"{item_name}", fill=(255, 255, 255), font=font_title)
                y += 50  # spacing after title
            
                # Type/Subtype
                draw.text((x_margin, y), f"{item_type} | {subtype}", fill=(200, 200, 200), font=font_type)
                y += 35
            
                # Stats
                draw.text((x_margin, y), f"Stats: {stats or 'N/A'}", fill=(255, 255, 255), font=font_stats)
                y += 35
            
                # Effects
                draw.text((x_margin, y), f"Effects: {effects or 'N/A'}", fill=(255, 255, 255), font=font_effects)
                y += 35
                        
                return background
                
            full_image = draw_item_text(
                background,
                self.item_name,
                self.item_type,
                self.subtype,
                self.stats,
                self.effects,
                self.donated_by or "Anonymous"
            )
        
            MAX_EMBED_WIDTH = 600
            MAX_EMBED_HEIGHT = 300
            width, height = full_image.size
            ratio = min(MAX_EMBED_WIDTH / width, MAX_EMBED_HEIGHT / height, 1.0)
            embed_image = full_image.resize((int(width * ratio), int(height * ratio)), Image.ANTIALIAS)
    
            # Convert both images to bytes
            full_bytes = io.BytesIO()
            full_image.save(full_bytes, format="PNG")
            full_bytes.seek(0)
    
            embed_bytes = io.BytesIO()
            embed_image.save(embed_bytes, format="PNG")
            embed_bytes.seek(0)
        
            # 2. Save all info to database, including created_images
            await add_item_db(
                guild_id=interaction.guild.id,
                name=self.item_name,
                type_=self.item_type,
                subtype=self.subtype,
                stats=self.stats,
                classes=", ".join(self.usable_classes) or "All",
                image=None,  # original image field empty
                created_images=created_images,  # store bytes directly
                donated_by=self.donated_by or "Anonymous",
                qty=1,
                added_by=str(interaction.user),
                attack=self.attack,
                effects=self.effects,
                ac=self.ac
            )
            file_for_embed = discord.File(fp=embed_bytes, filename="item_preview.png")
            embed = discord.Embed(title=self.item_name, description=f"{self.item_type} | {self.subtype}")
            embed.set_image(url=f"attachment://item_preview.png")
            await interaction.response.send_message(
                f"✅ Added **{self.item_name}** to the Guild Bank (manual image created).",
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
class ImageDetailsModal(discord.ui.Modal):
    def __init__(self, interaction: discord.Interaction, view=None, item_row=None):
        """
        Unified modal for adding or editing an image item.
        """
        super().__init__(title="Image Item Details")
        self.interaction = interaction
        self.view = view
        self.is_edit = item_row is not None

        if self.is_edit:
            self.item_id = item_row['id']
            self.guild_id = item_row['guild_id']
            default_name = item_row['name']
            default_donor = item_row.get('donated_by') or "Anonymous"
        else:
            self.item_id = None
            self.guild_id = interaction.guild.id
            default_name = ""
            default_donor = ""

        # Item Name
        self.item_name = discord.ui.TextInput(label="Item Name", default=default_name, required=True)
        self.add_item(self.item_name)

        # Donated By
        self.donated_by = discord.ui.TextInput(label="Donated By", default=default_donor, required=False)
        self.add_item(self.donated_by)

    async def on_submit(self, modal_interaction: discord.Interaction):
        item_name = self.item_name.value
        donated_by = self.donated_by.value or "Anonymous"
        added_by = str(modal_interaction.user)
        if self.is_edit:
            await update_item_db(
                guild_id=self.guild_id,
                item_id=self.item_id,
                name=item_name,
                donated_by=donated_by,
                added_by=added_by
            )
            await modal_interaction.response.send_message(f"✅ Updated **{item_name}**.", ephemeral=True)
        else:
            if not self.view or not getattr(self.view, "image", None):
                await modal_interaction.response.send_message(
                    "❌ No image provided. Send an attachment or a link in chat.", ephemeral=True
                )
                return

            await add_item_db(
                guild_id=self.guild_id,
                name=item_name,
                type_="Image",
                subtype="Image",
                stats="",
                classes="All",
                image=self.view.image,
                donated_by=donated_by,
                qty=1,
                added_by=added_by
            )
            await modal_interaction.response.send_message(
                f"✅ Image item **{item_name}** added to the guild bank!", ephemeral=True
            )



# ------ITEM DETAILS ----
class ItemDetailsModal(discord.ui.Modal):
    def __init__(self, view: ItemEntryView):
        super().__init__(title=f"{view.item_type} Details")
        self.view = view

        # Weapon
        if view.item_type == "Weapon":
            self.item_name = discord.ui.TextInput(
                label="Item Name", default=view.item_name, required=True
            )
            self.attack = discord.ui.TextInput(
                label="Attack / Delay", default=view.attack or "", required=True
            )
            self.stats = discord.ui.TextInput(
                label="Stats", default=view.stats or "", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default=view.effects or "", required=False, style=discord.TextStyle.paragraph
            )
            self.donated_by = discord.ui.TextInput(
                label="Donated by", default=view.donated_by or "", required=False
            )
            self.add_item(self.item_name)
            self.add_item(self.attack)
            self.add_item(self.stats)
            self.add_item(self.effects)
            self.add_item(self.donated_by)

        # Armor
        elif view.item_type == "Armor":
            self.item_name = discord.ui.TextInput(
                label="Item Name", default=view.item_name, required=True
            )
            self.ac = discord.ui.TextInput(
                label="Armor Class", default=view.ac or "", required=True
            )
            self.stats = discord.ui.TextInput(
                label="Stats", default=view.stats or "", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default=view.effects or "", required=False, style=discord.TextStyle.paragraph
            )
            self.donated_by = discord.ui.TextInput(
                label="Donated by", default=view.donated_by or "", required=False
            )
            self.add_item(self.item_name)
            self.add_item(self.ac)
            self.add_item(self.stats)
            self.add_item(self.effects)
            self.add_item(self.donated_by)

        # Consumable
        elif view.item_type == "Consumable":
            self.item_name = discord.ui.TextInput(
                label="Item Name", default=view.item_name, required=True
            )
            self.stats = discord.ui.TextInput(
                label="Stats", default=view.stats or "", required=False, style=discord.TextStyle.paragraph
            )
            self.effects = discord.ui.TextInput(
                label="Effects", default=view.effects or "", required=False, style=discord.TextStyle.paragraph
            )
            self.donated_by = discord.ui.TextInput(
                label="Donated by", default=view.donated_by or "", required=False
            )
            self.add_item(self.item_name)
            self.add_item(self.stats)
            self.add_item(self.effects)
            self.add_item(self.donated_by)

        # Crafting / Misc
        else:
            self.item_name = discord.ui.TextInput(
                label="Item Name", default=view.item_name, required=True
            )
            self.stats = discord.ui.TextInput(
                label="Info", default=view.stats or "", style=discord.TextStyle.paragraph, required=False
            )
            self.donated_by = discord.ui.TextInput(
                label="Donated by", default=view.donated_by or "", required=False
            )
            self.add_item(self.item_name)
            self.add_item(self.stats)
            self.add_item(self.donated_by)

    async def on_submit(self, interaction: discord.Interaction):
        # Save values back to the view
        self.view.item_name = self.item_name.value
        self.view.donated_by = self.donated_by.value or "Anonymous"

        if self.view.item_type == "Weapon":
            self.view.attack = self.attack.value
            self.view.stats = self.stats.value
            self.view.effects = self.effects.value
        elif self.view.item_type == "Armor":
            self.view.ac = self.ac.value
            self.view.stats = self.stats.value
            self.view.effects = self.effects.value
        elif self.view.item_type == "Consumable":
            self.view.stats = self.stats.value
            self.view.effects = self.effects.value
        else:  # Crafting / Misc
            self.view.stats = self.stats.value

        await interaction.response.send_message(
            "✅ Details saved. Click Submit when ready.", ephemeral=True
        )








# ---------- /view_bank Command ----------

@bot.tree.command(name="view_bank", description="View all items in the guild bank.")
async def view_bank(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM inventory WHERE guild_id=$1 AND qty >= 1 ORDER BY name",
            interaction.guild.id
        )

    if not rows:
        await interaction.response.send_message("Guild bank is empty.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    TYPE_COLORS = {
        "weapon": discord.Color.red(),
        "armor": discord.Color.blue(),
        "consumable": discord.Color.gold(),
        "crafting": discord.Color.green(),
        "misc": discord.Color.dark_gray(),
    }

    def code_block(text: str) -> str:
        text = (text or "").strip()
        return f"```{text}```" if text else "```None```"

    async def build_embed_with_file(row):
        item_type = (row.get('type') or "Misc").lower()
        emoji = ITEM_TYPE_EMOJIS.get(row['type'], "")
        name = row.get('name', 'Unknown Item')
        subtype = row.get('subtype', 'None')
        donated_by = row.get('donated_by') or "Anonymous"
        stats = row.get('stats') or ""
        effects = row.get('effects') or ""

        embed = discord.Embed(
            title=f"{emoji} {name}",
            color=TYPE_COLORS.get(item_type, discord.Color.blurple())
        )
        embed.set_footer(text=f"Donated by: {donated_by} | {name}")

        # Handle created_images (raw bytes)
        if row.get('created_images'):
            file = discord.File(io.BytesIO(row['created_images']), filename=f"{name}.png")
            embed.set_image(url=f"attachment://{name}.png")
            return embed, file

        # Handle uploaded images (URL)
        if row.get('image'):
            embed.set_image(url=row['image'])
            return embed, None

        # Otherwise, text-only
        desc = f"{row['type']} | {subtype}\n"
        match item_type:
            case "weapon":
                attack = row.get('attack') or "N/A"
                desc += (
                    f"Attack / Delay: {attack}\n"
                    f"Stats: {code_block(stats)}"
                    f"Effects: {code_block(effects)}"
                )
            case "armor":
                ac = row.get('ac') or "N/A"
                desc += (
                    f"AC: {ac}\n"
                    f"Stats: {code_block(stats)}"
                    f"Effects: {code_block(effects)}"
                )
            case "consumable":
                desc += (
                    f"Stats: {code_block(stats)}"
                    f"Effects: {code_block(effects)}"
                )
            case "crafting" | "misc":
                desc += f"Info: {code_block(stats)}"
            case _:
                desc += f"Info: {code_block(stats)}"

        desc += f"\nDonated by: {donated_by}"
        embed.description = desc
        return embed, None

    # Send embeds
    for row in rows:
        embed, file = await build_embed_with_file(row)
        if file:
            await interaction.channel.send(embed=embed, file=file)
        else:
            await interaction.channel.send(embed=embed)

    await interaction.followup.send(f"✅ Sent {len(rows)} items.", ephemeral=True)



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
    active_views[interaction.user.id] = view  # Track this view

    # If an image was uploaded, attach it to the view
    if image:
        view.image = image.url
        view.waiting_for_image = False
        # Optional: open the minimal modal for donated_by and item name
        await interaction.response.send_modal(ImageDetailsModal(interaction, view=view))
    else:
        # Just show the view with dropdowns for subtype/classes
        await interaction.response.send_message(f"Adding a new {item_type}:", view=view, ephemeral=True)



@bot.tree.command(name="edit_item", description="Edit an existing item in the guild bank.")
@app_commands.describe(item_name="Name of the item to edit")
async def edit_item(interaction: discord.Interaction, item_name: str):
    # Fetch the item from the database
    item = await get_item_by_name(interaction.guild.id, item_name)
    if not item:
        await interaction.response.send_message("Item not found.", ephemeral=True)
        return

    # Open the appropriate modal based on whether the item has an image
    if item.get('image'):
        await interaction.response.send_modal(ImageDetailsModal(interaction, item_row=item))
    else:
        view = ItemEntryView(interaction.user, item_type=item['type'], item_id=item['id'], existing_data=item)
        await interaction.response.send_modal(ItemDetailsModal(view))




@bot.tree.command(name="remove_item", description="Remove an item from the guild bank.")
@app_commands.describe(item_name="Name of the item to remove")
async def remove_item(interaction: discord.Interaction, item_name: str):
    async with db_pool.acquire() as conn:
        # Fetch the item with qty = 1 (active) to remove
        item = await conn.fetchrow(
            "SELECT * FROM inventory WHERE guild_id=$1 AND name=$2 AND qty=1",
            interaction.guild.id,
            item_name
        )

        if not item:
            await interaction.response.send_message(
                "Item not found or already removed.", ephemeral=True
            )
            return

        # Set qty to 0 instead of deleting
        await conn.execute(
            "UPDATE inventory SET qty=0 WHERE item_id=$1",
            item['id']
        )

    await interaction.response.send_message(
        f"🗑️ Removed **{item_name}** from the Guild Bank.", ephemeral=True
    )








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





