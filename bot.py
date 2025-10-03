import discord
from discord.ext import commands
import json
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

ITEMS_FILE = "items.json"

def load_items():
    if not os.path.exists(ITEMS_FILE):
        with open(ITEMS_FILE, "w") as f:
            json.dump([], f)
    with open(ITEMS_FILE, "r") as f:
        return json.load(f)

def save_items(items):
    with open(ITEMS_FILE, "w") as f:
        json.dump(items, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command()
async def add_item(ctx):
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("Enter item name:")
    name = (await bot.wait_for("message", check=check)).content

    await ctx.send("Enter item type:")
    item_type = (await bot.wait_for("message", check=check)).content

    await ctx.send("Enter item stats as key:value (comma-separated), e.g., `attack:10,defense:5`")
    stats_msg = (await bot.wait_for("message", check=check)).content
    stats = dict(stat.split(":") for stat in stats_msg.split(","))

    await ctx.send("Enter usable classes (comma-separated):")
    classes = (await bot.wait_for("message", check=check)).content.split(",")

    await ctx.send("Upload an image or provide a direct image URL:")

    img_msg = await bot.wait_for("message", check=check)

    if img_msg.attachments:
        image_url = img_msg.attachments[0].url
    else:
        image_url = img_msg.content.strip()

    item = {
        "name": name,
        "type": item_type,
        "stats": stats,
        "classes": classes,
        "image": image_url
    }

    items = load_items()
    items.append(item)
    save_items(items)

    await ctx.send(f"Item '{name}' added successfully!")

@bot.command()
async def view_items(ctx):
    items = load_items()
    if not items:
        await ctx.send("No items found.")
        return

    for item in items:
        embed = discord.Embed(title=item["name"], description=f"Type: {item['type']}")
        stats = "\n".join([f"**{k}**: {v}" for k, v in item["stats"].items()])
        embed.add_field(name="Stats", value=stats, inline=False)
        embed.add_field(name="Usable by", value=", ".join(item["classes"]), inline=False)
        embed.set_image(url=item["image"])
        await ctx.send(embed=embed)

# Replace with your bot token
bot.run("YMTQyMzYwNTU5MjgxMTExMDQxMA.G1LePs.34i7FTUYHl1R2eKAhuuEk6tWWpciidAmrNwT9Y")

