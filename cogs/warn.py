import json
import random
import ast
from datetime import datetime
import re
import compress_json
import traceback

import discord
from discord import Member
from discord.ext import commands
from discord.ext.commands import has_permissions, MissingPermissions

# Todo nicknames for mirrored embeds

class bidict(dict):
    def __init__(self, *args, **kwargs):
        super(bidict, self).__init__(*args, **kwargs)
        self.inverse = {}
        for key, value in self.items():
            self.inverse.setdefault(value, []).append(key) 

    def __setitem__(self, key, value):
        if key in self:
            self.inverse[self[key]].remove(key) 
        super(bidict, self).__setitem__(key, value)
        self.inverse.setdefault(value, []).append(key)        

    def __delitem__(self, key):
        value = self[key] 
        self.inverse.setdefault(value, []).remove(key)
        if value in self.inverse and not self.inverse[value]: 
            del self.inverse[value]
        super(bidict, self).__delitem__(key)

def load_data(filename, global_var, default=None):
    try:
        data = compress_json.load(filename)
        if isinstance(default, bidict):
            globals()[global_var] = bidict(data)
        else:
            globals()[global_var] = data
    except FileNotFoundError:
        if isinstance(default, bidict):
            globals()[global_var] = bidict()
        else:
            globals()[global_var] = default

# Te stałe kolory pochodzą z biblioteki discord.js
with open("embed_colors.txt") as f:
    data = f.read()
    colors = ast.literal_eval(data)
    color_list = [c for c in colors.values()]

# Dwukierunkowy słownik do przechowywania par wiadomości i kanałów
message_channel_pairs = bidict()

# Dwukierunkowy słownik do przechowywania par wiadomości
message_pairs = bidict()

async def get_opposite_message(message_id, bot): # Zwraca klucz w słowniku, jeśli wartość pasuje lub odwrotnie
    global message_pairs
    global message_channel_pairs
    load_data('message_pairs.json.lzma', 'message_pairs', bidict())
    load_data('message_channel_pairs.json.lzma', 'message_channel_pairs', bidict())
    for key, value in message_pairs.items():
        try:
            if value == int(message_id) or key == str(message_id): # Klucz to prawdziwe ID wiadomości
                channel = bot.get_channel(message_channel_pairs[str(value)])
                message = await channel.fetch_message(value)
                return channel, message # To prawdopodobnie zepsuje się, jeśli będzie wiele par kanałów, ponieważ nie zwróci tablicy zawierającej wszystkie wyniki, tylko pierwszy znaleziony kanał
        except:
            return None, None
    return None, None  # Zwraca None, jeśli wartość nie została znaleziona w słowniku

async def get_original_message(message_id, bot): # Zwraca klucz w słowniku, jeśli klucz lub wartość tej pary pasuje
    global message_pairs
    global message_channel_pairs
    load_data('message_pairs.json.lzma', 'message_pairs', bidict())
    load_data('message_channel_pairs.json.lzma', 'message_channel_pairs', bidict())
    for key, value in message_pairs.items():
        try:
            if value == int(message_id) or key == str(message_id): # Klucz to prawdziwe ID wiadomości
                channel = bot.get_channel(message_channel_pairs[str(key)])
                real_message = await channel.fetch_message(key)
                return real_message
        except:
            return None
    return None  # Zwraca None, jeśli wartość nie została znaleziona w słowniku

async def get_user_from_input(input_str, bot):
    # Wzorzec wyrażenia regularnego do dopasowania wzmiankach o użytkownikach i ID
    user_pattern = re.compile(r'<@!?(\d+)>|(\d+)')

    # Próbuj znaleźć dopasowanie w ciągu wejściowym
    try:
        match = user_pattern.match(input_str)
    except TypeError:
        return None

    if match:
        # Sprawdź, czy znaleziono wzmiankę o użytkowniku (<@user_id> lub <@!user_id>)
        try:
            if match.group(1):
                user_id = int(match.group(1))
            else:
                # Użyj ID numerycznego, jeśli nie znaleziono wzmianki
                user_id = int(match.group(2))
        except ValueError:
            return None
            
        # Pobierz obiekt użytkownika
        for guild in bot.guilds:
            try:
                user = await guild.fetch_member(user_id)
                if user:
                    # Użytkownik znaleziony, wyjdź z pętli
                    break
            except discord.NotFound:
                # Użytkownik nie znaleziony w tej gildii, przejdź do następnej gildii
                user = None
                continue
        if user:
            # Zaloguj pomyślne pobranie użytkownika
            print(f"Znaleziono użytkownika: {user.name} (ID: {user.id})")
            return user
        else:
            # Zaloguj, że użytkownik nie został znaleziony
            print(f"Nie znaleziono użytkownika o ID: {user_id}")
            return None
    else:
        return None

