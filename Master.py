import asyncio
import os
import sys
sys.path.insert(0, "lib")
import logging
import logging.handlers
import traceback
import datetime
import subprocess

try:
    from discord.ext import commands
    import discord
except ImportError:
    print("Discord.py is not installed.\n"
          "Install it you stupid\n")

    sys.exit(1)

from moduls.utils.settings import Settings
from moduls.utils.dataIO import dataIO
from moduls.utils.chat_formatting import inline
from collections import Counter
from io import TextIOWrapper

#
# Bugs bitch
#
#   red  load        module     .
#
#
#
#
#                 https://github.com/Rapptz/RoboDanny/
#

description = "MasterBot - A super duper awesome Discord bot by Horizon based off red-discordbot and discord.py using XK2 as a base."


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):

        def prefix_manager(bot, message):
            """
            Hows prefixes if set.
            If there isn't any
            it will return the global prefixes instead.

            Requires a Bot instance and a Message object to be
            passed as arguments.
            """
            return bot.settings.get_prefixes(message.server)

        self.counter = Counter()
        self.uptime = datetime.datetime.utcnow()  # Refreshed before login
        self._message_modifiers = []
        self.settings = Settings()
        self._intro_displayed = False
        self._shutdown_mode = None
        self.logger = set_logger(self)
        self._last_exception = None
        self.oauth_url = ""
        if 'self_bot' in kwargs:
            self.settings.self_bot = kwargs['self_bot']
        else:
            kwargs['self_bot'] = self.settings.self_bot
            if self.settings.self_bot:
                kwargs['pm_help'] = False
        super().__init__(*args, command_prefix=prefix_manager, **kwargs)

    async def send_message(self, *args, **kwargs):
        if self._message_modifiers:
            if "content" in kwargs:
                pass
            elif len(args) == 2:
                args = list(args)
                kwargs["content"] = args.pop()
            else:
                return await super().send_message(*args, **kwargs)

            content = kwargs['content']
            for m in self._message_modifiers:
                try:
                    content = str(m(content))
                except:   # Faulty modifiers should not
                    pass  # break send_message
            kwargs['content'] = content

        return await super().send_message(*args, **kwargs)

    async def shutdown(self, *, restart=False):
        """Gracefully Stops Master with exit code 0

        If restart is True, the exit code will be 26 instead
        The launcher automatically restarts Master when that happens"""
        self._shutdown_mode = not restart
        await self.logout()

    def add_message_modifier(self, func):
        """
        Adds a message modifier to the bot

        A message modifier is a callable that accepts a message's
        content as the first positional argument.
        Before a message gets sent, func will get called with
        the message's content as the only argument. The message's
        content will then be modified to be the func's return
        value.
        Exceptions thrown by the callable will be catched and
        silenced.
        """
        if not callable(func):
            raise TypeError("The message modifier function "
                            "must be a callable.")

        self._message_modifiers.append(func)

    def remove_message_modifier(self, func):
        """Removes a message modifier from the bot"""
        if func not in self._message_modifiers:
            raise RuntimeError("Function not present in the message "
                               "modifiers.")

        self._message_modifiers.remove(func)

    def clear_message_modifiers(self):
        """Removes all message modifiers from the bot"""
        self._message_modifiers.clear()

    async def send_cmd_help(self, ctx):
        if ctx.invoked_subcommand:
            pages = self.formatter.format_help_for(ctx, ctx.invoked_subcommand)
            for page in pages:
                await self.send_message(ctx.message.channel, page)
        else:
            pages = self.formatter.format_help_for(ctx, ctx.command)
            for page in pages:
                await self.send_message(ctx.message.channel, page)

    def user_allowed(self, message):
        author = message.author

        if author.bot:
            return False
