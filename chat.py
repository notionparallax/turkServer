# -*- coding: utf-8 -*-
"""
Chat Server.

This simple application uses WebSockets to run a primitive chat server.
"""

from flask import Flask, render_template
from flask_sockets import Sockets
import logging
from logging.handlers import RotatingFileHandler
import gevent
import os
import redis

REDIS_URL = os.environ['REDIS_URL']
REDIS_CHAN = 'chat'

app = Flask(__name__)
app.debug = 'DEBUG' in os.environ

sockets = Sockets(app)
redis = redis.from_url(REDIS_URL)


class ChatBackend(object):
    """Interface for registering and updating WebSocket clients."""

    def __init__(self):
        self.clients = list()
        self.pubsub = redis.pubsub()
        self.pubsub.subscribe(REDIS_CHAN)

    def __iter_data(self):
        for message in self.pubsub.listen():
            data = message.get('data')
            if message['type'] == 'message':
                app.logger.warning(u'Sending message: {}'.format(data))
                yield data

    def register(self, client):
        """Register a WebSocket connection for Redis updates."""
        self.clients.append(client)
        app.logger.warning('registered: ' + str(client))

    def send(self, client, data):
        """Send given data to the registered client.

        Automatically discards invalid connections.
        """
        try:
            client.send(data)
        except Exception:
            self.clients.remove(client)

    def run(self):
        """Listen for new messages in Redis, and sends them to clients."""
        for data in self.__iter_data():
            for client in self.clients:
                gevent.spawn(self.send, client, data)

    def start(self):
        """Maintain Redis subscription in the background."""
        gevent.spawn(self.run)


chats = ChatBackend()
chats.start()


@app.route('/')
def hello():
    app.logger.warning('/')
    return render_template('index.html')


@sockets.route('/submit')
def inbox(ws):
    """Receive incoming chat messages, inserts them into Redis."""
    while not ws.closed:
        # Sleep to prevent *constant* context-switches.
        gevent.sleep(0.1)
        message = ws.receive()

        if message:
            app.logger.warning(u'Inserting message: {}'.format(message))
            redis.publish(REDIS_CHAN, message)
            ws.send(str(message) + " I hear you")


@sockets.route('/receive')
def outbox(ws):
    """Send outgoing chat messages, via `ChatBackend`."""
    chats.register(ws)
    app.logger.warning(u'subscribing')

    while not ws.closed:
        # Context switch while `ChatBackend.start`
        # is running in the background.
        gevent.sleep(0.1)


handler = RotatingFileHandler('foo.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.DEBUG)
app.logger.addHandler(handler)
