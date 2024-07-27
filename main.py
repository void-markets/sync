import discord
from discord.ui import Button, View
from discord.ext import commands
from discord.ext.commands import has_permissions, MissingPermissions
from requests import get
import json
import compress_json
import aiohttp
import re
import os

# Todo kolejka do edytowania i usuwania wiadomości
# Todo kolejka do dodawania i usuwania reakcji
# ^^^ Aby zapobiec konfliktom, te funkcje nie mogą działać jednocześnie
# ^^^ Obecnie działają

# Todo dodaj komendę do zmiany zdjęcia profilowego
# Todo dodaj funkcjonalność komend slash
# Todo Komenda profilowa, która wyświetla prawdziwe i fałszywe informacje o użytkowniku
# Todo Dodaj wsparcie dla wielu mostów, aby można było połączyć trzy kanały z rzędu (jak to zrobić bez bazy danych?)

# todo: dodaj sprawdzanie uprawnień do komend get_author i warning

# todo: odwzorowanie tworzenia wątków i wiadomości w wątkach

# todo: odwzorowanie odpowiedzi

# todo: przepisz pętle w channel_pairs, aby używały if `value` in `dict` i bezpośrednio odwoływały się do par klucz-wartość zamiast przeszukiwać cały słownik

# Token bota i prefiks
TOKEN = 'Token_tutaj'
PREFIX = '^'

# Inicjalizacja bota
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

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

# Słownik dwukierunkowy do przechowywania par wiadomości i kanałów
message_channel_pairs = bidict()

# Słownik dwukierunkowy do przechowywania par wiadomości
message_pairs = bidict()

# Słownik do przechowywania reakcji na wiadomości
message_reactions = {}

# Słownik do przechowywania par kanałów
channel_pairs = {}

# Słownik do przechowywania członków
members = {}

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

def save_data(filename, data):
    compress_json.dump(data, filename)

# Tworzenie własnej kontroli, aby sprawdzić uprawnienia do "tworzenia webhooka"
def has_create_webhook_permission():
    async def predicate(ctx):
        if ctx.guild:
            # Sprawdź, czy użytkownik ma uprawnienia do "zarządzania webhookami" w obecnym serwerze
            permissions = ctx.author.guild_permissions
            if permissions.manage_webhooks:
                return True
            else:
                await ctx.send("Nie masz uprawnień do zarządzania webhookami.")
                return False
        else:
            # Ta komenda dotyczy tylko serwerów (guild)
            await ctx.send("Ta komenda może być używana tylko na serwerze (guild).")
            return False

    return commands.check(predicate)

def get_original_message(message_id): # Zwraca klucz w słowniku, jeśli klucz lub wartość pasuje
    for key, value in message_pairs.items():
        if value == message_id or key == message_id: # Klucz to prawdziwe ID wiadomości
            channel = bot.get_channel(message_channel_pairs[str(key)])
            real_message = channel.fetch_message(key)
            return real_message
    return None  # Zwraca None, jeśli wartość nie została znaleziona w słowniku

async def get_channel_from_input(input_str):
    # Wzorzec wyrażenia regularnego do dopasowywania wspomnienia kanałów i ID
    channel_pattern = re.compile(r'<#(\d+)>|(\d+)')

    # Próba znalezienia dopasowania w ciągu wejściowym
    match = channel_pattern.match(input_str)

    if match:
        # Sprawdź, czy znaleziono wspomnienie kanału (<#channel_id>)
        if match.group(1):
            channel_id = int(match.group(1))
        else:
            # Użyj numerycznego ID, jeśli nie znaleziono wspomnienia
            channel_id = int(match.group(2))
        
        # Pobierz obiekt kanału
        channel = bot.get_channel(channel_id)

        return channel
    else:
        return None

async def get_user_from_input(input_str):
    # Wzorzec wyrażenia regularnego do dopasowywania wspomnień użytkowników i ID
    user_pattern = re.compile(r'<@!?(\d+)>|(\d+)')

    # Próba znalezienia dopasowania w ciągu wejściowym
    match = user_pattern.match(input_str)

    if match:
        # Sprawdź, czy znaleziono wspomnienie użytkownika (<@user_id> lub <@!user_id>)
        if match.group(1):
            user_id = int(match.group(1))
        else:
            # Użyj numerycznego ID, jeśli nie znaleziono wspomnienia
            user_id = int(match.group(2))
        
        try:
            # Pobierz obiekt użytkownika
            user = await bot.fetch_user(user_id)
        except:
            return None
        if user:
            # Zaloguj pomyślne pobranie użytkownika
            print(f"Użytkownik znaleziony: {user.name} (ID: {user.id})")
            return user
        else:
            # Zaloguj brak użytkownika
            print(f"Nie znaleziono użytkownika o ID: {user_id}")
            return None
    else:
        return None

