import os
import discord
from discord.ext import commands
import asyncpg

TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- CONFIG ----------------
ITEM_TYPES = ["Armor", "Crafting", "Misc", "Quest", "Potion", "Weapon"]
CLASSES = [
    "Archer","Bard","Beastmaster","Cleric","Druid","Elementalist",
    "Enchanter","Fighter","Inquisitor","Monk","Necromancer","Paladin",
    "Ranger","Rogue","Shadow Knight","Shaman","Spellblade","Wizard"
]
TYPES_WITH_STATS = {"Weapon","Armor","Potion"}

SUBTYPES = {
    "Armor": ["Plate", "Leather", "Chain"],
    "Weapon": ["Sword", "Axe", "Bow", "Dagger"],
    "Potion": ["Healing", "Mana", "Buff"],
    "Crafting": ["Materials"],
    "Misc": ["Misc"],
    "Quest": ["Quest"]
}

db_conn = None

# ---------------- MODAL FOR DRAFT STATS ----------------
class StatsModalDraft(discord.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(title=f"{view_ref.item_type}: {view_ref.subtype} Stats")
        self.view_ref = view_ref

        # Add fields based on item type
        stats = view_ref.stats or {}
        if view_ref.item_type == "Weapon":
            self.attack = discord.ui.TextInput(label="Attack", default=stats.get("Attack",""))
            self.delay = discord.ui.TextInput(label="Delay", default=stats.get("Delay",""))
            self.add_item(self.attack)
            self.add_item(self.delay)
        elif view_ref.item_type == "Armor":
            self.defense = discord.ui.TextInput(label="Defense", default=stats.get("Defense",""))
            self.weight = discord.ui.TextInput(label="Weight", default=stats.get("Weight",""))
            self.add_item(self.defense)
            self.add_item(self.weight)
        elif view_ref.item_type == "Potion":
            self.effect = discord.ui.TextInput(label="Effect", default=stats.get("Effect",""))
            self.duration = discord.ui.TextInput(label="Duration", default=stats.get("Duration",""))
            self.add_item(self.effect)
            self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):
        # Save stats in draft view
        self.view_ref.stats = {child.label: child.value for child in self.children}
        await interaction.response.send_message("✅ Stats updated! You can continue editing or click Submit.", ephemeral=True)

# ---------------- VIEW FOR DRAFT ENTRY ----------------
class ItemEntryView(discord.ui.View):
    def __init__(self, item_name, author):
        super().__init__(timeout=300)
        self.item_name = item_name
        self.author = author

        # Draft state
        self.item_type = None
        self.subtype = None
        self.stats = None
        self.usable_classes = []

        # Item Type
        self.type_select = discord.ui.Select(
            placeholder="Select Item Type",
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES],
            min_values=1,
            max_values=1
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        # Subtype
        self.subtype_select = discord.ui.Select(
            placeholder="Select Subtype",
            options=[],
            min_values=1,
            max_values=1
        )
        self.subtype_select.callback = self.select_subtype
        self.add_item(self.subtype_select)

        # Usable Classes
        self.classes_select = discord.ui.Select(
            placeholder="Select Usable Classes",
            options=[discord.SelectOption(label=c) for c in CLASSES],
            min_values=1,
            max_values=len(CLASSES)
        )
        self.classes_select.callback = self.select_classes
        self.add_item(self.classes_select)

        # Stats button
        self.stats_button = discord.ui.Button(label="Edit Stats", style=discord.ButtonStyle.primary)
        self.stats_button.callback = self.open_stats_modal
        self.add_item(self.stats_button)

        # Submit button
        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.success)
        self.submit_button.callback = self.submit_item
        self.add_item(self.submit_button)

    async def select_type(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)
        self.item_type = interaction.data["values"][0]
        # Update subtype options
        options = SUBTYPES.get(self.item_type, ["None"])
        self.subtype_select.options = [discord.SelectOption(label=o) for o in options]
        await interaction.response.edit_message(view=self)

    async def select_subtype(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)
        self.subtype = interaction.data["values"][0]
        await interaction.response.edit_message(view=self)

    async def select_classes(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)
        self.usable_classes = interaction.data["values"]
        await interaction.response.edit_message(view=self)

    async def open_stats_modal(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)
        if not self.item_type or not self.subtype:
            return await interaction.response.send_message("Select Type and Subtype first!", ephemeral=True)
        modal = StatsModalDraft(self)
        await interaction.response.send_modal(modal)

    async def submit_item(self, interaction: discord.Interaction):
        if not all([self.item_type, self.subtype, self.usable_classes]):
            return await interaction.response.send_message("Complete all fields first!", ephemeral=True)
        stats_str = "; ".join([f"{k}: {v}" for k,v in (self.stats or {}).items()]) if self.stats else None
        await db_conn.execute(
            "INSERT INTO inventory(item_name,item_type,subtype,item_class,stats,photo_url) VALUES($1,$2,$3,$4,$5,$6)",
            self.item_name, self.item_type, self.subtype, ",".join(self.usable_classes), stats_str, None
        )
        await interaction.response.send_message(f"✅ **{self.item_name}** added to the Guild Bank!", ephemeral=True)
        self.stop()

# ---------------- COMMANDS ----------------
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
async def add_item(interaction: discord.Interaction, name: str):
    view = ItemEntryView(name, interaction.user)
    await interaction.response.send_message(f"Adding item: **{name}**", view=view, ephemeral=True)

@bot.tree.command(name="view_items", description="View the Guild Bank")
async def view_items(interaction: discord.Interaction):
    rows = await db_conn.fetch("SELECT item_name,item_type,subtype,item_class,stats FROM inventory")
    if not rows:
        return await interaction.response.send_message("The Guild Bank is empty.", ephemeral=True)

    sorted_rows = sorted(rows, key=lambda r: r["item_name"].lower())
    desc_lines = []
    for r in sorted_rows:
        classes_sorted = sorted(r["item_class"].split(",")) if r["item_class"] else []
        stats_str = r["stats"] or "None"
        subtype_str = r["subtype"] or ""
        line = f"{r['item_name']} | {r['item_type']}: {subtype_str} | Stats: {stats_str} | Usable By: {', '.join(classes_sorted)}"
        desc_lines.append(line)
    embed = discord.Embed(title="Guild Bank", description="\n".join(desc_lines))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete_item", description="Delete an item from the Guild Bank")
async def delete_item(interaction: discord.Interaction, item_name: str):
    await db_conn.execute("DELETE FROM inventory WHERE item_name=$1", item_name)
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}** from the Guild Bank.", ephemeral=True)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    global db_conn
    if db_conn is None:
        db_conn = await asyncpg.connect(DATABASE_URL)
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                item_name TEXT,
                item_type TEXT,
                subtype TEXT,
                item_class TEXT,
                stats TEXT,
                photo_url TEXT
            )
        """)
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
