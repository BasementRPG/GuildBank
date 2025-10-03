import discord
from discord.ext import commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory inventory: {user_id: [items]}
inventory = {}

# Predefined dropdown choices
ITEM_TYPES = ["Weapon", "Armor", "Potion", "Misc"]
CLASSES = ["Warrior", "Mage", "Rogue", "Cleric"]

class AddItemModal(discord.ui.Modal, title="Add Item"):
    item_name = discord.ui.TextInput(label="Item Name", placeholder="Enter item name")

    async def on_submit(self, interaction: discord.Interaction):
        # We’ll store the item type/class separately (selected in dropdown)
        await interaction.response.send_message(
            "Please select the item type and class from the dropdown below.",
            view=TypeClassView(self.item_name.value),
            ephemeral=True
        )

class TypeClassView(discord.ui.View):
    def __init__(self, item_name):
        super().__init__(timeout=60)
        self.item_name = item_name
        # Dropdown for item types
        self.type_select = discord.ui.Select(
            placeholder="Select Item Type",
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES]
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        # Dropdown for classes
        self.class_select = discord.ui.Select(
            placeholder="Select Class",
            options=[discord.SelectOption(label=c) for c in CLASSES]
        )
        self.class_select.callback = self.select_class
        self.add_item(self.class_select)

        # Button for optional photo
        self.add_item(UploadPhotoButton(item_name))

    async def select_type(self, interaction: discord.Interaction):
        self.selected_type = self.type_select.values[0]
        await interaction.response.send_message(
            f"Item type selected: {self.selected_type}", ephemeral=True)

    async def select_class(self, interaction: discord.Interaction):
        self.selected_class = self.class_select.values[0]
        await interaction.response.send_message(
            f"Class selected: {self.selected_class}", ephemeral=True)

class UploadPhotoButton(discord.ui.Button):
    def __init__(self, item_name):
        super().__init__(label="Upload Photo (Optional)", style=discord.ButtonStyle.primary)
        self.item_name = item_name

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Upload a photo of the item (optional). Just attach it in your next message.",
            ephemeral=True)

@bot.tree.command(name="additem", description="Add an item to your inventory")
async def additem(interaction: discord.Interaction):
    """Slash command entry point"""
    await interaction.response.send_modal(AddItemModal())

@bot.tree.command(name="showinventory", description="Show your inventory")
async def showinventory(interaction: discord.Interaction):
    user_id = interaction.user.id
    items = inventory.get(user_id, [])
    if not items:
        await interaction.response.send_message("Your inventory is empty.", ephemeral=True)
    else:
        formatted = "\n".join([f"- {item}" for item in items])
        await interaction.response.send_message(f"Your inventory:\n{formatted}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)

# Replace with your bot token
bot.run(os.getenv("DISCORD_TOKEN"))




