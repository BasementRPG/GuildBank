import discord
from discord.ext import commands
import sqlite3
import os

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# --- SQLite setup ---
conn = sqlite3.connect("inventory.db")
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS inventory (
    user_id TEXT,
    item_name TEXT,
    item_type TEXT,
    item_class TEXT,
    photo_url TEXT
)""")
conn.commit()

ITEM_TYPES = ["Weapon", "Armor", "Potion", "Misc"]
CLASSES = ["Warrior", "Mage", "Rogue", "Cleric"]

# ----- Add Item Flow -----
class AddItemModal(discord.ui.Modal, title="Add Item"):
    item_name = discord.ui.TextInput(label="Item Name", placeholder="Enter item name")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select the item type and class below:",
            view=TypeClassView(self.item_name.value, interaction.user.id),
            ephemeral=True
        )

class TypeClassView(discord.ui.View):
    def __init__(self, item_name, user_id, edit=False, old_name=None):
        super().__init__(timeout=120)
        self.item_name = item_name
        self.user_id = user_id
        self.selected_type = None
        self.selected_class = None
        self.edit = edit
        self.old_name = old_name

        self.type_select = discord.ui.Select(
            placeholder="Select Item Type",
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES]
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        self.class_select = discord.ui.Select(
            placeholder="Select Class",
            options=[discord.SelectOption(label=c) for c in CLASSES]
        )
        self.class_select.callback = self.select_class
        self.add_item(self.class_select)

        self.add_item(UploadPhotoButton(self))

    async def select_type(self, interaction: discord.Interaction):
        self.selected_type = self.type_select.values[0]
        await interaction.response.send_message(f"Item type selected: {self.selected_type}", ephemeral=True)

    async def select_class(self, interaction: discord.Interaction):
        self.selected_class = self.class_select.values[0]
        await interaction.response.send_message(f"Class selected: {self.selected_class}", ephemeral=True)

class UploadPhotoButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="Upload Photo (Optional)", style=discord.ButtonStyle.primary)
        self.view_parent = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Upload a photo of the item (optional). Reply with an attachment now.",
            ephemeral=True
        )

        def check(m):
            return m.author == interaction.user and m.attachments

        try:
            msg = await bot.wait_for('message', check=check, timeout=60)
            photo_url = msg.attachments[0].url
        except Exception:
            photo_url = None

        if self.view_parent.edit:
            # Update existing item
            c.execute("""UPDATE inventory 
                         SET item_name=?, item_type=?, item_class=?, photo_url=?
                         WHERE user_id=? AND item_name=?""",
                      (self.view_parent.item_name,
                       self.view_parent.selected_type,
                       self.view_parent.selected_class,
                       photo_url,
                       self.view_parent.user_id,
                       self.view_parent.old_name))
            conn.commit()
            await interaction.followup.send("Item updated successfully ✅", ephemeral=True)
        else:
            # Insert new item
            c.execute("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)",
                      (self.view_parent.user_id,
                       self.view_parent.item_name,
                       self.view_parent.selected_type,
                       self.view_parent.selected_class,
                       photo_url))
            conn.commit()
            await interaction.followup.send("Item saved to your inventory ✅", ephemeral=True)

# --- Slash Commands ---
@bot.tree.command(name="additem", description="Add an item to your inventory")
async def additem(interaction: discord.Interaction):
    await interaction.response.send_modal(AddItemModal())

@bot.tree.command(name="showinventory", description="Show your inventory")
async def showinventory(interaction: discord.Interaction):
    c.execute("SELECT item_name, item_type, item_class, photo_url FROM inventory WHERE user_id=?",
              (interaction.user.id,))
    items = c.fetchall()
    if not items:
        await interaction.response.send_message("Your inventory is empty.", ephemeral=True)
        return

    embed = discord.Embed(title=f"{interaction.user.name}'s Inventory")
    for item_name, item_type, item_class, photo_url in items:
        desc = f"Type: {item_type}\nClass: {item_class}"
        embed.add_field(name=item_name, value=desc, inline=False)
        if photo_url:
            embed.set_thumbnail(url=photo_url)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Edit Item Flow ---
@bot.tree.command(name="edititem", description="Edit an item in your inventory")
async def edititem(interaction: discord.Interaction):
    c.execute("SELECT item_name FROM inventory WHERE user_id=?", (interaction.user.id,))
    items = [row[0] for row in c.fetchall()]
    if not items:
        await interaction.response.send_message("You have no items to edit.", ephemeral=True)
        return

    view = SelectItemToEditView(interaction.user.id, items)
    await interaction.response.send_message("Select an item to edit:", view=view, ephemeral=True)

class SelectItemToEditView(discord.ui.View):
    def __init__(self, user_id, items):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.select = discord.ui.Select(placeholder="Select an item",
                                        options=[discord.SelectOption(label=i) for i in items])
        self.select.callback = self.select_item
        self.add_item(self.select)

    async def select_item(self, interaction: discord.Interaction):
        old_name = self.select.values[0]
        modal = EditItemModal(old_name, self.user_id)
        await interaction.response.send_modal(modal)

class EditItemModal(discord.ui.Modal, title="Edit Item"):
    new_name = discord.ui.TextInput(label="New Item Name", placeholder="Enter new name")

    def __init__(self, old_name, user_id):
        super().__init__()
        self.old_name = old_name
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Select the new type/class for **{self.old_name}**:",
            view=TypeClassView(self.new_name.value, self.user_id, edit=True, old_name=self.old_name),
            ephemeral=True
        )

# --- Remove Item Flow ---
@bot.tree.command(name="removeitem", description="Remove an item from your inventory")
async def removeitem(interaction: discord.Interaction):
    c.execute("SELECT item_name FROM inventory WHERE user_id=?", (interaction.user.id,))
    items = [row[0] for row in c.fetchall()]
    if not items:
        await interaction.response.send_message("You have no items to remove.", ephemeral=True)
        return

    view = SelectItemToRemoveView(interaction.user.id, items)
    await interaction.response.send_message("Select an item to remove:", view=view, ephemeral=True)

class SelectItemToRemoveView(discord.ui.View):
    def __init__(self, user_id, items):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.select = discord.ui.Select(placeholder="Select an item",
                                        options=[discord.SelectOption(label=i) for i in items])
        self.select.callback = self.select_item
        self.add_item(self.select)

    async def select_item(self, interaction: discord.Interaction):
        item_name = self.select.values[0]
        c.execute("DELETE FROM inventory WHERE user_id=? AND item_name=?", (self.user_id, item_name))
        conn.commit()
        await interaction.response.send_message(f"Item **{item_name}** removed from your inventory ✅", ephemeral=True)

# --- Bot Ready ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(e)

# Replace with your bot token
bot.run(os.getenv("DISCORD_TOKEN"))