def check_in():
    ip = get('https://api.ipify.org').content.decode('utf8')
    print('Mój publiczny adres IP to: {}'.format(ip))

def update_channel_pairs_format(channel_pairs):
    try:
        for ch1, (webhook_url, ch2) in channel_pairs.items():
            channel_pairs[str(ch1)]["webhook_url"]
            return channel_pairs, False
    except:
        print("Wykryto stary format słownika, konwertowanie...")
        new_channel_pairs = {}
        for ch1, (webhook_url, ch2) in channel_pairs.items():
            new_channel_pairs[str(ch1)] = {
                "webhook_url": webhook_url,
                "paired_id": ch2
            }
        else:
            return new_channel_pairs, True


# Nasłuchiwanie zdarzenia gotowości bota
@bot.event
async def on_ready():
    global channel_pairs
    print(f'Zalogowano jako {bot.user.name} ({bot.user.id})')
    check_in()
    
    load_data('channel_pairs.json.lzma', 'channel_pairs', {})
    # Sprawdź, czy channel_pairs jest w starym formacie
    if isinstance(globals()['channel_pairs'], dict):
        # Konwertuj na nowy format
        channel_pairs, isFormatOld = update_channel_pairs_format(globals()['channel_pairs'])
        if isFormatOld:
            # Jeśli stary format, zapisz zaktualizowany channel_pairs do pliku
            save_data('channel_pairs.json.lzma', channel_pairs)
    
    load_data('message_pairs.json.lzma', 'message_pairs', bidict())
    load_data('message_channel_pairs.json.lzma', 'message_channel_pairs', bidict())
    load_data('message_reactions.json.lzma', 'message_reactions', {})
    load_data('members.json.lzma', 'members', {})
    cogs = []
    for cog_file in os.listdir('cogs/'):
        if cog_file.endswith('.py') and cog_file != 'slash.py':
            cog_import = 'cogs.' + cog_file.split('.')[0]
            cogs.append(cog_import)
            print(f'Znaleziono {cog_file} jako cog')

    for cog in cogs:
        print(f'Ładowanie {cog}')
        try:
            await bot.load_extension(cog)
        except discord.ext.commands.errors.ExtensionAlreadyLoaded:
            # Bot próbował załadować cog, który był już załadowany.
            print(f"Próba załadowania coga/rozszerzenia, które było już załadowane ({cog})")

# Komenda do parowania dwóch kanałów
@bot.command(aliases=['pairchannels', 'pairch', 'pairchan', 'link', 'linkchans', 'linkchannels'])
@has_create_webhook_permission()
async def pair(ctx, channel1str, channel2str):
    global channel_pairs
    channel1 = await get_channel_from_input(channel1str)
    channel2 = await get_channel_from_input(channel2str)
    fetched_channels = None
    if channel1 == None:
        fetched_channels = channel1str
    if channel2 == None:
        if fetched_channels is not None:
            fetched_channels += ", " + channel2str
        else:
            fetched_channels = channel2str
    if channel1 == None or channel2 == None:
        await ctx.send(f':negative_squared_cross_mark: Nie mogę uzyskać dostępu do kanału(-ów) wymienionych: {fetched_channels}')
        return

    # Sprawdź, czy bot ma uprawnienia do tworzenia webhooków w obu serwerach
    if (
        not ctx.guild.me.guild_permissions.manage_webhooks
        or not channel1.guild.me.guild_permissions.manage_webhooks
        or not channel2.guild.me.guild_permissions.manage_webhooks
    ):
        await ctx.send(':negative_squared_cross_mark: Potrzebuję uprawnień do tworzenia webhooków w obu serwerach!')
        return

    # Sprawdź, czy podano oba kanały
    if channel2 is None:
        await ctx.send(':negative_squared_cross_mark: Musisz podać dwa kanały do parowania.')
        return

    try:
        # Utwórz webhooki dla obu kanałów w ich odpowiednich serwerach
        webhook1 = await channel1.create_webhook(name='PairBot Webhook')
        webhook2 = await channel2.create_webhook(name='PairBot Webhook')

        # Zapisz parę kanałów w słowniku
        channel_pairs[channel1.id] = {
            "webhook_url": webhook1.url,
            "paired_id": channel2.id
        }
        
        channel_pairs[channel2.id] = {
            "webhook_url": webhook2.url,
            "paired_id": channel1.id
        }
        
        # Zapisz zaktualizowane channel_pairs do pliku
        save_data('channel_pairs.json.lzma', channel_pairs)

        await ctx.send(':white_check_mark: Webhook został pomyślnie utworzony!')
    except discord.errors.HTTPException as e:
        if e.status == 400 and e.code == 30007:
            await ctx.send(':x: Osiągnięto maksymalną liczbę webhooków w jednym z kanałów. Możesz potrzebować usunąć kilka webhooków w tym kanale, aby kontynuować.')
        else:
            await ctx.send(':x: Wystąpił błąd podczas tworzenia webhooka.')

