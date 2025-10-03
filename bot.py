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

# --- UI Components ---
class AddItemModal(discord.ui.Modal, title="Add Item"):
    item_name = discord.ui.TextInput(label="Item Name", placeholder="Enter item name")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Select the item type and class below:", 
            view=TypeClassView(self.item_name.value, interaction.user.id), 
            ephemeral=True
        )

class TypeClassView(discord.ui.View):
    def __init__(self, item_name, user_id):
        super().__init__(timeout=120)
        self.item_name = item_name
        self.user_id = user_id
        self.selected_type = None
        self.selected_class = None

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

        # Save to DB
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
        if photo_url:
            embed.add_field(name=item_name, value=desc, inline=False)
            embed.set_thumbnail(url=photo_url)
        else:
            embed.add_field(name=item_name, value=desc, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

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





