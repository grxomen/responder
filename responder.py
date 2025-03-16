import discord
import random
import os
import asyncio
from datetime import datetime
from discord.ext import commands
from pymongo import MongoClient

# MongoDB Setup
MONGO_URL = "YOUR_MONGO_CONNECTION_STRING"
client = MongoClient(MONGO_URL)
db = client["DiscordBot"]
messages_collection = db["Messages"]

# Discord Bot Setup
TOKEN = "YOUR_BOT_TOKEN"

intents = discord.Intents.default()
intents.messages = True

bot = commands.Bot(command_prefix="_", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

@bot.command()
async def repeat(ctx, *, message: str):
    """ Sends an embedded message and stores it in MongoDB """

    # Randomly choose a color
    color = random.choice([0x000000, 0xB0C0FF])
    
    # Create an embed
    embed = discord.Embed(title="Echo", description=message, color=color)
    embed.set_footer(text=f"Sent by {ctx.author.name} at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # Send the embed
    msg = await ctx.send(embed=embed)

    # Store in MongoDB
    message_data = {
        "message_id": msg.id,
        "user": ctx.author.name,
        "content": message,
        "color": color,
        "channel": ctx.channel.name,
        "timestamp": datetime.utcnow()
    }
    messages_collection.insert_one(message_data)

@bot.command()
async def history(ctx, page: int = 1):
    """ Fetches paginated message history from MongoDB """
    messages_per_page = 5
    total_messages = messages_collection.count_documents({})
    total_pages = (total_messages // messages_per_page) + (1 if total_messages % messages_per_page else 0)

    if page < 1 or page > total_pages:
        await ctx.send(f"Invalid page number! There are {total_pages} pages available.")
        return

    messages = list(messages_collection.find().skip((page - 1) * messages_per_page).limit(messages_per_page))
    
    embed = discord.Embed(title=f"Message History (Page {page}/{total_pages})", color=0xB0C0FF)

    for msg in messages:
        timestamp = msg["timestamp"].strftime('%Y-%m-%d %H:%M:%S')
        embed.add_field(name=f"{msg['user']} (at {timestamp} UTC)", value=f'"{msg["content"]}" in #{msg["channel"]}', inline=False)

    msg = await ctx.send(embed=embed)

    if total_pages > 1:
        await msg.add_reaction("⬅️")
        await msg.add_reaction("➡️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"]

        while True:
            try:
                reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == "⬅️" and page > 1:
                    page -= 1
                elif str(reaction.emoji) == "➡️" and page < total_pages:
                    page += 1
                else:
                    continue

                messages = list(messages_collection.find().skip((page - 1) * messages_per_page).limit(messages_per_page))

                embed = discord.Embed(title=f"Message History (Page {page}/{total_pages})", color=0xB0C0FF)
                for msg in messages:
                    timestamp = msg["timestamp"].strftime('%Y-%m-%d %H:%M:%S')
                    embed.add_field(name=f"{msg['user']} (at {timestamp} UTC)", value=f'"{msg["content"]}" in #{msg["channel"]}', inline=False)

                await msg.edit(embed=embed)

                await msg.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                break

@bot.command()
async def edit_message(ctx, message_id: int, *, new_content: str):
    """ Edits a stored message in MongoDB and updates the embed in Discord """
    message_data = messages_collection.find_one({"message_id": message_id})

    if not message_data:
        await ctx.send("Message not found!")
        return

    # Update message content in MongoDB
    messages_collection.update_one({"message_id": message_id}, {"$set": {"content": new_content}})

    # Fetch the original message and edit it
    channel = discord.utils.get(ctx.guild.text_channels, name=message_data["channel"])
    if channel:
        try:
            msg = await channel.fetch_message(message_id)

            embed = discord.Embed(title="Echo (Edited)", description=new_content, color=message_data["color"])
            embed.set_footer(text=f"Edited by {ctx.author.name} at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

            await msg.edit(embed=embed)
            await ctx.send(f"Message {message_id} has been updated!")

        except discord.NotFound:
            await ctx.send("Could not find the original message in the channel.")
    else:
        await ctx.send("Channel not found!")

@bot.command()
async def clear_history(ctx):
    """ Clears all stored messages from MongoDB """
    messages_collection.delete_many({})
    await ctx.send("Message history cleared!")

@bot.command()
async def delete_message(ctx, message_id: int):
    """ Deletes a specific message from MongoDB and Discord """
    message_data = messages_collection.find_one({"message_id": message_id})

    if not message_data:
        await ctx.send("Message not found!")
        return

    # Delete from MongoDB
    messages_collection.delete_one({"message_id": message_id})

    # Delete from Discord
    channel = discord.utils.get(ctx.guild.text_channels, name=message_data["channel"])
    if channel:
        try:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
            await ctx.send(f"Message {message_id} has been deleted!")
        except discord.NotFound:
            await ctx.send("Could not find the original message in the channel.")
    else:
        await ctx.send("Channel not found!")

# Run the bot
bot.run(TOKEN)