# Komenda do rozparowania dwóch kanałów
@bot.command(aliases=['unpairch', 'unpairchan', 'unlink', 'unlinkchans', 'unlinkchannels'])
@has_create_webhook_permission()
async def unpair(ctx, channel1str, channel2str):
    global channel_pairs

    # Napraw błąd: Usuń tylko tę parę, jeśli channel1 lub 2 są połączone z innymi, nieokreślonymi kanałami, zachowaj te połączenia
    channel1 = await get_channel_from_input(channel1str)
    channel2 = await get_channel_from_input(channel2str)

    # Sprawdź, czy kanały istnieją
    fetched_channels = []

    if channel1 is None:
        fetched_channels.append(channel1str)
    if channel2 is None:
        fetched_channels.append(channel2str)

    if fetched_channels:
        await ctx.send(f':negative_squared_cross_mark: Nie mogę uzyskać dostępu do kanału(-ów) wymienionych: {", ".join(fetched_channels)}')
        return

    # Sprawdź, czy para istnieje
    missing_pair = []

    if str(channel1.id) not in channel_pairs:
        missing_pair.append(channel1.mention)
    if str(channel2.id) not in channel_pairs:
        missing_pair.append(channel2.mention)

    if missing_pair:
        await ctx.send(f':negative_squared_cross_mark: Kanał(y) wymieniony(e) nie są sparowane: {", ".join(missing_pair)}')
        return

    # Usuń webhooki
    await discord.Webhook.from_url(channel_pairs[str(channel1.id)]["webhook_url"], session=bot.http._HTTPClient__session).delete()
    await discord.Webhook.from_url(channel_pairs[str(channel2.id)]["webhook_url"], session=bot.http._HTTPClient__session).delete()

    # Usuń parę z słownika
    del channel_pairs[str(channel1.id)]
    del channel_pairs[str(channel2.id)]

    # Zapisz zaktualizowane channel_pairs do pliku
    save_data('channel_pairs.json.lzma', channel_pairs)

    await ctx.send(':white_check_mark: Para webhooków została zniszczona!')

# Komenda do wyświetlania par kanałów
@bot.command(aliases=['listpairs', 'listchans', 'listchannels', 'viewpairs', 'viewchans', 'viewchannels'])
@has_create_webhook_permission()
async def list(ctx):
    processed_channels = set()  # Utwórz zestaw do śledzenia przetworzonych ID kanałów
    pair_list = []

    for channel_id, data in channel_pairs.items(): #for ch1, (webhook_url, ch2) in channel_pairs.items():
        # Sprawdź, czy ID kanału zostało już przetworzone
        ch1 = int(channel_id)
        ch2 = int(data["paired_id"])
        if ch1 in processed_channels and ch2 in processed_channels:
            continue

        pair_list.append(f'<#{ch1}> :left_right_arrow: <#{ch2}>')
        processed_channels.add(ch1)
        processed_channels.add(ch2)

    # Utwórz embed do wysłania listy
    embed = discord.Embed(
        title="Pary kanałów",
        description="\n".join(pair_list),
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)

# Komenda do ustawiania lub wyświetlania pseudonimu
@bot.command(aliases=['nick', 'setnick', 'setnickname', 'changename']) # Todo dodaj opcję usuwania pseudonimu oraz możliwość ustawienia pseudonimu DLA użytkowników, jeśli masz uprawnienia do ustawiania pseudonimów.
async def nickname(ctx, *, args=None):
    global members
    if args:
        # Użytkownik podał argumenty, spróbuj ustawić pseudonim
        user = await get_user_from_input(args)
        if user is None:
            if str(ctx.author.id) in members and "nickname" in members[str(ctx.author.id)]: # Jeśli pseudonim już istnieje
                del members[str(ctx.author.id)]["nickname"] # Usuń stary pseudonim
            elif str(ctx.author.id) not in members:
                members[str(ctx.author.id)] = {}
            # Sprawdź duplikat pseudonimu
            for user_id, user_data in members.items():
                if 'nickname' not in user_data:
                    continue
                if user_data['nickname'] == args:
                    await ctx.send(embed=discord.Embed(description="Ten pseudonim jest już używany przez innego użytkownika."))
                    break
            else: # Else aktywuje się tylko jeśli instrukcja break nie została napotkana podczas pętli for
                # Użytkownik ustawia własny pseudonim
                members[str(ctx.author.id)]["nickname"] = args
                save_data('members.json.lzma', members)
                await ctx.send(embed=discord.Embed(description=f"Twój pseudonim został ustawiony na: {args}"))
                return
            return
        user_id = str(user.id)
        if str(user_id) in members and 'nickname' in members[str(user_id)]:
            # Wyświetlanie pseudonimu innego użytkownika
            await ctx.send(embed=discord.Embed(description=f"Pseudonim {user.display_name} to: {members[str(user_id)]['nickname']}"))
        else:
            # Użytkownik nie znaleziony w słowniku pseudonimów
            await ctx.send(embed=discord.Embed(description="Nie ustawiono pseudonimu dla tego użytkownika."))
    else:
        # Brak argumentów, wyświetl pseudonim nadawcy
        user_id = str(ctx.author.id)
        if str(user_id) in members and 'nickname' in members[str(user_id)]:
            await ctx.send(embed=discord.Embed(description=f"Twój pseudonim to: {members[str(user_id)]['nickname']}"))
        else:
            await ctx.send(embed=discord.Embed(description="Nie ustawiono pseudonimu dla Ciebie."))

