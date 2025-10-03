import os
import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

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
    def __init__(self, author):
        super().__init__(timeout=None)
        self.author = author

        # Current state
        self.item_type = None
        self.subtype = None
        self.usable_classes = []
        self.item_name = ""
        self.stats = ""

        # 1️⃣ Item Type
        self.type_select = discord.ui.Select(
            placeholder="Select Item Type",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES]
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        # 2️⃣ Subtype
        self.subtype_select = discord.ui.Select(
            placeholder="Select Subtype",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label="Select type first")]
        )
        self.subtype_select.callback = self.select_subtype
        self.add_item(self.subtype_select)

        # 3️⃣ Classes (multi-select + All option)
        class_options = [discord.SelectOption(label="All")] + [discord.SelectOption(label=c) for c in CLASSES]
        self.classes_select = discord.ui.Select(
            placeholder="Select Usable Classes",
            min_values=1,
            max_values=len(class_options),
            options=class_options
        )
        self.classes_select.callback = self.select_classes
        self.add_item(self.classes_select)

        # 4️⃣ Item Details button
        self.details_button = discord.ui.Button(label="Add Item Details", style=discord.ButtonStyle.secondary)
        self.details_button.callback = self.open_item_details
        self.add_item(self.details_button)

        # 5️⃣ Submit
        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.success)
        self.submit_button.callback = self.submit_item
        self.add_item(self.submit_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("You can’t edit this entry.", ephemeral=True)
            return False
        return True

    # ---------------------------
    # Callbacks
    # ---------------------------
    async def select_type(self, interaction: discord.Interaction):
        new_type = interaction.data["values"][0]

        # Reset form if type changed
        if self.item_type and self.item_type != new_type:
            self.item_name = ""
            self.stats = ""
            self.subtype = None
            self.usable_classes = []

        # Update subtype options
        options = [discord.SelectOption(label=o) for o in SUBTYPES.get(new_type, ["None"])]
        self.subtype_select.options = options
        self.item_type = new_type

        await interaction.response.edit_message(view=self)

    async def select_subtype(self, interaction: discord.Interaction):
        self.subtype = interaction.data["values"][0]
        await interaction.response.edit_message(view=self)

    async def select_classes(self, interaction: discord.Interaction):
        selected = interaction.data["values"]
        if "All" in selected:
            self.usable_classes = ["All"]
            # reset select menu to show only All as selected
            options = [discord.SelectOption(label="All", default=True)] + [discord.SelectOption(label=c) for c in CLASSES]
            self.classes_select.options = options
        else:
            self.usable_classes = selected
        await interaction.response.edit_message(view=self)

    async def open_item_details(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ItemDetailsModal(self))

    async def submit_item(self, interaction: discord.Interaction):
        classes_str = ", ".join(self.usable_classes)
        msg = (
            f"**Item Name:** {self.item_name}\n"
            f"**Item Type:** {self.item_type} | **Subtype:** {self.subtype}\n"
            f"**Stats:** {self.stats}\n"
            f"**Usable by:** {classes_str}"
        )
        await interaction.response.send_message(f"Saved to Guild Bank:\n{msg}", ephemeral=True)
        self.stop()

# -------------------------------
# Command
# -------------------------------
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
async def add_item(interaction: discord.Interaction):
    view = ItemEntryView(interaction.user)
    await interaction.response.send_message("Fill in the item details below:", view=view, ephemeral=True)

# -------------------------------
# Events
# -------------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
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
