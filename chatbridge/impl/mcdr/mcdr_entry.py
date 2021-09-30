import os
from threading import Event, Lock
from typing import Optional

from mcdreforged.api.all import *

from chatbridge.common import logger
from chatbridge.impl.mcdr.client import ChatBridgeMCDRClient
from chatbridge.impl.mcdr.config import MCDRClientConfig


META = ServerInterface.get_instance().as_plugin_server_interface().get_self_metadata()
Prefixes = ('!!ChatBridge', '!!cb')
client: Optional[ChatBridgeMCDRClient] = None
config: Optional[MCDRClientConfig] = None
cb_stop_done = Event()
cb_lock = Lock()


def tr(key: str, *args, **kwargs) -> RTextBase:
	return ServerInterface.get_instance().rtr(META.id + '.' + key, *args, **kwargs)


def display_help(source: CommandSource):
	source.reply(tr('help_message', version=META.version, prefix=Prefixes[0], prefixes=', '.join(Prefixes)))


def display_status(source: CommandSource):
	if config is None or client is None:
		source.reply(tr('status.not_init'))
	else:
		source.reply(tr('status.not_init', client.is_online()))


@new_thread('ChatBridge-restart')
def restart_client(source: CommandSource):
	with cb_lock:
		client.restart()
	source.reply(tr('restarted'))


@new_thread('ChatBridge-unload')
def on_unload(server: PluginServerInterface):
	with cb_lock:
		if client is not None and client.is_online():
			client.stop()
	cb_stop_done.set()


@new_thread('ChatBridge-messenger')
def send_chat(message: str, *, author: str = ''):
	with cb_lock:
		if client is not None:
			if not client.is_online():
				client.start()
			client.send_chat(message, author)


def on_load(server: PluginServerInterface, old_module):
	global client, config
	if not os.path.isfile(os.path.join('config', server.get_self_metadata().id, 'config.json')):
		server.logger.exception('Config file not found! ChatBridge will not work properly')
		server.logger.error('Fill the default configure file with correct values and reload the plugin')
		server.save_config_simple(MCDRClientConfig.get_default())
		return

	try:
		config = server.load_config_simple(target_class=MCDRClientConfig)
	except:
		server.logger.exception('Failed to read the config file! ChatBridge might not work properly')
		server.logger.error('Fix the configure file and then reload the plugin')
	if config.debug:
		logger.DEBUG_SWITCH = True
	client = ChatBridgeMCDRClient(config, server)
	for prefix in Prefixes:
		server.register_help_message(prefix, tr('help_summary'))
	server.register_command(
		Literal(Prefixes).
		runs(display_help).
		then(Literal('status').runs(display_status)).
		then(Literal('restart').runs(restart_client))
	)

	@new_thread('ChatBridge-start')
	def start():
		with cb_lock:
			if isinstance(getattr(old_module, 'cb_stop_done', None), type(cb_stop_done)):
				stop_event: Event = old_module.cb_stop_done
				if not stop_event.wait(30):
					server.logger.warning('Previous chatbridge instance does not stop for 30s')
			client.start()

	start()


def on_user_info(server: PluginServerInterface, info: Info):
	if info.is_from_server:
		send_chat(info.content, author=info.player)


def on_player_joined(server: PluginServerInterface, player_name: str, info: Info):
	send_chat('{} joined {}'.format(player_name, config.name))


def on_player_left(server: PluginServerInterface, player_name: str):
	send_chat('{} left {}'.format(player_name, config.name))


def on_server_startup(server: PluginServerInterface):
	send_chat('Server has started up')


def on_server_stop(server: PluginServerInterface, return_code: int):
	send_chat('Server stopped')


@event_listener('more_apis.death_message')
def on_player_death(server: PluginServerInterface, message: str):
	send_chat(message)