@bot.command(aliases=['getauth', 'getauthor', 'author'])
@has_permissions(manage_messages=True) # Todo: użyj komendy message_channel_pairs, aby uzyskać kanał
async def get_author(ctx, message_id=None):
    if message_id is None:
        await ctx.send("Proszę podać ID wiadomości.")
        return
    try:
        message_id = int(message_id)
    except:
        await ctx.send("ID wiadomości powinno zawierać tylko cyfry, proszę podać poprawne ID wiadomości.")
        return
    # Sprawdź, czy podane message_id istnieje w słowniku message_pairs
    original_id = None  # Przechowuj oryginalne message_id
    isOriginal = False
    for original, paired in message_pairs.items():
        if str(paired) == str(message_id):
            # Znaleziono dopasowaną parę, użyj oryginalnego message_id
            original_id = original
            break
        elif str(original) == str(message_id):
            # original_id = original
            isOriginal = True
            break
    if isOriginal:
        await ctx.send("Podano ID wiadomości oryginalnego autora.")
        return
    if original_id is not None:
        # Przeszukaj serwery i kanały tekstowe, aby znaleźć wiadomość
        for guild in bot.guilds:
            for channel in guild.text_channels:
                try:
                    message = await channel.fetch_message(original_id)
                    if message:
                        author_id_msg = await ctx.send(f"ID autora wiadomości: {message.author.id}")
                        await ctx.message.delete(delay=30)
                        await author_id_msg.delete(delay=30)
                        return  # Zakończ pętlę, jeśli wiadomość została znaleziona
                except discord.NotFound:
                    continue  # Kontynuuj wyszukiwanie, jeśli wiadomość nie została znaleziona

        # Jeśli pętla zakończy się, a wiadomość nadal nie zostanie znaleziona, wyślij wiadomość
        await ctx.send("Sparowana wiadomość istnieje w jsonie, ale nie na Discordzie (powiedz właścicielowi bota!)")
    else:
        await ctx.send("Sparowana wiadomość nie została znaleziona")
    
# Komenda pomocy
@bot.command(aliases=['helpme', 'commands', 'cmds', 'info'])
@has_create_webhook_permission()
async def help(ctx):
    # Utwórz embed dla wiadomości pomocy
    embed = discord.Embed(
        title="Dostępne komendy",
        description="Oto dostępne komendy:",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="^pair <Kanał> <Kanał>",
        value="Sparuj dwa kanały",
        inline=False
    )

    embed.add_field(
        name="^unpair <Kanał> <Kanał>",
        value="Rozparuj dwa kanały",
        inline=False
    )

    embed.add_field(
        name="^list",
        value="Wyświetl sparowane kanały",
        inline=False
    )
    
    embed.add_field(
        name="^nickname <wspomnienie_użytkownika|ID_użytkownika|tutaj_pseudonim|nic>",
        value="Ustaw lub wyświetl pseudonim dla siebie lub innego użytkownika",
        inline=False
    )
    
    embed.add_field(
        name="^get_author <sparowane_ID_wiadomości>",
        value="Uzyskaj prawdziwego autora wiadomości za pomocą ID wiadomości (przydatne do ostrzeżeń)",
        inline=False
    )

    embed.add_field(
        name="^help",
        value="Pokaż tę wiadomość",
        inline=False
    )
    
    embed.add_field(
        name="^purge <ilość>",
        value="Usuń określoną liczbę wiadomości w bieżącym i sparowanym kanale",
        inline=False
    )
    
    embed.add_field(
        name="^warn <wspomnienie_użytkownika|ID_użytkownika|sparowane_ID_wiadomości> <powód>",
        value="Ostrzeż użytkownika z powodem",
        inline=False
    )
    
    embed.add_field(
        name="^warns <wspomnienie_użytkownika|ID_użytkownika|sparowane_ID_wiadomości>",
        value="Zobacz wszystkie ostrzeżenia użytkownika",
        inline=False
    )
    
    embed.add_field(
        name="^remove_warn <wspomnienie_użytkownika|ID_użytkownika|sparowane_ID_wiadomości> <numer_ostrzeżenia>",
        value="Usuń konkretne ostrzeżenie u użytkownika",
        inline=False
    )
    
    embed.add_field(
        name="^edit_warn <wspomnienie_użytkownika|ID_użytkownika|sparowane_ID_wiadomości> <numer_ostrzeżenia>",
        value="Edytuj konkretne ostrzeżenie u użytkownika",
        inline=False
    )

    await ctx.send(embed=embed)