#modul
        if author == self.user:
            return self.settings.self_bot

        mod_cog = self.get_cog('Mod')
        global_ignores = self.get_cog('Owner').global_ignores

        if self.settings.owner == author.id:
            return True

        if author.id in global_ignores["blacklist"]:
            return False

        if global_ignores["whitelist"]:
            if author.id not in global_ignores["whitelist"]:
                return False

        if not message.channel.is_private:
            server = message.server
            names = (self.settings.get_server_admin(
                server), self.settings.get_server_mod(server))
            results = map(
                lambda name: discord.utils.get(author.roles, name=name),
                names)
            for r in results:
                if r is not None:
                    return True

        if mod_cog is not None:
            if not message.channel.is_private:
                if message.server.id in mod_cog.ignore_list["SERVERS"]:
                    return False

                if message.channel.id in mod_cog.ignore_list["CHANNELS"]:
                    return False

        return True

    async def pip_install(self, name, *, timeout=None):
        """
        Installs a pip package in the local 'lib' folder in a thread safe
        way. On Mac systems the 'lib' folder is not used.
        Can specify the max seconds to wait for the task to complete

        Returns a bool indicating if the installation was successful
        """

        IS_MAC = sys.platform == "darwin"
        interpreter = sys.executable

        if interpreter is None:
            raise RuntimeError("Couldn't find Python's interpreter")

        args = [
            interpreter, "-m",
            "pip", "install",
            "--upgrade",
            "--target", "lib",
            name
        ]

        if IS_MAC: # --target is a problem on Homebrew. See PR #552
            args.remove("--target")
            args.remove("lib")

        def install():
            code = subprocess.call(args)
            sys.path_importer_cache = {}
            return not bool(code)

        response = self.loop.run_in_executor(None, install)
        return await asyncio.wait_for(response, timeout=timeout)


