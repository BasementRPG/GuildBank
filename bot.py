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
    "Archer", "Bard", "Beastmaster", "Cleric", "Druid", "Elementalist",
    "Enchanter", "Fighter", "Inquisitor", "Monk", "Necromancer", "Paladin",
    "Ranger", "Rogue", "Shadow Knight", "Shaman", "Spellblade", "Wizard"
]

db_conn = None  # will initialize in on_ready

# ---------------- STATS MODAL ----------------
class ItemStatsModal(discord.ui.Modal):
    def __init__(self, item_name, item_types, item_classes):
        super().__init__(title=f"Enter Stats for {item_name}")
        self.item_name = item_name
        self.item_types = item_types
        self.item_classes = item_classes

        # Dynamic fields based on item type
        if "Weapon" in item_types:
            self.attack = discord.ui.TextInput(label="Attack", placeholder="Enter Attack value", required=True)
            self.delay = discord.ui.TextInput(label="Delay", placeholder="Enter Delay value", required=True)
            self.add_item(self.attack)
            self.add_item(self.delay)
        if "Armor" in item_types:
            self.defense = discord.ui.TextInput(label="Defense", placeholder="Enter Defense value", required=True)
            self.weight = discord.ui.TextInput(label="Weight", placeholder="Enter Weight value", required=True)
            self.add_item(self.defense)
            self.add_item(self.weight)
        if "Potion" in item_types:
            self.effect = discord.ui.TextInput(label="Effect", placeholder="Enter Effect", required=True)
            self.duration = discord.ui.TextInput(label="Duration", placeholder="Enter Duration value", required=True)
            self.add_item(self.effect)
            self.add_item(self.duration)
        # Add more types/stats as needed

    async def on_submit(self, interaction: discord.Interaction):
        stats = {field.label: field.value for field in self.children}
        stats_str = "; ".join([f"{k}: {v}" for k, v in stats.items()])

        await db_conn.execute(
            "INSERT INTO inventory(item_name,item_type,item_class,stats,photo_url) VALUES($1,$2,$3,$4,$5)",
            self.item_name,
            ",".join(self.item_types),
            ",".join(self.item_classes),
            stats_str,
            None
        )

        await interaction.response.send_message(
            f"✅ Added **{self.item_name}** ({', '.join(sorted(self.item_types))} - {', '.join(sorted(self.item_classes))}) with stats: {stats_str} to the Guild Bank.",
            ephemeral=True
        )

# ---------------- VIEW FOR MULTI-SELECT DROPDOWNS ----------------
class AddItemView(discord.ui.View):
    def __init__(self, item_name, author):
        super().__init__(timeout=120)
        self.item_name = item_name
        self.author = author
        self.item_types = []
        self.item_classes = []

        # Multi-select for Item Types
        self.type_select = discord.ui.Select(
            placeholder="Choose Item Type(s)",
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES],
            min_values=1,
            max_values=len(ITEM_TYPES)
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        # Multi-select for Classes
        self.class_select = discord.ui.Select(
            placeholder="Choose Class(es)",
            options=[discord.SelectOption(label=c) for c in CLASSES],
            min_values=1,
            max_values=len(CLASSES)
        )
        self.class_select.callback = self.select_class
        self.add_item(self.class_select)

    async def select_type(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("This is not your selection!", ephemeral=True)
        self.item_types = interaction.data["values"]
        await self.check_complete(interaction)

    async def select_class(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("This is not your selection!", ephemeral=True)
        self.item_classes = interaction.data["values"]
        await self.check_complete(interaction)

    async def check_complete(self, interaction: discord.Interaction):
        if self.item_types and self.item_classes:
            # Directly show the modal; no prior response sent
            await interaction.response.send_modal(
                ItemStatsModal(self.item_name, self.item_types, self.item_classes)
            )
            self.stop()

# ---------------- COMMANDS ----------------
@bot.tree.command(name="add_item", description="Add an item to the Guild Bank")
async def add_item(interaction: discord.Interaction, name: str):
    view = AddItemView(name, interaction.user)
    await interaction.response.send_message(f"Adding item: **{name}**. Choose type(s) and class(es):", view=view, ephemeral=True)

@bot.tree.command(name="view_items", description="View the Guild Bank")
async def view_items(interaction: discord.Interaction):
    rows = await db_conn.fetch("SELECT item_name,item_type,item_class,stats FROM inventory")
    if not rows:
        await interaction.response.send_message("The Guild Bank is empty.", ephemeral=True)
        return

    sorted_rows = sorted(rows, key=lambda r: r["item_name"].lower())
    desc_lines = []
    for r in sorted_rows:
        types_sorted = sorted(r["item_type"].split(",")) if r["item_type"] else []
        classes_sorted = sorted(r["item_class"].split(",")) if r["item_class"] else []
        stats_display = f" | Stats: {r['stats']}" if r.get("stats") else ""
        desc_lines.append(f"- {r['item_name']} ({', '.join(types_sorted)} - {', '.join(classes_sorted)}){stats_display}")

    embed = discord.Embed(title="Guild Bank", description="\n".join(desc_lines))
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="delete_item", description="Delete an item from the Guild Bank")
async def delete_item(interaction: discord.Interaction, item_name: str):
    await db_conn.execute("DELETE FROM inventory WHERE item_name=$1", item_name)
    await interaction.response.send_message(f"🗑️ Deleted **{item_name}** from the Guild Bank.", ephemeral=True)

@bot.tree.command(name="update_item", description="Update an item in the Guild Bank")
async def update_item(interaction: discord.Interaction, old_name: str, new_name: str, new_types: str, new_classes: str, new_stats: str = None):
    types_list = [t.strip() for t in new_types.split(",") if t.strip() in ITEM_TYPES]
    classes_list = [c.strip() for c in new_classes.split(",") if c.strip() in CLASSES]

    if not types_list or not classes_list:
        await interaction.response.send_message("Invalid type(s) or class(es).", ephemeral=True)
        return

    await db_conn.execute(
        """UPDATE inventory
           SET item_name=$1, item_type=$2, item_class=$3, stats=$4
           WHERE item_name=$5""",
        new_name, ",".join(types_list), ",".join(classes_list), new_stats, old_name
    )
    await interaction.response.send_message(
        f"🔄 Updated **{old_name}** to **{new_name}** ({', '.join(types_list)} - {', '.join(classes_list)}) in the Guild Bank.",
        ephemeral=True
    )

# ---------------- READY EVENT ----------------
@bot.event
async def on_ready():
    global db_conn
    if db_conn is None:
        db_conn = await asyncpg.connect(DATABASE_URL)
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                item_name TEXT,
                item_type TEXT,
                item_class TEXT,
                stats TEXT,
                photo_url TEXT
            )
        """)
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

bot.run(TOKEN)