async def create_mirrored_message_embed(message):
    global members
    if str(message.author.id) in members and 'nickname' in members[str(message.author.id)]: # Pseudonim istnieje
        username = members[str(message.author.id)]['nickname'] # Użyj pseudonimu
    else: # Pseudonim nie istnieje
        username = message.author.display_name # Użyj display_name
    # Utwórz pusty embed
    embed = discord.Embed()

    # Ustaw tytuł embeda na podstawie treści wiadomości
    embed.description = " "

    # Ustaw kolor embeda (kod koloru hex)
    embed.color = 0x00FFFF

    # Ustaw stopkę embeda, aby wyświetlić nazwisko autora
    embed.set_footer(
        text=f"{username}: {message.content}",
        icon_url=message.author.display_avatar.url,
    )

    # Utwórz widok, aby dodać komponent przycisku
    view = discord.ui.View()
    # Dodaj komponent przycisku "Przejdź do oryginalnej wiadomości"
    view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label="ᴶᵘᵐᵖ ᵗᵒ ᴿᵉᵖˡʸ", url=f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"))

    return embed, view


# Zdarzenie do obsługi kopiowania wiadomości
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.reference:
        print(message.reference)
    
    # Znajdź sparowany kanał dla bieżącego kanału
    for channel_id, data in channel_pairs.items(): # for channel_id, (webhook_url, paired_id) in channel_pairs.items():
        if message.channel.id == int(channel_id):
            paired_id = data['paired_id']
            webhook_url = data['webhook_url']
            global message_pairs
            global message_channel_pairs
            global members
            if str(message.author.id) in members and 'nickname' in members[str(message.author.id)]: # Nickname istnieje
                username = members[str(message.author.id)]['nickname'] # Użyj nickname
            else: # Nickname nie istnieje
                username = message.author.display_name # Użyj display_name
            webhook_url = channel_pairs[str(paired_id)]["webhook_url"]
            async with aiohttp.ClientSession() as session:
                if message.reference:
                    embeds = []
                    view = None
                    if str(message.reference.message_id) in message_pairs: # Pobierz ID przeciwnych wiadomości, ponieważ odpowiedź będzie w sparowanym kanale
                        target_message_id = message_pairs[str(message.reference.message_id)] # message.reference.message_id to prawdziwa wiadomość
                    elif int(message.reference.message_id) in message_pairs.inverse:
                        target_message_id = message_pairs.inverse[int(message.reference.message_id)][0] # message.reference.message_id to wiadomość bota
                    else:
                        target_message_id = None
                    if target_message_id:
                        channel = bot.get_channel(message_channel_pairs[str(target_message_id)])
                        reference_message = await channel.fetch_message(target_message_id)
                        embed, view = await create_mirrored_message_embed(reference_message)
                        embeds.append(embed)
                        print(embed)
                else:
                    embeds = [] 
                    view = None
                files = []
                for attachment in message.attachments:
                    file = await attachment.to_file(use_cached=True, spoiler=attachment.is_spoiler())
                    files.append(file)
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                webhook = await bot.fetch_webhook(webhook.id) # Todo: Zmień kod par kanałów, aby zapisywał webhook.id zamiast URL webhooka, naprawdę nie chcę tego ponownie kodować...
                if view:
                    response = await webhook.send(username=username, content=message.content, avatar_url=message.author.display_avatar.url, files=files, embeds=embeds, view=view, wait=True)
                else:
                    response = await webhook.send(username=username, content=message.content, avatar_url=message.author.display_avatar.url, files=files, embeds=embeds, wait=True)
                message_pairs[str(message.id)] = response.id
                save_data('message_pairs.json.lzma', message_pairs)
                message_channel_pairs[str(message.id)] = message.channel.id # Prawdziwa wiadomość
                message_channel_pairs[str(response.id)] = response.channel.id # Odbita wiadomość
                save_data('message_channel_pairs.json.lzma', message_channel_pairs)
            break
    await bot.process_commands(message)

