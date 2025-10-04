# ---------- Read-Only Modal ----------
class ReadOnlyDetailsModal(discord.ui.Modal):
    def __init__(self, title_text: str, body_text: str):
        super().__init__(title=title_text)
        # Text input is required in a modal, we disable it for read-only
        self.details = discord.ui.TextInput(
            label="Details",
            style=discord.TextStyle.paragraph,
            default=body_text,
            required=False,
            max_length=4000
        )
        self.details.disabled = True  # make it read-only
        self.add_item(self.details)

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
        modal = ReadOnlyDetailsModal(title_text=self.item_row['name'], body_text=details_text)
        await interaction.response.send_modal(modal)

# ---------- /view_bank Command ----------
@bot.tree.command(name="view_bank", description="View all items in the guild bank.")
async def view_bank(interaction: discord.Interaction):
    rows = await get_all_items()
    if not rows:
        await interaction.response.send_message("Guild bank is empty.", ephemeral=True)
        return

    # Sort items alphabetically
    sorted_rows = sorted(rows, key=lambda r: r['name'].lower())

    # Send one message per item
    for row in sorted_rows:
        embed = discord.Embed(
            title=row["name"],
            description=f"{row['type']} | {row['subtype']}",
            color=discord.Color.blue()
        )
        view = discord.ui.View()
        view.add_item(ViewDetailsButton(item_row=row))

        await interaction.channel.send(embed=embed, view=view)
    
    # Optionally, acknowledge the command ephemerally
    await interaction.response.send_message(f"✅ Sent {len(sorted_rows)} items.", ephemeral=True)
