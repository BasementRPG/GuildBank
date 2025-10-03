import discord
from discord.ext import commands
from discord import app_commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ── Constants ────────────────────────────────────────────────
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
    "All", "Archer", "Bard", "Beastmaster", "Cleric", "Druid", "Elementalist",
    "Enchanter", "Fighter", "Inquisitor", "Monk", "Necromancer", "Paladin",
    "Ranger", "Rogue", "Shadow Knight", "Shaman", "Spellblade", "Wizard"
]


# ── Modal for stats ──────────────────────────────────────────
class StatsModal(discord.ui.Modal, title="Enter Item Stats"):
    attack = discord.ui.TextInput(label="Attack", required=False)
    delay = discord.ui.TextInput(label="Delay", required=False)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.stats = f"Attack: {self.attack.value} | Delay: {self.delay.value}"
        await interaction.response.send_message("Stats saved.", ephemeral=True)


# ── Main view ────────────────────────────────────────────────
class ItemEntryView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=None)
        self.author = author

        # current selections
        self.item_type = None
        self.subtype = None
        self.usable_classes = []
        self.stats = ""

        # build dropdowns
        self.type_select = discord.ui.Select(
            placeholder="Select Item Type",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES]
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        self.subtype_select = discord.ui.Select(
            placeholder="Select Subtype",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label="Select type first")]
        )
        self.subtype_select.callback = self.select_subtype
        self.add_item(self.subtype_select)

        self.classes_select = discord.ui.Select(
            placeholder="Select Usable Classes",
            min_values=1, max_values=len(CLASSES),
            options=[discord.SelectOption(label=c) for c in CLASSES]
        )
        self.classes_select.callback = self.select_classes
        self.add_item(self.classes_select)

        # buttons
        self.add_item(discord.ui.Button(label="Add Stats", style=discord.ButtonStyle.secondary, custom_id="addstats"))
        self.children[-1].callback = self.open_stats

        self.add_item(discord.ui.Button(label="Submit", style=discord.ButtonStyle.success, custom_id="submit"))
        self.children[-1].callback = self.submit_item

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("You can’t edit this entry.", ephemeral=True)
            return False
        return True

    async def select_type(self, interaction: discord.Interaction):
        self.item_type = interaction.data["values"][0]
        # update subtype options dynamically
        options = SUBTYPES.get(self.item_type, ["None"])
        self.subtype_select.options = [discord.SelectOption(label=o) for o in options]
        self.subtype = None
        await interaction.response.defer(ephemeral=True)

    async def select_subtype(self, interaction: discord.Interaction):
        self.subtype = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)

    async def select_classes(self, interaction: discord.Interaction):
        selected = interaction.data["values"]
        if "All" in selected:
            self.usable_classes = ["All"]
        else:
            self.usable_classes = selected
        await interaction.response.defer(ephemeral=True)

    async def open_stats(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StatsModal(self))

    async def submit_item(self, interaction: discord.Interaction):
        # Insert into DB here — you have self.item_type, self.subtype, self.usable_classes, self.stats
        # Example:
        # await db.execute("INSERT INTO inventory (item_type, subtype, classes, stats) VALUES ($1,$2,$3,$4)",
        #                  self.item_type, self.subtype, self.usable_classes, self.stats)

        classes_str = ", ".join(self.usable_classes)
        msg = (
            f"**Item Type:** {self.item_type}\n"
            f"**Subtype:** {self.subtype}\n"
            f"**Stats:** {self.stats}\n"
            f"**Usable by:** {classes_str}"
        )
        await interaction.response.send_message(f"Saved to Guild Bank:\n{msg}", ephemeral=True)
        self.stop()


# ── Command ─────────────────────────────────────────────────
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
async def add_item(interaction: discord.Interaction):
    view = ItemEntryView(interaction.user)
    await interaction.response.send_message("Fill in the item details below:", view=view, ephemeral=True)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(e)


bot.run("YOUR_TOKEN_HERE")