# Nasłuchiwacz zdarzeń usunięcia wiadomości
@bot.event
async def on_raw_message_delete(payload):
    global message_pairs
    # Sprawdź, czy ID wiadomości jest w słowniku message_pairs
    message_id = payload.message_id
    if str(message_id) in message_pairs:
        target_message_id = message_pairs[str(message_id)] # message_id to prawdziwa wiadomość
        del message_pairs[str(message_id)]
    elif message_id in message_pairs.inverse:
        target_message_id = message_pairs.inverse[message_id][0] # message_id to wiadomość bota
        del message_pairs[target_message_id]
    else:
        return
    global message_channel_pairs
    if str(message_id) in message_channel_pairs:
        del message_channel_pairs[str(message_id)]
    save_data('message_pairs.json.lzma', message_pairs)
    save_data('message_channel_pairs.json.lzma', message_channel_pairs)
    
    # Znajdź sparowany kanał dla bieżącego kanału
    for channel_id, data in channel_pairs.items(): # for channel_id, (webhook_url, paired_id) in channel_pairs.items():
        if payload.channel_id == int(channel_id):
            # Pobierz docelowy kanał
            paired_id = data['paired_id']
            target_channel = bot.get_channel(paired_id)
            if target_channel:
                try:
                    target_message = await target_channel.fetch_message(target_message_id)
                    print(f"Wiadomość({message_id}) usunięta, propagowanie usunięcia do sparowanej wiadomości({target_message_id})")
                    await target_message.delete()
                except discord.NotFound:
                    print(f"Sparowana wiadomość({target_message_id}) nie znaleziona")

def delete_pair(m):
    global message_pairs
    global message_channel_pairs
    message_id = m.id
    if str(message_id) in message_pairs:
        del message_pairs[str(message_id)] # message_id to prawdziwa wiadomość
    elif int(message_id) in message_pairs.inverse:
        target_message_id = message_pairs.inverse[int(message_id)][0] # message_id to wiadomość bota
        del message_pairs[target_message_id]
    if str(message_id) in message_channel_pairs:
        del message_channel_pairs[str(message_id)]
    # print(message_id)
    return True

@bot.command(aliases=['purgech', 'purgechan', 'delete', 'clear', 'cleanup'])
@has_permissions(administrator=True)
async def purge(ctx, amount: int):
    if str(ctx.channel.id) not in channel_pairs:
        await ctx.send("Ten kanał nie jest sparowany z innym kanałem.")
        return
    global message_pairs
    global message_channel_pairs
    first = True
    for channel_id, data in channel_pairs.items(): # for channel_id, (webhook_url, paired_id) in channel_pairs.items():
        if str(ctx.channel.id) == str(channel_id):
            paired_channel = bot.get_channel(data['paired_id'])
            
            if not paired_channel:
                # await ctx.send("Sparowany kanał nie został znaleziony.")
                continue
            
            if first: # Na wypadek gdyby było wiele sparowanych kanałów
                # Usuń wiadomości w bieżącym kanale
                deleted = await ctx.channel.purge(limit=amount + 1, check=delete_pair)  # +1, aby uwzględnić wiadomość komendy purge
                first = False
            
            # Usuń wiadomości w sparowanym kanale
            deleted_paired = await paired_channel.purge(limit=amount + 1, check=delete_pair)  # +1, aby uwzględnić wiadomość komendy purge
            
            # Zaktualizuj message_pairs i message_channel_pairs, aby odzwierciedlić usunięcie wiadomości
            save_data('message_pairs.json.lzma', message_pairs)
            save_data('message_channel_pairs.json.lzma', message_channel_pairs)
            
            purge_message = await ctx.send(f"Usunięto {len(deleted)-1} wiadomości w tym kanale i {len(deleted_paired)-1} wiadomości w sparowanym kanale.")
            await purge_message.delete(delay=30)
            break
    else:
        deleted = await ctx.channel.purge(limit=amount + 1)
        purge_message = await ctx.send(f"Usunięto {len(deleted)-1} wiadomości.")
        await purge_message.delete(delay=30)

# Nasłuchiwacz zdarzeń edytowania wiadomości
@bot.event
async def on_raw_message_edit(payload):
    # Sprawdź, czy ID wiadomości jest w słowniku message_pairs
    message_id = payload.message_id
    if str(message_id) in message_pairs:
        target_message_id = message_pairs[str(message_id)] # message_id to prawdziwa wiadomość
    elif message_id in message_pairs.inverse:
        return
        # target_message_id = message_pairs.inverse[message_id][0] # message_id to wiadomość bota (technicznie niemożliwe, ponieważ nie można edytować wiadomości bota)
    else:
        return
    # Znajdź sparowany kanał dla bieżącego kanału
    paired_webhook_url = channel_pairs[str(channel_pairs[str(payload.channel_id)]["paired_id"])]["webhook_url"]

    # Sprawdź, czy ID kanału jest w słowniku sparowanych kanałów
    for channel_id, data in channel_pairs.items(): # for channel_id, (webhook_url, paired_id) in channel_pairs.items():
        if payload.channel_id == int(channel_id):
            if data['paired_id'] is not None:
                # Pobierz docelowy kanał
                target_channel = bot.get_channel(data['paired_id'])
            
                if target_channel:
                    # Edytuj odbitą wiadomość w docelowym kanale
                    print(f"Wiadomość edytowana o ID: {message_id}")
                    try:
                        # Znajdź sparowaną wiadomość w docelowym kanale według ID
                        target_message = await target_channel.fetch_message(target_message_id)
                        # Pobierz webhook i edytuj wiadomość
                        webhook = discord.Webhook.from_url(paired_webhook_url, client=bot)
                        await webhook.edit_message(
                            target_message_id,
                            content=payload.data['content'],
                            attachments=payload.data['attachments'],
                            embeds=target_message.embeds,
                        )
                        print(f"Wiadomość odbita edytowana pomyślnie: {target_message_id}")
                        await update_message_reaction_count(target_channel, bot.get_channel(payload.channel_id), target_message_id, message_id)
                    except discord.NotFound as e:
                        print(f"Sparowana wiadomość nie została znaleziona w docelowym kanale: {target_message_id}")
                    except Exception as e:
                        print(f"Błąd edytowania wiadomości: {e}")

