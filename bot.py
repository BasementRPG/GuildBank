class ItemEntryView(discord.ui.View):
    def __init__(self, item_name, author):
        super().__init__(timeout=300)
        self.item_name = item_name
        self.author = author

        self.item_type = None
        self.subtype = None
        self.stats = None
        self.usable_classes = []

        # ---------------- Item Type ----------------
        self.type_select = discord.ui.Select(
            placeholder="Select Item Type",
            options=[discord.SelectOption(label=t) for t in ITEM_TYPES],
            min_values=1,
            max_values=1,
        )
        self.type_select.callback = self.select_type
        self.add_item(self.type_select)

        # ---------------- Subtype ----------------
        self.subtype_select = discord.ui.Select(
            placeholder="Select Subtype",
            options=[discord.SelectOption(label="Select Type First")],
            min_values=1,
            max_values=1,
        )
        self.subtype_select.callback = self.select_subtype
        self.add_item(self.subtype_select)

        # ---------------- Usable Classes ----------------
        class_options = [discord.SelectOption(label="All")] + [discord.SelectOption(label=c) for c in CLASSES]
        self.classes_select = discord.ui.Select(
            placeholder="Select Usable Classes",
            options=class_options,
            min_values=1,
            max_values=len(class_options),
        )
        self.classes_select.callback = self.select_classes
        self.add_item(self.classes_select)

        # ---------------- Stats Button ----------------
        self.stats_button = discord.ui.Button(label="Edit Stats", style=discord.ButtonStyle.primary)
        self.stats_button.callback = self.open_stats_modal
        self.add_item(self.stats_button)

        # ---------------- Submit Button ----------------
        self.submit_button = discord.ui.Button(label="Submit", style=discord.ButtonStyle.success)
        self.submit_button.callback = self.submit_item
        self.add_item(self.submit_button)

    # ---------------- CALLBACKS ----------------
    async def select_type(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)

        self.item_type = interaction.data["values"][0]

        # Update Subtype options based on selected type
        options = SUBTYPES.get(self.item_type, ["None"])
        self.subtype_select.options = [discord.SelectOption(label=o) for o in options]

        # Keep current subtype if it exists in new options, else reset
        if self.subtype not in options:
            self.subtype = None
            self.subtype_select.placeholder = "Select Subtype"

        await interaction.response.edit_message(view=self)

    async def select_subtype(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)
        self.subtype = interaction.data["values"][0]
        await interaction.response.edit_message(view=self)

    async def select_classes(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)

        selected = interaction.data["values"]
        if "All" in selected:
            self.usable_classes = ["All"]
            # Deselect other classes visually
            self.classes_select.values = ["All"]
        else:
            self.usable_classes = selected
        await interaction.response.edit_message(view=self)

    async def open_stats_modal(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("Not your entry!", ephemeral=True)
        if not self.item_type or not self.subtype:
            return await interaction.response.send_message("Select Type and Subtype first!", ephemeral=True)
        modal = StatsModal(self)
        await interaction.response.send_modal(modal)

    async def submit_item(self, interaction: discord.Interaction):
        if not all([self.item_type, self.subtype, self.usable_classes]):
            return await interaction.response.send_message("Complete all fields first!", ephemeral=True)

        stats_str = "; ".join([f"{k}: {v}" for k,v in (self.stats or {}).items()]) if self.stats else None
        await db_conn.execute(
            "INSERT INTO inventory(item_name,item_type,subtype,item_class,stats,photo_url) VALUES($1,$2,$3,$4,$5,$6)",
            self.item_name,
            self.item_type,
            self.subtype,
            ",".join(self.usable_classes),
            stats_str,
            None
        )
        await interaction.response.send_message(f"✅ **{self.item_name}** added to the Guild Bank!", ephemeral=True)
        self.stop()