class Formatter(commands.HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _add_subcommands_to_page(self, max_width, commands):
        for name, command in sorted(commands, key=lambda t: t[0]):
            if name in command.aliases:
                # skip aliases
                continue

            entry = '  {0:<{width}} {1}'.format(name, command.short_doc,
                                                width=max_width)
            shortened = self.shorten(entry)
            self._paginator.add_line(shortened)


def initialize(bot_class=Bot, formatter_class=Formatter):
    formatter = formatter_class(show_check_failure=False)

    bot = bot_class(formatter=formatter, description=description, pm_help=None)

    import __main__
    __main__.send_cmd_help = bot.send_cmd_help  # Backwards
    __main__.user_allowed = bot.user_allowed    # compatibility
    __main__.settings = bot.settings            # sucks # will remove

    async def get_oauth_url():
        try:
            data = await bot.application_info()
        except Exception as e:
            return "Couldn't retrieve invite link.Error: {}".format(e)
        return discord.utils.oauth_url(data.id)

    async def set_bot_owner():
        if bot.settings.self_bot:
            bot.settings.owner = bot.user.id
            return "[Selfbot mode]"

        if bot.settings.owner:
            owner = discord.utils.get(bot.get_all_members(),
                                      id=bot.settings.owner)
            if not owner:
                try:
                    owner = await bot.get_user_info(bot.settings.owner)
                except:
                    owner = None
                if not owner:
                    owner = bot.settings.owner  # Just the ID then
            return owner

        how_to = "Do `/set owner` in chat to set it"

        if bot.user.bot:  # Can fetch owner
            try:
                data = await bot.application_info()
                bot.settings.owner = data.owner.id
                bot.settings.save_settings()
                return data.owner
            except:
                return "Failed to fetch owner. " + how_to
        else:
            return "Yet to be set. " + how_to
#moduls
    @bot.event
    async def on_ready():
        if bot._intro_displayed:
            return
        bot._intro_displayed = True

        owner_cogs = bot.get_cog('Owner')
        total_cogs = len(owner_cogs._list_cogs())
        users = len(set(bot.get_all_members()))
        servers = len(bot.servers)
        channels = len([c for c in bot.get_all_channels()])

        login_time = datetime.datetime.utcnow() - bot.uptime
        login_time = login_time.seconds + login_time.microseconds/1E6
#deets
        print("Login successful. ({}ms)\n".format(login_time))

        owner = await set_bot_owner()

        print("-----------------")
        print("Master Bot")
        print("-----------------")
        print(str(bot.user))
        print("\nConnected to:")
        print("{} servers".format(servers))
        print("{} channels".format(channels))
        print("{} users\n".format(users))
        prefix_label = 'Prefix'
        if len(bot.settings.prefixes) > 1:
            prefix_label += 'es'
        print("{}: {}".format(prefix_label, " ".join(bot.settings.prefixes)))
        print("Owner: " + str(owner))
        print("{}/{} active modules with {} commands".format(
            len(bot.cogs), total_cogs, len(bot.commands)))
        print("-----------------")
#moduls
        if bot.settings.token and not bot.settings.self_bot:
            print("\nLink to invite bot:")
            url = await get_oauth_url()
            bot.oauth_url = url
            print("bit.ly/MasterRaceBot")

        print("\nOfficial server: https://bit.ly/MasterRace")

        print("TODO: Annouce ver. 1.9.0 Master Revision ")

        await bot.get_cog('Owner').disable_commands()

    @bot.event
    async def on_resumed():
        bot.counter["session_resumed"] += 1

    @bot.event
    async def on_command(command, ctx):
        bot.counter["processed_commands"] += 1

    @bot.event
    async def on_message(message):
        bot.counter["messages_read"] += 1
        if bot.user_allowed(message):
            await bot.process_commands(message)

    @bot.event
    async def on_command_error(error, ctx):
        channel = ctx.message.channel
        if isinstance(error, commands.MissingRequiredArgument):
            await bot.send_cmd_help(ctx)
        elif isinstance(error, commands.BadArgument):
            await bot.send_cmd_help(ctx)
        elif isinstance(error, commands.DisabledCommand):
            await bot.send_message(channel, "Nope no command.")
        elif isinstance(error, commands.CommandInvokeError):
            # A bit hacky, couldn't find a better way
            no_dms = "Nope no dms"
            is_help_cmd = ctx.command.qualified_name == "help"
            is_forbidden = isinstance(error.original, discord.Forbidden)
            if is_help_cmd and is_forbidden and error.original.text == no_dms:
                msg = ("I Can't DM you dood. Either"
                       " you blocked me (Why would you tho?) or you disabled DMs in this server. (If you did is probs cuz humans can be dicks)")
                await bot.send_message(channel, msg)
                return

            bot.logger.exception("Exception in command '{}'".format(
                ctx.command.qualified_name), exc_info=error.original)
            message = ("Error in command '{}'. Oops something broke. (I didn't mean it I SWEAR!!) check the console or the"
                       "logs for the deets. But if you can't (Sry 'bout dat), ask your local server admin to contact @horizon#0223 (and fast too.)"
                       "".format(ctx.command.qualified_name))
            log = ("Exception in command '{}'\n"
                   "".format(ctx.command.qualified_name))
            log += "".join(traceback.format_exception(type(error), error,
                                                      error.__traceback__))
            bot._last_exception = log
            await ctx.bot.send_message(channel, inline(message))
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        elif isinstance(error, commands.NoPrivateMessage):
            await bot.send_message(channel, "*Honey that command don't work here"
                                            "go in a server and try that again*.")
        elif isinstance(error, commands.CommandOnCooldown):
            await bot.send_message(channel, "Chill dood"
                                            "Then Try again in {:.2f}s"
                                            "".format(error.retry_after))
        else:
            bot.logger.exception(type(error).__name__, exc_info=error)

    return bot
#moduls.json

def check_folders():
    folders = ("data", "data/Master", "moduls", "moduls/utils")
    for folder in folders:
        if not os.path.exists(folder):
            print("Creating " + folder + " folder...")
            os.makedirs(folder)


def interactive_setup(settings):
    first_run = settings.bot_settings == settings.default_settings

    if first_run:
        print("MasterBot - (How haven't you gone through this already?) First run setup!!\n")
        print("If you haven't already, create a new bot account and name it Masterbot or imma kill you\n")
        print("(Im waiting)")

    if not settings.login_credentials:
        print("\nTOKEN IN HERE!!:")
        while settings.token is None and settings.email is None:
            choice = input("> ")
            if "@" not in choice and len(choice) >= 50:  # Assuming token
                settings.token = choice
            elif "@" in choice:
                settings.email = choice
                settings.password = input("\nPassword> ")
            else:
                print("DAS A FAKE TOKEN!!!!!.")
        settings.save_settings()

    if not settings.prefixes:
        print("\nChoose prefix / PLZ")
        confirmation = False
        while confirmation is False:
            new_prefix = ensure_reply("\nPrefix> ").strip()
            print("\nIf {0} isn't / imma kill you.\nYou "
                  "{0}help is the help command (if you forgot DON'T FORGET AGAIN)"
                  "\nYes means Good its is a / No means it isn't a / and your gonna change it.".format(
                      new_prefix))
            confirmation = get_answer()
        settings.prefixes = [new_prefix]
        settings.save_settings()

    if first_run:
        print("\nAdmin role")
        settings.default_admin = input("\nAdmin role> ")
        if settings.default_admin == "":
            settings.default_admin = ""
        settings.save_settings()

        print("\nMod role")
        settings.default_mod = input("\nModerator role> ")
        if settings.default_mod == "":
            settings.default_mod = ""
        settings.save_settings()

        print("\nIt is done. You cannot type annymore.")
        input("\n")


def set_logger(bot):
    logger = logging.getLogger("Master")
    logger.setLevel(logging.INFO)

    Master_format = logging.Formatter(
        '%(asctime)s %(levelname)s %(cog)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(Master_format)
    if bot.settings.debug:
        stdout_handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    else:
        stdout_handler.setLevel(logging.INFO)
        logger.setLevel(logging.INFO)

    fhandler = logging.handlers.RotatingFileHandler(
        filename='data/Master/master.log', encoding='utf-8', mode='a',
        maxBytes=10**7, backupCount=5)
    fhandler.setFormatter(Master_format)

    logger.addHandler(fhandler)
    logger.addHandler(stdout_handler)

    dpy_logger = logging.getLogger("discord")
    if bot.settings.debug:
        dpy_logger.setLevel(logging.DEBUG)
    else:
        dpy_logger.setLevel(logging.WARNING)
    handler = logging.FileHandler(
        filename='data/Master/discord.log', encoding='utf-8', mode='a')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(cog)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]"))
    dpy_logger.addHandler(handler)

    return logger


def ensure_reply(msg):
    choice = ""
    while choice == "":
        choice = input(msg)
    return choice


def get_answer():
    choices = ("yes", "y", "no", "n")
    c = ""
    while c not in choices:
        c = input(">").lower()
    if c.startswith("y"):
        return True
    else:
        return False


def set_cog(cog, value):  # TODO: move this out of Master.py
    data = dataIO.load_json("data/Master/moduls.json")
    data[cog] = value
    dataIO.save_json("data/Master/moduls.json", data)


def load_cogs(bot):
    defaults = ("alias", "audio", "customcom", "downloader", "economy",
                "general", "image", "mod", "streams", "trivia")

    try:
        registry = dataIO.load_json("data/Master/moduls.json")
    except:
        registry = {}

    bot.load_extension('moduls.owner')
    owner_cogs = bot.get_cog('Owner')
    if owner_cogs is None:
        print("A big chunk of MasterBot is broke somehow (the core module) talk to @horizon#0223 about this")
        exit(1)

    if bot.settings._no_cogs:
        bot.logger.debug("Skipping initial modules loading (--no-modules)")
        if not os.path.isfile("data/Master/moduls.json"):
            dataIO.save_json("data/Master/moduls.json", {})
        return

    failed = []
    extensions = owner_cogs._list_cogs()

    if not registry:  # All default cogs enabled by default
        for ext in defaults:
            registry["cogs." + ext] = True

    for extension in extensions:
        if extension.lower() == "cogs.owner":
            continue
        to_load = registry.get(extension, False)
        if to_load:
            try:
                owner_cogs._load_cogs(extension)
            except Exception as e:
                print("{}: {}".format(e.__class__.__name__, str(e)))
                bot.logger.exception(e)
                failed.append(extension)
                registry[extension] = False

    dataIO.save_json("data/Master/moduls.json", registry)

    if failed:
        print("\nFailed to load: {}\n".format(" ".join(failed)))


def main(bot):
    check_folders()
    if not bot.settings.no_prompt:
        interactive_setup(bot.settings)
    load_cogs(bot)

    if bot.settings._dry_run:
        print("Quitting: dry run")
        bot._shutdown_mode = True
        exit(0)

    print("Logging into Discord...")
    bot.uptime = datetime.datetime.utcnow()

    if bot.settings.login_credentials:
        yield from bot.login(*bot.settings.login_credentials,
                             bot=not bot.settings.self_bot)
    else:
        print("No credentials available to login.")
        raise RuntimeError()
    yield from bot.connect()


if __name__ == '__main__':
    sys.stdout = TextIOWrapper(sys.stdout.detach(),
                               encoding=sys.stdout.encoding,
                               errors="replace",
                               line_buffering=True)
    bot = initialize()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main(bot))
    except discord.LoginFailure:
        bot.logger.error(traceback.format_exc())
        if not bot.settings.no_prompt:
            choice = input("Wrong Login info. If they worked before "
                           "Discord might be having temporary technical "
                           "issues.\nIn this case, press enter and try again "
                           "later.\nOtherwise you can type 'reset' to reset "
                           "the current credentials and set them again the "
                           "next start.\n> ")
            if choice.lower().strip() == "reset":
                bot.settings.token = None
                bot.settings.email = None
                bot.settings.password = None
                bot.settings.save_settings()
                print("Login credentials have been reset.")
    except KeyboardInterrupt:
        loop.run_until_complete(bot.logout())
    except Exception as e:
        bot.logger.exception("Fatal exception, attempting graceful logout")
        loop.run_until_complete(bot.logout())
    finally:
        loop.close()
        if bot._shutdown_mode is True:
            exit(0)
        elif bot._shutdown_mode is False:
            exit(26) # Restart
        else:
            exit(1)
lol = laugh
@bot.event
async def on_message(lol):
    await self.bot.say("*Controls you*")
print ("Master")