# Nasłuchiwacz zdarzeń dodawania reakcji
@bot.event
async def on_raw_reaction_add(payload):
    # Sprawdź, czy reakcja nie została dodana przez bota
    if payload.member.id == bot.user.id:
        return
    global message_pairs

    # Sprawdź, czy ID wiadomości, do której dodano reakcję, jest w słowniku message_pairs
    reacted_message_id = payload.message_id
    if str(reacted_message_id) in message_pairs:
        target_message_id = message_pairs[str(reacted_message_id)] # reacted_message_id to prawdziwa wiadomość
        bot_message_id = target_message_id
        user_message_id = reacted_message_id
    elif reacted_message_id in message_pairs.inverse:
        target_message_id = message_pairs.inverse[int(reacted_message_id)][0] # reacted_message_id to wiadomość bota
        bot_message_id = reacted_message_id
        user_message_id = target_message_id
    else:
        return
    emoji = str(payload.emoji)
    print(f"Reakcja dodana: {emoji} przez użytkownika {payload.user_id} do wiadomości {reacted_message_id} w kanale {payload.channel_id}")

    # Sprawdź, czy docelowa wiadomość jest w sparowanym kanale 
    for channel_id, data in channel_pairs.items(): # for channel_id, (webhook_url, target_channel_id) in channel_pairs.items():
        if payload.channel_id == int(channel_id):
            target_channel = bot.get_channel(data["paired_id"])
            if target_channel:
                global message_reactions
                reaction_channel = bot.get_channel(payload.channel_id)
            
                if str(reacted_message_id) not in message_reactions:
                    message_reactions[str(reacted_message_id)] = {}
                    message_reactions[str(target_message_id)] = {}
            
                if emoji in message_reactions[str(reacted_message_id)]:
                    message_reactions[str(reacted_message_id)][emoji] += 1 # Licz reakcje z każdej wiadomości za każdym razem? Aby uniknąć desynchronizacji podczas offline???
                else:
                    message_reactions[str(reacted_message_id)][emoji] = 1
                save_data('message_reactions.json.lzma', message_reactions)
                await update_message_reaction_count(target_channel, reaction_channel, bot_message_id, user_message_id)
                try:
                    # Znajdź sparowaną wiadomość w docelowym kanale według ID
                    target_message = await target_channel.fetch_message(target_message_id)

                    if target_message:
                        # Przejdź przez reakcje na sparowanej wiadomości
                        for reaction in target_message.reactions:
                            if str(reaction.emoji) == str(payload.emoji):
                                print(f"Emoji {payload.emoji} jest już wśród reakcji.")
                                break
                        else:
                            # Dodaj reakcję do prawdziwej wiadomości
                            await target_message.add_reaction(payload.emoji)
                            print(f"Reakcja: {payload.emoji} odzwierciedlona w sparowanej wiadomości: {target_message_id}")
                    else:
                        print("Sparowana wiadomość nie została znaleziona")
                except discord.NotFound:
                    print(f"Sparowana wiadomość o ID {target_message_id} nie została znaleziona w docelowym kanale")
                except Exception as e:
                    print(f"Błąd przy obsłudze reakcji: {e}")

