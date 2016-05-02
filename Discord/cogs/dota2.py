import re

import discord.utils
from discord.ext import commands

from .utils import checks, formats, steamapi
from lxml import html
import requests

import json


class Dota2:
    """Dota 2 related commands"""

    def __init__(self, bot):
        self.bot = bot
        self.steam_api = steamapi.SteamAPI(bot.steam_api_key)
        with open("Dota/heroes.json", 'r') as f:
            self.heroes = json.load(f)['result']['heroes']
        with open("Dota/items.json", 'r') as f:
            self.items = json.load(f)['result']['items']
        with open("Dota/lobbies.json", 'r') as f:
            self.lobbies = json.load(f)['lobbies']
        with open("Dota/modes.json", 'r') as f:
            self.modes = json.load(f)['modes']
        with open("Dota/regions.json", 'r') as f:
            self.regions = json.load(f)['regions']

    @commands.command(hidden=True)
    @checks.is_owner()
    async def update_heroes(self):
        heroes = self.steam_api.get_heroes()

        with open("Dota/heroes.json", 'w') as f:
            json.dump(heroes, f, ensure_ascii=True, indent=4)

        self.heroes = heroes

    @commands.command(hidden=True)
    @checks.is_owner()
    async def update_items(self):
        items = self.steam_api.get_game_items()

        with open("Dota/items.json", 'w') as f:
            json.dump(items, f, ensure_ascii=True, indent=4)

    @commands.command(pass_context=True)
    async def dotabuff(self, ctx, *, member: discord.Member=None):
        """Dotabuff profile links

        Links the Dotabuff pages for the linked Steam accounts of
        the requested member. If no member is specified then the
        info returned is for the user that invoked the command."""
        if member is None:
            member = ctx.message.author

        steam_ids = self.bot.steam_info.get(member.id)

        if steam_ids is None:
            await self.bot.say("{0.name} has not linked their Steam account to MT5ABot.".format(member))
            return

        msg = "Dotabuff page(s) for {0.name}:\n\n".format(member)
        response = self.steam_api.get_player_summaries(steam_ids)['response']
        # Response isn't in a guaranteed order.
        for steam_id in steam_ids:
            for player in response['players']:
                if player['steamid'] == steam_id:
                    dota_id = int(steam_id) - steamapi.ID.STEAM_TO_DOTA_CONSTANT
                    msg += "{0} - <https://dotabuff.com/players/{1}>\n".format(player['personaname'], dota_id)
        await self.bot.say(msg)

    def get_latest_match(self, steam_id):
        try:
            req = self.steam_api.get_match_history(account_id=steam_id, matches_requested=1)
            print(req)
            result = req['result']
        except:
            print("uh")
            return None

        if result['status'] == 15:
            return {}

        elif result['num_results'] == 0:
            return {}

        return result['matches'][0]

    def get_latest_match_from_list(self, steam_ids):
        latest_match = {}

        for steam_id in steam_ids:
            match = self.get_latest_match(steam_id)
            if match is None:
                return None
            if not match == {} and (latest_match == {} or latest_match['match_seq_num'] < match['match_seq_num']):
                latest_match = match

        return latest_match

    def get_hero_name(self, i):
        for hero in self.heroes:
            if hero['id'] == i:
                return hero['localized_name']
        return 'Unknown Hero'

    def get_item_name(self, i):
        for item in self.items:
            if item['id'] == i:
                return item['localized_name']
        return 'Unknown Item'

    def get_lobby_name(self, i):
        for lobby in self.lobbies:
            if lobby['id'] == i:
                return lobby['name']
        return 'Unknown Lobby Type'

    def get_mode_name(self, i):
        for mode in self.modes:
            if mode['id'] == i:
                return mode['name']
        return 'Unknown Game Mode'

    def get_region_name(self, i):
        for region in self.regions:
            if region['id'] == i:
                return region['name']
        return 'Unknown Matchmaking Region'

    def get_game_length(self, duration):
        minutes = int(duration / 60)
        seconds = int(duration % 60)
        return "{0}:{1}".format(minutes, str(seconds).zfill(2))

    def get_player_blurb(self, player):
        dota_id = player['account_id']

        name = None
        for server in self.bot.servers:
            for member in server.members:
                steam_ids = self.bot.steam_info.get(member.id)
                if steam_ids is not None:
                    for steam_id in steam_ids:
                        if dota_id == int(steam_id) - steamapi.ID.STEAM_TO_DOTA_CONSTANT:
                            name = member.name
                            break

        if name is None:
            return None

        hero_name = self.get_hero_name(player['hero_id'])
        return ("__Player -- {0}__\n"
                "Hero -- {1}\n"
                "Level -- {2}\n"
                "K/D/A -- {3}/{4}/{5}\n"
                "GPM -- {6}\n\n".format(name, hero_name, player['level'], player['kills'],
                                    player['deaths'], player['assists'], player['gold_per_min']))

    def parse_match(self, match):
        result = self.steam_api.get_match_details(match['match_id'])
        try:
            match_info = result['result']
        except KeyError:
            print(result)
            return None

        lobby_name = self.get_lobby_name(match_info['lobby_type'])
        mode_name = self.get_mode_name(match_info['game_mode'])
        region_name = self.get_region_name(match_info['cluster'])
        game_length = self.get_game_length(match_info['duration'])
        winning_team = "Radiant" if match_info['radiant_win'] else "Dire"

        match_string = ''
        match_string += "Lobby Type -- {0}\n".format(lobby_name)
        match_string += "Game Mode -- {0}\n".format(mode_name)
        match_string += "Region -- {0}\n".format(region_name)
        match_string += "Duration -- {0}\n".format(game_length)
        match_string += "Winning Team -- {0}\n\n".format(winning_team)

        match_string += "<http://www.dotabuff.com/matches/{0}>\n\n".format(match['match_id'])

        player_count = 0
        print_rad = False
        print_dir = False

        for player in match_info['players']:
            player_count += 1
            player_blurb = self.get_player_blurb(player)

            if player_blurb is not None:
                if not print_rad and player_count <= 5:
                    match_string += "__**Radiant Team**__\n\n"
                    print_rad = True
                if not print_dir and player_count > 5:
                    match_string += "__**Dire Team**__\n\n"
                    print_dir = True
                match_string += player_blurb

        return match_string

    @commands.command(pass_context=True)
    async def last_match(self, ctx, *, member: discord.Member=None):
        """Info about the last match played.

        Gives info for the last Dota 2 match of the requested member.
        If no member is specified then the info returned is for the user
        that invoked the command."""

        if member is None:
            member = ctx.message.author

        steam_ids = self.bot.steam_info.get(member.id)

        if steam_ids is None:
            await self.bot.say("{0.name} has not linked their Steam account to MT5ABot.".format(member))
            return

        match = self.get_latest_match_from_list(steam_ids)
        print(match)
        if match is None:
            await self.bot.say("The Steam Web API is down. Please try again later.")
        else:
            match_string = self.parse_match(match)
            print(match_string)
            if match_string is None:
                await self.bot.say("The Steam Web API is down. Please try again later.")
            else:
                await self.bot.say(match_string)


def setup(bot):
    bot.add_cog(Dota2(bot))
