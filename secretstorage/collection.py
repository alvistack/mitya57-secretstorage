# SecretStorage module for Python
# Access passwords using the SecretService DBus API
# Author: Dmitry Shachnev, 2013
# License: BSD

"""Collection is a place where secret items are stored. Normally, only
the default collection should be used (usually named "login"), but this
module allows to use any registered collection.

Collections are usually automatically unlocked when user logs in, but
collections can also be locked and unlocked using
:func:`Collection.lock` and :func:`Collection.unlock` methods (unlocking
requires showing the unlocking prompt to user and can be synchronous or
asynchronous). Creating new items and editing existing ones is possible
only in unlocked collection."""

import dbus
from secretstorage.defines import SECRETS, SS_PREFIX, SS_PATH
from secretstorage.exceptions import LockedException, ItemNotFoundException
from secretstorage.item import Item
from secretstorage.util import *

COLLECTION_IFACE = SS_PREFIX + 'Collection'
SERVICE_IFACE    = SS_PREFIX + 'Service'
DEFAULT_COLLECTION = '/org/freedesktop/secrets/aliases/default'

class Collection(object):
	"""Represents a collection."""

	def __init__(self, bus, collection_path=DEFAULT_COLLECTION, session=None):
		collection_obj = bus.get_object(SECRETS, collection_path)
		self.bus = bus
		self.session = session
		self.collection_path = collection_path
		self.collection_iface = dbus.Interface(collection_obj,
			COLLECTION_IFACE)
		self.collection_props_iface = dbus.Interface(collection_obj,
			dbus.PROPERTIES_IFACE)

	def is_locked(self):
		"""Returns ``True`` if item is locked, otherwise ``False``."""
		return bool(self.collection_props_iface.Get(
			COLLECTION_IFACE, 'Locked'))

	def ensure_not_locked(self):
		"""If collection is locked, raises
		:exc:`~secretstorage.exceptions.LockedException`."""
		if self.is_locked():
			raise LockedException('Item is locked!')

	def unlock(self, callback=None):
		"""Requests unlocking the collection. If `callback` is specified,
		calls it when unlocking is complete (see
		:func:`~secretstorage.util.exec_prompt` description for
		details). Otherwise, uses asynchronous loop from GLib API."""
		service_obj = self.bus.get_object(SECRETS, SS_PATH)
		service_iface = dbus.Interface(service_obj, SERVICE_IFACE)
		prompt = service_iface.Unlock([self.collection_path], signature='ao')[1]
		if len(prompt) > 1:
			if callback:
				exec_prompt(self.bus, prompt, callback)
			else:
				exec_prompt_async_glib(self.bus, prompt)
		elif callback:
			# We still need to call it.
			callback(False, [])

	def lock(self):
		"""Locks the collection."""
		service_obj = self.bus.get_object(SECRETS, SS_PATH)
		service_iface = dbus.Interface(service_obj, SERVICE_IFACE)
		service_iface.Lock([self.collection_path])

	def delete(self):
		"""Deletes the collection and all items inside it."""
		self.ensure_not_locked()
		return self.collection_iface.Delete()

	def get_all_items(self):
		"""Returns a generator of all items in the collection."""
		for item_path in self.collection_props_iface.Get(
		COLLECTION_IFACE, 'Items'):
			yield Item(self.bus, item_path, self.session)

	def search_items(self, attributes):
		"""Returns a generator of items with the given attributes.
		`attributes` should be a dictionary."""
		locked, unlocked = self.collection_iface.SearchItems(attributes)
		for item_path in locked + unlocked:
			yield Item(self.bus, item_path, self.session)

	def get_label(self):
		"""Returns the collection label."""
		label = self.collection_props_iface.Get(COLLECTION_IFACE, 'Label')
		return to_unicode(label)

	def set_label(self, label):
		"""Sets collection label to `label`."""
		self.ensure_not_locked()
		self.collection_props_iface.Set(COLLECTION_IFACE, 'Label', label)

	def create_item(self, label, attributes, secret, replace=False):
		"""Creates a new :class:`~secretstorage.item.Item` with given
		`label` (unicode string), `attributes` (dictionary) and `secret`
		(bytestring). If `replace` is ``True``, replaces the existing
		item with the same attributes. Returns the created item."""
		self.ensure_not_locked()
		if not self.session:
			self.session = open_session(self.bus)
		secret = format_secret(secret, self.session)
		properties = {
			SS_PREFIX+'Item.Label': label,
			SS_PREFIX+'Item.Attributes': attributes
		}
		new_item, prompt = self.collection_iface.CreateItem(properties,
			secret, replace)
		return Item(self.bus, new_item, self.session)

def create_collection(bus, label, alias='', session=None):
	"""Creates a new :class:`Collection` with the given `label` and `alias`
	and returns it. This action requires prompting. If prompt is dismissed,
	raises :exc:`~secretstorage.exceptions.ItemNotFoundException`. This is
	asynchronous function, uses loop from GLib API."""
	if not session:
		session = open_session(bus)
	properties = {SS_PREFIX+'Collection.Label': label}
	service_obj = bus.get_object(SECRETS, SS_PATH)
	service_iface = dbus.Interface(service_obj, SERVICE_IFACE)
	collection_path, prompt = service_iface.CreateCollection(properties,
		alias)
	if len(collection_path) > 1:
		return Collection(bus, collection_path, session=session)
	dismissed, unlocked = exec_prompt_async_glib(bus, prompt)
	if dismissed:
		raise ItemNotFoundException('Prompt dismissed.')
	return Collection(bus, unlocked, session=session)