# Nasłuchiwacz zdarzeń usunięcia reakcji
@bot.event
async def on_raw_reaction_remove(payload):
    # Sprawdź, czy reakcja nie została dodana przez bota
    if payload.user_id == bot.user.id:
        return

    # Sprawdź, czy ID wiadomości, do której usunięto reakcję, jest w słowniku message_pairs
    reacted_message_id = payload.message_id
    if str(reacted_message_id) in message_pairs:
        target_message_id = message_pairs[str(reacted_message_id)]  # reacted_message_id to prawdziwa wiadomość
        bot_message_id = target_message_id
        user_message_id = reacted_message_id
    elif reacted_message_id in message_pairs.inverse:
        target_message_id = message_pairs.inverse[int(reacted_message_id)][0]  # reacted_message_id to wiadomość bota
        bot_message_id = reacted_message_id
        user_message_id = target_message_id
    else:
        return
    print(f"Reakcja usunięta: {payload.emoji} przez użytkownika {payload.user_id} z wiadomości {reacted_message_id} w kanale {payload.channel_id}")
    reaction_channel = bot.get_channel(payload.channel_id)
    users_reacted = [] 
    reactMsg = await reaction_channel.fetch_message(payload.message_id)
    # Przejdź przez reakcje na wiadomości payload.message_id
    for reaction in reactMsg.reactions:
        if str(reaction.emoji) == str(payload.emoji):
            # Sprawdź, czy są inni użytkownicy (oprócz bota), którzy zareagowali na oryginalną wiadomość (to zapobiega usuwaniu reakcji, gdy jest ona nadal używana pod wiadomością)
            async for user in reaction.users():
                if user.id != bot.user.id:
                    users_reacted.append(user)
    
    # Sprawdź, czy docelowa wiadomość jest w sparowanym kanale
    for channel_id, data in channel_pairs.items(): #for channel_id, (webhook_url, target_channel_id) in channel_pairs.items():
        if payload.channel_id == int(channel_id):
            # Pobierz docelowy kanał
            target_channel = bot.get_channel(data["paired_id"])

            if target_channel:
                global message_reactions
                
                emoji = str(payload.emoji)
            
                if str(reacted_message_id) not in message_reactions:
                    message_reactions[str(reacted_message_id)] = {}
                    message_reactions[str(target_message_id)] = {}
            
                if message_reactions[str(reacted_message_id)][emoji] <= 0:
                    message_reactions[str(reacted_message_id)][emoji] = 0
                    print("Negatywna wartość reakcji!! Niepoprawna liczba reakcji negatywnej uniknięta!")
                elif emoji in message_reactions[str(reacted_message_id)]:
                    message_reactions[str(reacted_message_id)][emoji] -= 1
                else:
                    message_reactions[str(reacted_message_id)][emoji] = 0
                save_data('message_reactions.json.lzma', message_reactions)
                await update_message_reaction_count(target_channel, reaction_channel, bot_message_id, user_message_id)
                try:
                    # Znajdź sparowaną wiadomość w docelowym kanale według ID
                    target_message = await target_channel.fetch_message(target_message_id)

                    if target_message:
                        if len(users_reacted) == 0:
                            # Usuń reakcję
                            await target_message.remove_reaction(payload.emoji, bot.user)
                            print(f"Reakcja usunięta z sparowanej wiadomości: {payload.emoji}")
                        else:
                            print(f"Reakcja nie została usunięta z sparowanej wiadomości: {payload.emoji} (Inni użytkownicy zareagowali)")
                    else:
                        print("Sparowana wiadomość nie została znaleziona")
                except discord.NotFound:
                    print(f"Sparowana wiadomość o ID {target_message_id} nie została znaleziona w docelowym kanale")
                except Exception as e:
                    print(f"Błąd przy usuwaniu reakcji: {e}")

async def update_message_reaction_count(target_channel, reaction_channel, bot_message_id, user_message_id):
    global message_reactions
    # Połącz liczbę reakcji dla obu wiadomości
    user_emoji_counts = message_reactions.get(str(user_message_id), {})
    bot_emoji_counts = message_reactions.get(str(bot_message_id), {})

    # Utwórz słownik z połączoną liczbą emoji
    combined_emoji_counts = {}
    for emoji, count in user_emoji_counts.items():
        combined_emoji_counts[emoji] = combined_emoji_counts.get(emoji, 0) + count

    for emoji, count in bot_emoji_counts.items():
        combined_emoji_counts[emoji] = combined_emoji_counts.get(emoji, 0) + count

    # Utwórz reprezentację tekstową liczby emoji
    emoji_count_str = " ".join([f"{count}-{emoji}" for emoji, count in combined_emoji_counts.items() if count > 1])

    # Zaktualizuj treść wiadomości z reakcji z połączoną liczbą emoji
    if combined_emoji_counts:
        try:
            bot_message = await reaction_channel.fetch_message(bot_message_id)
            user_message = await target_channel.fetch_message(user_message_id)
            channel = reaction_channel
        except discord.errors.NotFound:
            bot_message = await target_channel.fetch_message(bot_message_id)
            user_message = await reaction_channel.fetch_message(user_message_id)
            channel = target_channel
        if bot_message and user_message:
            paired_webhook_url = channel_pairs[str(channel.id)]["webhook_url"]
            webhook = discord.Webhook.from_url(paired_webhook_url, client=bot)
            if emoji_count_str:
                new_content = f"{user_message.content.split('(')[0].strip()} ({emoji_count_str})"
            else:
                new_content = user_message.content  # Użyj oryginalnej treści, jeśli emoji_count_str jest pusty
            await webhook.edit_message(
                int(bot_message_id),
                content=new_content,
            )

# Uruchom bota
if __name__ == '__main__':
    bot.run(TOKEN, reconnect=True)