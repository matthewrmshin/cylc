# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2019 NIWA & British Crown (Met Office) & Contributors.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Publisher for workflow runtime API."""

import asyncio

import zmq

from cylc.flow import LOG
from cylc.flow.network import ZMQSocketBase


async def gather_coros(coro_func, items):
    """Gather multi-part send coroutines"""
    gathers = ()
    for item in items:
        gathers += (coro_func(*item),)
    await asyncio.gather(*gathers)


def serialize_data(data, serializer, *args, **kwargs):
    """Serialize by specified method."""
    if callable(serializer):
        return serializer(data, *args, **kwargs)
    if isinstance(serializer, str):
        return getattr(data, serializer)(*args, **kwargs)
    return data


class WorkflowPublisher(ZMQSocketBase):
    """Initiate the PUB part of a ZMQ PUB-SUB pair.

    This class contains the logic for the ZMQ message Publisher.

    Note: Security TODO

    Usage:
        * Define ...

    """

    def __init__(self, suite, context=None, barrier=None,
                 threaded=True, daemon=False):
        super().__init__(zmq.PUB, bind=True, context=context,
                         barrier=barrier, threaded=threaded, daemon=daemon)
        self.suite = suite
        self.topics = set()

    def _socket_options(self):
        """Set socket options after socket instantiation and before bind.

        Overwrites Base method.

        """
        # this limit on messages in queue is more than enough,
        # as messages correspond to scheduler loops (*messages/loop):
        self.socket.sndhwm = 1000

    def _bespoke_stop(self):
        """Bespoke stop items."""
        LOG.debug('stopping zmq publisher...')
        self.stopping = True

    async def send_multi(self, topic, data, serializer=None):
        """Send multi part message.

        Args:
            topic (bytes): The topic of the message.
            data (object): Data element/message to serialise and send.
            serializer (object, optional): string/func for encoding.

        """
        self.topics.add(topic)
        self.socket.send_multipart(
            [topic, serialize_data(data, serializer)]
        )

    def publish(self, items):
        """Publish topics.

        Args:
            items (iterable): [(topic, data, serializer)]

        """
        try:
            self.loop.run_until_complete(gather_coros(self.send_multi, items))
        except Exception as exc:
            LOG.error('publish: %s', exc)
