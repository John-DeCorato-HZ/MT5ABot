import inspect
import itertools

from discord.ext.commands.formatter import Paginator, HelpFormatter, GroupMixin, Command, CommandError


class SortedHelpFormatter(HelpFormatter):
    """Overridden help formatter that implements sorted command names.

    Not sure why is isn't in the base code in discord.py since it's a
    one line change but whatever.

    Parameters
    -----------
    show_hidden : bool
        Dictates if hidden commands should be shown in the output.
        Defaults to ``False``.
    show_check_failure : bool
        Dictates if commands that have their :attr:`Command.checks` failed
        shown. Defaults to ``False``.
    width : int
        The maximum number of characters that fit in a line.
        Defaults to 80.
    """

    def __init__(self, show_hidden=False, show_check_failure=False, width=80):
        self.width = width
        self.show_hidden = show_hidden
        self.show_check_failure = show_check_failure

    def has_subcommands(self):
        """bool : Specifies if the command has subcommands."""
        return isinstance(self.command, GroupMixin)

    def is_bot(self):
        """bool : Specifies if the command being formatted is the bot itself."""
        return self.command is self.context.bot

    def is_cog(self):
        """bool : Specifies if the command being formatted is actually a cog."""
        return not self.is_bot() and not isinstance(self.command, Command)

    def shorten(self, text):
        """Shortens text to fit into the :attr:`width`."""
        if len(text) > self.width:
            return text[:self.width - 3] + '...'
        return text

    @property
    def max_name_size(self):
        """int : Returns the largest name length of a command or if it has subcommands
        the largest subcommand name."""
        try:
            commands = self.command.commands if not self.is_cog() else self.context.bot.commands
            if commands:
                return max(map(lambda c: len(c.name) if self.show_hidden or not c.hidden else 0, commands.values()))
            return 0
        except AttributeError:
            return len(self.command.name)

    @property
    def clean_prefix(self):
        """The cleaned up invoke prefix. i.e. mentions are ``@name`` instead of ``<@id>``."""
        user = self.context.bot.user
        # this breaks if the prefix mention is not the bot itself but I
        # consider this to be an *incredibly* strange use case. I'd rather go
        # for this common use case rather than waste performance for the
        # odd one.
        return self.context.prefix.replace(user.mention, '@' + user.name)

    def get_command_signature(self):
        """Retrieves the signature portion of the help page."""
        result = []
        prefix = self.clean_prefix
        cmd = self.command
        parent = cmd.full_parent_name
        if len(cmd.aliases) > 0:
            aliases = '|'.join(cmd.aliases)
            fmt = '{0}[{1.name}|{2}]'
            if parent:
                fmt = '{0}{3} [{1.name}|{2}]'
            result.append(fmt.format(prefix, cmd, aliases, parent))
        else:
            name = prefix + cmd.name if not parent else prefix + parent + ' ' + cmd.name
            result.append(name)

        params = cmd.clean_params
        if len(params) > 0:
            for name, param in params.items():
                if param.default is not param.empty:
                    # We don't want None or '' to trigger the [name=value] case and instead it should
                    # do [name] since [name=None] or [name=] are not exactly useful for the user.
                    should_print = param.default if isinstance(param.default, str) else param.default is not None
                    if should_print:
                        result.append('[{}={}]'.format(name, param.default))
                    else:
                        result.append('[{}]'.format(name))
                elif param.kind == param.VAR_POSITIONAL:
                    result.append('[{}...]'.format(name))
                else:
                    result.append('<{}>'.format(name))

        return ' '.join(result)

    def get_ending_note(self):
        command_name = self.context.invoked_with
        return "Type {0}{1} command for more info on a command.\n" \
               "You can also type {0}{1} category for more info on a category.".format(self.clean_prefix, command_name)

    def filter_command_list(self):
        """Returns a filtered list of commands based on the two attributes
        provided, :attr:`show_check_failure` and :attr:`show_hidden`. Also
        filters based on if :meth:`is_cog` is valid.
        Returns
        --------
        iterable
            An iterable with the filter being applied. The resulting value is
            a (key, value) tuple of the command name and the command itself.
        """

        def predicate(tuple):
            cmd = tuple[1]
            if self.is_cog():
                # filter commands that don't exist to this cog.
                if cmd.instance is not self.command:
                    return False

            if cmd.hidden and not self.show_hidden:
                return False

            if self.show_check_failure:
                # we don't wanna bother doing the checks if the user does not
                # care about them, so just return true.
                return True

            try:
                return cmd.can_run(self.context)
            except CommandError:
                return False

        iterator = self.command.commands.items() if not self.is_cog() else self.context.bot.commands.items()
        return filter(predicate, iterator)

    def _add_subcommands_to_page(self, max_width, commands):
        def get_name(c):
            return c[0]
        sorted_commands = sorted(commands, key=get_name)
        for name, command in sorted_commands:
            if name in command.aliases:
                # skip aliases
                continue

            entry = '  {0:<{width}} {1}'.format(name, command.short_doc, width=max_width)
            shortened = self.shorten(entry)
            self._paginator.add_line(shortened)

    def format_help_for(self, context, command_or_bot):
        """Formats the help page and handles the actual heavy lifting of how
        the help command looks like. To change the behaviour, override the
        :meth:`format` method.
        Parameters
        -----------
        context : :class:`Context`
            The context of the invoked help command.
        command_or_bot : :class:`Command` or :class:`Bot`
            The bot or command that we are getting the help of.
        Returns
        --------
        list
            A paginated output of the help command.
        """
        self.context = context
        self.command = command_or_bot
        return self.format()

    def format(self):
        """Handles the actual behaviour involved with formatting.
        To change the behaviour, this method should be overridden.
        Returns
        --------
        list
            A paginated output of the help command.
        """
        self._paginator = Paginator()

        # we need a padding of ~80 or so

        description = self.command.description if not self.is_cog() else inspect.getdoc(self.command)

        if description:
            # <description> portion
            self._paginator.add_line(description, empty=True)

        if isinstance(self.command, Command):
            # <signature portion>
            signature = self.get_command_signature()
            self._paginator.add_line(signature, empty=True)

            # <long doc> section
            if self.command.help:
                self._paginator.add_line(self.command.help, empty=True)

            # end it here if it's just a regular command
            if not self.has_subcommands():
                self._paginator.close_page()
                return self._paginator.pages

        max_width = self.max_name_size

        def category(tup):
            cog = tup[1].cog_name
            # we insert the zero width space there to give it approximate
            # last place sorting position.
            return cog + ':' if cog is not None else '\u200bNo Category:'

        if self.is_bot():
            data = sorted(self.filter_command_list(), key=category)
            for category, commands in itertools.groupby(data, key=category):
                # there simply is no prettier way of doing this.
                commands = list(commands)
                if len(commands) > 0:
                    self._paginator.add_line(category)

                self._add_subcommands_to_page(max_width, commands)
        else:
            self._paginator.add_line('Commands:')
            self._add_subcommands_to_page(max_width, self.filter_command_list())

        # add the ending note
        self._paginator.add_line()
        ending_note = self.get_ending_note()
        self._paginator.add_line(ending_note)
        return self._paginator.pages
