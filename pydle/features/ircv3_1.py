## ircv3_1.py
# IRCv3.1 full spec support.
from . import sasl
from . import tls
from .. import protocol

__all__ = [ 'IRCv3_1Support' ]


NO_ACCOUNT = '*'

class IRCv3_1Support(sasl.SASLSupport, tls.TLSSupport):
    """ Support for IRCv3.1's base and optional extensions. """

    ## Internal overrides.

    def _create_user(self, nickname):
        super()._create_user(nickname)
        if ('account-notify' in self._capabilities and self._capabilities['account-notify']) or ('extended-join' in self._capabilities and self._capabilites['extended-join']):
            self.users[nickname]['account'] = None


    ## IRC callbacks.

    def on_capability_account_notify_available(self):
        """ Take note of user account changes. """
        return True

    def on_capability_away_notify_available(self):
        """ Take note of AWAY messages. """
        return True

    def on_capability_extended_join_available(self):
        """ Take note of user account and realname on JOIN. """
        return True

    def on_capability_multi_prefix_available(self):
        """ Thanks to how underlying client code works we already support multiple prefixes. """
        return True

    def on_capability_tls_available(self):
        """ We never need to request this explicitly. """
        return False


    ## Message handlers.

    def on_raw_account(self, message):
        """ Changes in the associated account for a nickname. """
        if 'account-notify' not in self._capabilities or not self._capabilities['account-notify']:
            return

        nick, user, host = protocol.parse_user(message.source)
        account = message.params[0]

        if nick not in self.users:
            return

        self._sync_user(nick, user, host)
        if account == NO_ACCOUNT:
            account = None
        self.users[nick]['account'] = account

    def on_raw_away(self, message):
        """ Process AWAY messages. """
        if 'away-notify' not in self._capabilities or not self._capabilities['away-notify']:
            return

        nick, user, host = protocol.parse_user(message.source)
        if nick not in self.users:
            return

        self._sync_user(nick, user, host)
        self.users[nick]['away'] = len(message.params) > 0
        self.users[nick]['away_message'] = message.params[0] if len(message.params) > 0 else None

    def on_raw_join(self, message):
        """ Process extended JOIN messages. """
        if 'extended-join' in self._capabilities and self._capabilities['extended-join']:
            nick, user, host = protocol.parse_user(message.source)
            channels, account, realname = message.params

            self._sync_user(nick, user, host)

            # Emit a fake join message.
            fakemsg = self._construct_message('JOIN', channels, source=message.source)
            super().on_raw_join(fakemsg)

            if account == NO_ACCOUNT:
                account = None
            self.users[nick]['account'] = account
            self.users[nick]['realname'] = realname
        else:
            super().on_raw_join(message)