async def check_user(user, bot, ctx):
        user_obj = await get_user_from_input(user, bot)
        if user_obj == None and user == None: # Nic nie podano
            await ctx.send("Zapomniałeś podać użytkownika jako argumentu.")
            return
        elif user_obj == None and user is not None: # Kanał tekstowy(?)
            message = await get_original_message(user, bot)
            if message is not None:
                user = await message.channel.guild.fetch_member(message.author.id)
                return user
            else:
                await ctx.send("Podany użytkownik jest nieprawidłowy.")
                return
        elif user_obj is not None and user is not None:
            user = user_obj
            return user
        else:
            return

class Warn(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # Definiuj nową komendę
    @commands.command(
        name='warn',
        description='Słynna komenda warn',
        usage='<@offender> nazwał moją mamę grubą :((((((( cri' # Todo: dodaj funkcjonalność bezpośredniego ID wiadomości dla sparowanych kanałów
    )
    @has_permissions(manage_messages=True)
    async def warn_command(self, ctx, user=None, *, reason: str):
        user = await check_user(user, self.bot, ctx)
        if user.guild_permissions.manage_messages == True:
            await ctx.send("Określony użytkownik ma uprawnienia \"Zarządzaj wiadomościami\" (lub wyższe) na serwerze.")
            return           
        if user.id == self.bot.user.id:
            await ctx.send("O, naprawdę, huh? Staram się jak najlepiej utrzymać ten serwer, a TY mnie tak traktujesz? Rzucam to..")
            return
        if user.bot:
            await ctx.send("Nie ma sensu ostrzegać bota. Po co w ogóle próbujesz.")
            return
        if user == ctx.author:
            await ctx.send("Dlaczego, do diabła, miałbyś ostrzegać siebie? Nienawidzisz siebie TAK bardzo?")
            return

        dt_string = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        # Załaduj istniejące dane z pliku
        try:
            data = compress_json.load("members.json.lzma")
        except FileNotFoundError:
            # Jeśli plik nie istnieje, zainicjalizuj pusty słownik
            data = {}

        # Sprawdź, czy ID użytkownika istnieje w danych i klucz 'warns' jest obecny i <= 0
        if str(user.id) in data and 'warns' in data[str(user.id)] and data[str(user.id)]['warns'] <= 0:
            # Zmodyfikuj dane w pamięci
            data[str(user.id)]['warns'] = 1
            data[str(user.id)]['1'] = {
                'warner': ctx.author.id,
                'warner_name': ctx.author.name,
                'reason': reason,
                'channel': str(ctx.channel.id),
                'datetime': dt_string
            }
        else:
            # Jeśli użytkownik ma wcześniejsze ostrzeżenia lub nie istnieje w danych, zaktualizuj odpowiednio
            if str(user.id) not in data:
                data[str(user.id)] = {}

            # Zwiększ liczbę ostrzeżeń
            warn_amount = data[str(user.id)].get("warns", 0) + 1
            data[str(user.id)]["warns"] = warn_amount
            data[str(user.id)]["username"] = user.name

            # Dodaj nowy wpis ostrzeżenia
            new_warn = {
                str(warn_amount): {
                    'warner': ctx.author.id,
                    'warner_name': ctx.author.name,
                    'reason': reason,
                    'channel': str(ctx.channel.id),
                    'datetime': dt_string
                }
            }
            data[str(user.id)].update(new_warn)

        # Zapisz zmodyfikowane dane z powrotem do pliku, nadpisując poprzednie zawartości
        compress_json.dump(data, "members.json.lzma")

        # Utwórz i wyślij embed pokazujący, że użytkownik został pomyślnie ostrzeżony
        embed = discord.Embed(
            title=f"Nowe ostrzeżenie dla {user.name}",
            color=random.choice(color_list)
        )
        embed.set_author(
            name=ctx.message.author.name,
            icon_url=ctx.message.author.display_avatar.url,
            url=f"https://discord.com/users/{ctx.message.author.id}/"
        )
        embed.add_field(
            name=f"Ostrzeżenie {warn_amount}",
            value=f"Osoba ostrzegająca: {ctx.author.name} (<@{ctx.author.id}>)\nPowód: {reason}\nKanał: <#{str(ctx.channel.id)}>\nData i godzina: {dt_string}",
            inline=True
        )
        # Tworzy i wysyła embed(y)
        await ctx.send(
            content="Pomyślnie dodano nowe ostrzeżenie.",
            embed=embed
        )
        paired_channel, paired_message = await get_opposite_message(ctx.message.id, self.bot)
        if paired_channel:
                await paired_channel.send(
                content="Pomyślnie dodano nowe ostrzeżenie.",
                embed=embed
            )
    @warn_command.error
    async def warn_handler(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            # Autor nie ma odpowiednich uprawnień
            await ctx.send('{0.author.name}, nie masz odpowiednich uprawnień do wykonania tej czynności. *(błąd commands.MissingPermissions, akcja anulowana)*'.format(ctx))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'user':
                # Autor nie określił użytkownika do ostrzeżenia
                await ctx.send("{0.author.name}, zapomniałeś określić użytkownika do ostrzeżenia. *(błąd commands.MissingRequiredArgument, akcja anulowana)*".format(ctx))
                return
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'reason':
                # Autor nie określił powodu
                await ctx.send("{0.author.name}, zapomniałeś określić powodu. *(błąd commands.MissingRequiredArgument, akcja anulowana)*".format(ctx))
                return
        traceback_str = traceback.format_exc()
        print(traceback_str)
        print(error)
        await ctx.send(error + " <@1143793302701879416>")

    @commands.command(
        name='warns',
        description='Zobacz wszystkie ostrzeżenia, jakie ma użytkownik',
        usage='<@offender>',
        aliases=['warnings']
    )
    async def warns_command(self, ctx, user=None):
        user = await check_user(user, self.bot, ctx)
        paired_channel, paired_message = await get_opposite_message(ctx.message.id, self.bot)
        try:
            data = compress_json.load("members.json.lzma")
        except FileNotFoundError:
            await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] nie ma żadnych ostrzeżeń.")
            if paired_channel:
                await paired_channel.send(f"{ctx.author.name}, użytkownik [{user.name}] nie ma żadnych ostrzeżeń.")
            return
    
        try:
            if 'warns' not in data.get(str(user.id), {}) or data[str(user.id)].get('warns') <= 0:
                await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] nie ma żadnych ostrzeżeń.")
                if paired_channel:
                    await paired_channel.send(f"{ctx.author.name}, użytkownik [{user.name}] nie ma żadnych ostrzeżeń.")
                return
        except:
            #raise commands.CommandInvokeError("user")
            return
        warn_amount = data[str(user.id)].get("warns", 0)
        last_noted_name = data[str(user.id)].get("username", user.name)
        warns_word = "ostrzeżenie" if warn_amount == 1 else "ostrzeżenia"
    
        embed = discord.Embed(
            title=f"Ostrzeżenia {user.name}",
            description=f"Ma {warn_amount} {warns_word}.",
            color=random.choice(color_list)
        )
    
        embed.set_author(
            name=ctx.message.author.name,
            icon_url=ctx.message.author.display_avatar.url,
            url=f"https://discord.com/users/{ctx.message.author.id}/"
        )
    
        for x in range(1, warn_amount + 1):
            warn_dict = data[str(user.id)][str(x)]
            warner_id = warn_dict.get('warner')
            
            try:
                warner = await ctx.guild.fetch_member(warner_id)
            except discord.NotFound:
                warner = None
    
            warn_reason = warn_dict.get('reason')
            warn_channel = warn_dict.get('channel')
            warn_datetime = warn_dict.get('datetime')
    
            warner_name = warner.name if warner else warn_dict.get('warner_name', 'Nieznany Użytkownik')
    
            embed.add_field(
                name=f"Ostrzeżenie {x}",
                value=f"Osoba ostrzegająca: {warner_name} (<@{warner_id}>)\nPowód: {warn_reason}\nKanał: <#{warn_channel}>\nData i godzina: {warn_datetime}",
                inline=True
            )
        # Wyślij embed(y).
        await ctx.send(
            content=None,
            embed=embed
        )
        if paired_channel:
            await paired_channel.send(
                content=None,
                embed=embed
            )
    @warns_command.error
    async def warns_handler(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'user':
                # Autor nie określił użytkownika
                await ctx.send("Proszę wspomnieć kogoś, aby sprawdzić jego ostrzeżenia.")
            else:
                await ctx.send("Użycie komendy: `^warns <użytkownik>`")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("Wystąpił błąd podczas przetwarzania komendy. Proszę spróbować ponownie później.")
            traceback_str = traceback.format_exc()
            print(traceback_str)
            print(error)
        else:
            await ctx.send(f"Wystąpił błąd: {error}")
            traceback_str = traceback.format_exc()
            print(traceback_str)
            print(error)

    @commands.command(
        name='remove_warn',
        description='Usuwa konkretne ostrzeżenie od konkretnego użytkownika.',
        usage='@user 2',
        aliases=['removewarn','clearwarn','warn_remove']
    )
    @has_permissions(manage_messages=True)
    async def remove_warn_command(self, ctx, user=None, *, warn: str):
        user = await check_user(user, self.bot, ctx)
        try:
            data = compress_json.load("members.json.lzma")
        except FileNotFoundError:
            await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] nie ma żadnych ostrzeżeń.")
            return
    
        if 'warns' not in data.get(str(user.id), {}) or data[str(user.id)].get('warns') <= 0:
            await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] nie ma żadnych ostrzeżeń.")
            return
    
        warn_amount = data[str(user.id)].get("warns", 0)
        specified_warn = data[str(user.id)].get(str(warn))
    
        if specified_warn is None:
            await ctx.send(f"{ctx.author.name}, nie ma ostrzeżenia numer {warn} dla użytkownika [{user.name} ({user.id})].")
            return
    
        warn_warner = specified_warn.get('warner')
        warn_reason = specified_warn.get('reason')
        warn_channel = specified_warn.get('channel')
        warn_datetime = specified_warn.get('datetime')
    
        try:
            warn_warner_name = self.bot.get_user(id=warn_warner)
        except:
            # Użytkownik prawdopodobnie opuścił serwer
            warn_warner_name = specified_warn.get('warner_name')
    
        confirmation_embed = discord.Embed(
            title=f'Warn numer {warn} użytkownika {user.name}',
            description=f'Osoba ostrzegająca: {warn_warner_name}\nPowód: {warn_reason}\nKanał: <#{warn_channel}>\nData i godzina: {warn_datetime}',
            color=random.choice(color_list),
        )
        confirmation_embed.set_author(
            name=ctx.message.author.name,
            icon_url=ctx.message.author.display_avatar.url,
            url=f"https://discord.com/users/{ctx.message.author.id}/"
        )
    
        def check(ms):
            return ms.channel == ctx.message.channel and ms.author == ctx.message.author
        paired_channel, paired_message = await get_opposite_message(ctx.message.id, self.bot)
        await ctx.send(content='Czy na pewno chcesz usunąć to ostrzeżenie? (Odpowiedz y lub n)', embed=confirmation_embed)
        if paired_channel:
            await paired_channel.send(content='Czy na pewno chcesz usunąć to ostrzeżenie? (Odpowiedz y lub n)', embed=confirmation_embed)
        msg = await self.bot.wait_for('message', check=check)
        reply = msg.content.lower()
    
        if reply in ('y', 'yes', 'confirm'):
            if warn_amount == 1:
                del data[str(user.id)]['warns']
            else:
                for x in range(int(warn), int(warn_amount)):
                    data[str(user.id)][str(x)] = data[str(user.id)][str(x + 1)]
                    del data[str(user.id)][str(x + 1)]
                data[str(user.id)]['warns'] = warn_amount - 1
            compress_json.dump(data, "members.json.lzma")
            await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] miał usunięte ostrzeżenie.")
            if paired_channel:
                await paired_channel.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] miał usunięte ostrzeżenie.")
        elif reply in ('n', 'no', 'cancel'):
            await ctx.send("W porządku, akcja anulowana.")
        else:
            await ctx.send("Nie wiem, co chciałeś, żebym zrobił. Akcja anulowana.")

    @remove_warn_command.error
    async def remove_warn_handler(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'user':
                # Autor nie określił użytkownika
                await ctx.send("Proszę wspomnieć kogoś, aby usunąć jego ostrzeżenia.")
                return
            if error.param.name == 'warn':
                # Autor nie określił ID ostrzeżenia
                await ctx.send("Nie określiłeś ID ostrzeżenia do usunięcia.")
                return
        if isinstance(error, commands.CommandInvokeError):
            # Autor prawdopodobnie określił nieprawidłowe ID
            await ctx.send("Określiłeś nieprawidłowe ID.")
            return
        await ctx.send(error)

    @commands.command(
        name='edit_warn',
        description='Edytuje konkretne ostrzeżenie u konkretnego użytkownika.',
        usage='@user 2',
        aliases=['editwarn', 'changewarn']
    )
    @has_permissions(manage_messages=True)
    async def edit_warn_command(self, ctx, user=None, *, warn: str):
        user = await check_user(user, self.bot, ctx)
        try:
            data = compress_json.load("members.json.lzma")
        except FileNotFoundError:
            await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] nie ma żadnych ostrzeżeń.")
            return
    
        if 'warns' not in data.get(str(user.id), {}) or data[str(user.id)].get('warns') <= 0:
            await ctx.send(f"{ctx.author.name}, użytkownik [{user.name} ({user.id})] nie ma żadnych ostrzeżeń.")
            return
    
        def check(ms):
            return ms.channel == ctx.message.channel and ms.author == ctx.message.author
    
        await ctx.send(content='Na jaki powód chcesz zmienić to ostrzeżenie?')
        msg = await self.bot.wait_for('message', check=check)
        warn_new_reason = msg.content
    
        specified_warn = data[str(user.id)].get(warn)
    
        if specified_warn is None:
            await ctx.send(f"{ctx.author.name}, nie ma ostrzeżenia numer {warn} dla użytkownika [{user.name} ({user.id})].")
            return
    
        warn_warner = specified_warn.get('warner')
        warn_channel = specified_warn.get('channel')
        warn_datetime = specified_warn.get('datetime')
    
        try:
            warn_warner_name = self.bot.get_user(id=warn_warner)
        except:
            # Użytkownik prawdopodobnie opuścił serwer
            warn_warner_name = specified_warn.get('warner_name')
    
        confirmation_embed = discord.Embed(
            title=f'Ostrzeżenie numer {warn} użytkownika {user.name}',
            description=f'Osoba ostrzegająca: {warn_warner_name}\nPowód: {warn_new_reason}\nKanał: <#{warn_channel}>\nData i godzina: {warn_datetime}',
            color=random.choice(color_list),
        )
        confirmation_embed.set_author(
            name=ctx.message.author.name,
            icon_url=ctx.message.author.display_avatar.url,
            url=f"https://discord.com/users/{ctx.message.author.id}/"
        )
        paired_channel, paired_message = await get_opposite_message(ctx.message.id, self.bot)
        await ctx.send(content='Czy na pewno chcesz edytować to ostrzeżenie w ten sposób? (Odpowiedz y/yes lub n/no)', embed=confirmation_embed)
        if paired_channel:
            await paired_channel.send(content='Czy na pewno chcesz edytować to ostrzeżenie w ten sposób? (Odpowiedz y/yes lub n/no)', embed=confirmation_embed)
        msg = await self.bot.wait_for('message', check=check)
        reply = msg.content.lower()
    
        if reply in ('y', 'yes', 'confirm'):
            specified_warn['reason'] = warn_new_reason
            compress_json.dump(data, "members.json.lzma")
            await ctx.send(f"[{ctx.author.name}], użytkownik [{user.name} ({user.id})] miał edytowane ostrzeżenie.")
            if paired_channel:
                await paired_channel.send(f"[{ctx.author.name}], użytkownik [{user.name} ({user.id})] miał edytowane ostrzeżenie.")
        elif reply in ('n', 'no', 'cancel'):
            await ctx.send("W porządku, akcja anulowana.")
        else:
            await ctx.send("Nie wiem, co chciałeś, żebym zrobił. Akcja anulowana.")
            
    @edit_warn_command.error
    async def edit_warn_handler(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'user':
                # Autor nie określił użytkownika
                await ctx.send("Proszę wspomnieć kogoś, aby edytować jego ostrzeżenia.")
                return
            if error.param.name == 'warn':
                # Autor nie określił ID ostrzeżenia
                await ctx.send("Nie określiłeś ID ostrzeżenia do edytowania.")
                return
        if isinstance(error, commands.CommandInvokeError):
            # Autor prawdopodobnie określił nieprawidłowe ID
            await ctx.send("Określiłeś nieprawidłowe ID.")
            return
        await ctx.send(error)

async def setup(bot):
    await bot.add_cog(Warn(bot))
