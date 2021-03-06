#
# Copyright 2016 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# -----------------------------------------------------------------------------

import logging

from journal import transaction, global_store_manager
from journal.messages import transaction_message

from sawtooth.exceptions import InvalidTransactionError


logger = logging.getLogger(__name__)

VALID_HANDS = ('ROCK', 'PAPER', 'SCISSORS')
STATES = ('OPEN', 'COMPLETE')


def _register_transaction_types(ledger):
    ledger.register_message_handler(
        RPSTransactionMessage,
        transaction_message.transaction_message_handler,
    )
    ledger.add_transaction_store(RPSTransaction)


class RPSTransactionMessage(transaction_message.TransactionMessage):
    MessageType = "/RPS/Transaction"

    def __init__(self, minfo=None):
        if minfo is None:
            minfo = {}

        super(RPSTransactionMessage, self).__init__(minfo)

        tinfo = minfo.get('Transaction', {})
        self.Transaction = RPSTransaction(tinfo)


class RPSTransaction(transaction.Transaction):
    TransactionTypeName = '/RPSTransaction'
    TransactionStoreType = global_store_manager.KeyValueStore
    MessageType = RPSTransactionMessage

    def __init__(self, minfo=None):
        if minfo is None:
            minfo = {}

        super(RPSTransaction, self).__init__(minfo)

        logger.debug("minfo: %s", repr(minfo))
        self._name = minfo['Name'] if 'Name' in minfo else None
        self._action = minfo['Action'] if 'Action' in minfo else None
        self._hand = minfo['Hand'] if 'Hand' in minfo else None
        self._players = minfo['Players'] if 'Players' in minfo else None

    def __str__(self):
        try:
            oid = self.OriginatorID
        except AssertionError:
            oid = "unknown"
        return "({0} {1} {2})".format(oid, self._name, self._hand)

    def check_valid(self, store):
        super(RPSTransaction, self).check_valid(store)

        logger.debug('checking %s', str(self))

        if self._name is None or self._name == '':
            raise InvalidTransactionError('name not set')

        if self._action is None or self._action == '':
            raise InvalidTransactionError('action not set')

        if self._action == 'CREATE':
            if self._name in store:
                raise InvalidTransactionError('game already exists')
            if (not isinstance(self._players, (int, long)) or not
                    self._players > 0):
                raise InvalidTransactionError('players must be a positive integer' +
                                   'larger then 0: %s (%s)' %
                                   (self._players, type(self._players)))
        elif self._action == 'SHOOT':
            if self._hand is None:
                raise InvalidTransactionError('SHOOT requires hand')

            if self._hand not in VALID_HANDS:
                raise InvalidTransactionError('invalid hand')

            if self._name not in store:
                raise InvalidTransactionError('no such game')

            players = store[self._name]['Players']
            state = store[self._name]['State']
            if state == 'COMPLETE':
                raise InvalidTransactionError('game complete')
            elif len(store[self._name]['Hands']) >= players:
                raise InvalidTransactionError('all players shown their hand but' +
                                   'game state not set to complete')
            elif state == 'OPEN':
                recorded_hand = store[self._name]['Hands']\
                    .get(self.OriginatorID)
                if recorded_hand is not None:
                    raise InvalidTransactionError('hand already registered')
            else:
                raise InvalidTransactionError('invalid game state')
        else:
            raise InvalidTransactionError('invalid action')

    def _is_winner(self, hand_a, hand_b):
        resolutions = (
            ('ROCK', 'ROCK', 'TIE'),
            ('ROCK', 'PAPER', 'LOSE'),
            ('ROCK', 'SCISSORS', 'WIN'),
            ('PAPER', 'PAPER', 'TIE'),
            ('PAPER', 'ROCK', 'WIN'),
            ('PAPER', 'SCISSORS', 'LOSE'),
            ('SCISSORS', 'SCISSORS', 'TIE'),
            ('SCISSORS', 'PAPER', 'WIN'),
            ('SCISSORS', 'ROCK', 'LOSE'),
        )
        for a, b, resolution in resolutions:
            if hand_a == a and hand_b == b:
                return resolution
        raise InvalidTransactionError("no resolution found for hand_a: %s, hand_b: %s"
                           % (hand_a, hand_b))

    def apply(self, store):
        logger.debug('apply %s', str(self))

        if self._name in store:
            game = store[self._name].copy()
        elif self._hand is not None:
            raise InvalidTransactionError("Hand to be played without a" +
                               "game registered (should not happen)")
        else:
            if self._players == 1:
                game = {
                    'State': 'OPEN',
                    'Hands': {},
                    'Players': 2,
                    'InitialID': self.OriginatorID,
                    'Computer': True
                }
            else:
                game = {
                    'State': 'OPEN',
                    'Hands': {},
                    'Players': self._players,
                    'InitialID': self.OriginatorID,
                }

        if self._hand is not None:
            if self.OriginatorID in game['Hands']:
                raise InvalidTransactionError('hand already registered')

            if self._hand not in VALID_HANDS:
                raise InvalidTransactionError('invalid hand')

            game['Hands'][self.OriginatorID] = self._hand

        nr_hands = len(game['Hands'])
        if game['State'] != 'OPEN' and nr_hands < game['Players']:
            raise InvalidTransactionError("state not open while missing hands")
        elif nr_hands == game['Players']:
            # find out how won
            initial_id = game['InitialID']
            hand_a = game['Hands'][initial_id]
            results = {}
            for player, hand_b in game['Hands'].iteritems():
                if player == initial_id:
                    continue
                results[player] = self._is_winner(hand_a, hand_b)
            game['Results'] = results
            game['State'] = 'COMPLETE'
        store[self._name] = game

    def dump(self):
        result = super(RPSTransaction, self).dump()

        result['Action'] = self._action
        result['Name'] = self._name
        if self._hand is not None:
            result['Hand'] = self._hand
        if self._players is not None:
            result['Players'] = self._players
        return result
