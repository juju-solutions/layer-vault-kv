import json
from hashlib import md5

from charmhelpers.core import hookenv
from charmhelpers.core import unitdata
from charmhelpers.contrib.openstack.vaultlocker import retrieve_secret_id
from charms.reactive import data_changed
from charms.reactive import endpoint_from_flag
from charms.reactive import set_flag, clear_flag

import hvac


class VaultNotReady(Exception):
    """
    Exception indicating that Vault was accessed before it was ready.
    """
    pass


class _Singleton(type):
    # metaclass to make a class a singleton
    def __call__(cls, *args, **kwargs):
        if not isinstance(getattr(cls, '_singleton_instance', None), cls):
            cls._singleton_instance = super().__call__(*args, **kwargs)
        return cls._singleton_instance


class _VaultBaseKV(dict, metaclass=_Singleton):
    _client = None  # shared client
    _path = None  # set by subclasses

    def __init__(self):
        if not self._client:
            _VaultBaseKV._client = hvac.Client(url=self._config['vault_url'])
            _VaultBaseKV._client.auth_approle(self._config['role_id'],
                                              self._config['secret_id'])
        response = self._client.read(self._path)
        super().__init__(response['data'] if response else {})

    @property
    def _config(self):
        _VaultBaseKV._config = get_vault_config()
        return _VaultBaseKV._config

    def __setitem__(self, key, value):
        self._client.write(self._path, **{key: value})
        super().__setitem__(key, value)

    def set(self, key, value):
        # alias in case a KV-like interface is preferred
        self[key] = value


class VaultUnitKV(_VaultBaseKV):
    """
    A simplified interface for storing data in Vault, with the data scoped to
    the current unit.

    Keys must be strings, but data can be structured as long as it is
    JSON-serializable.

    This class can be used as a dict, or you can use `self.get` and `self.set`
    for a more KV-like interface. When values are set, via either style, they
    are immediately persisted to Vault. Values are also cached in memory.

    Note: This class is a singleton.
    """
    def __init__(self):
        unit_num = hookenv.local_unit().split('/')[1]
        self._path = '{}/kv/unit/{}'.format(self._config['secret_backend'],
                                            unit_num)
        super().__init__()


class VaultAppKV(_VaultBaseKV):
    """
    A simplified interface for storing data in Vault, with data shared by every
    unit of the application.

    Keys must be strings, but data can be structured as long as it is
    JSON-serializable.

    This class can be used as a dict, or you can use `self.get` and `self.set`
    for a more KV-like interface. When values are set, via either style, they
    are immediately persisted to Vault. Values are also cached in memory.

    Note: This is intended to be used as a secure replacement for leadership
    data.  Therefore, only the leader should set data here.  This is not
    enforced, but data changed by non-leaders will not trigger hooks on other
    units, so they may not be notified of changes in a timely fashion.

    Note: This class is a singleton.
    """
    def __init__(self):
        self._path = '{}/kv/app'.format(self._config['secret_backend'])
        self._hash_path = '{}/kv/app-hashes/{}'.format(
            self._config['secret_backend'],
            hookenv.local_unit().split('/')[1])
        super().__init__()
        self._load_hashes()

    def _load_hashes(self):
        response = self._client.read(self._hash_path)
        self._old_hashes = response['data'] if response else {}
        self._new_hashes = {}
        for key in self.keys():
            self._rehash(key)

    def _rehash(self, key):
        serialized = json.dumps(self[key], sort_keys=True).encode('utf8')
        self._new_hashes[key] = md5(serialized).hexdigest()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._rehash(key)
        self._manage_flags(key)

    def _manage_flags(self, key):
        flag_any_changed = 'layer.vault-kv.app-kv.changed'
        flag_key_changed = 'layer.vault-kv.app-kv.changed.{}'.format(key)
        flag_key_set = 'layer.vault-kv.app-kv.set.{}'.format(key)
        if self.is_changed(key):
            # clear then set flag to ensure triggers are run even if the main
            # flag was never cleared
            clear_flag(flag_any_changed)
            set_flag(flag_any_changed)
            clear_flag(flag_key_changed)
            set_flag(flag_key_changed)
        if self.get(key) is not None:
            set_flag(flag_key_set)
        else:
            clear_flag(flag_key_set)

    def is_changed(self, key):
        """
        Determine if the value for the given key has changed.

        In order to detect changes, hashes of the values are also stored
        in Vault.  These hashes are updated automatically at exit via
        `self.update_hashes()`.
        """
        return self._new_hashes.get(key) == self._old_hashes.get(key)

    def any_changed(self):
        """
        Determine if any data has changed.

        In order to detect changes, hashes of the values are also stored
        in Vault.  These hashes are updated automatically at exit via
        `self.update_hashes()`.
        """
        all_keys = self._new_hashes.keys() | self._old_hashes.keys()
        return any(self.is_changed(key) for key in all_keys)

    def update_hashes(self):
        """
        Update the hashes in Vault, thus marking all fields as unchanged.

        This is done automatically at exit.
        """
        self._client.write(self._hash_path, **self._new_hashes)
        self._old_hashes.clear()
        self._old_hashes.update(self._new_hashes)


def get_vault_config():
    """
    Get the config data needed for this application to access Vault.

    This is only needed if you're using another application, such as
    VaultLocker, using the secrets backend provided by this layer.

    Returns a dictionary containing the following keys:

      * vault_url
      * secret_backend
      * role_id
      * secret_id

    Note: This data is cached in [UnitData][] so anything with access to that
    could access Vault as this application.

    If any of this data changes (such as the secret_id being rotated), this
    layer will set the `layer.vault-kv.config.changed` flag.

    If this is called before the Vault relation is available, it will raise
    `VaultNotReady`.

    [UnitData]: https://charm-helpers.readthedocs.io/en/latest/api/charmhelpers.core.unitdata.html
    """  # noqa
    vault = endpoint_from_flag('vault-kv.available')
    if not vault:
        raise VaultNotReady()
    return {
        'vault_url': vault.vault_url,
        'secret_backend': _get_secret_backend(),
        'role_id': vault.unit_role_id,
        'secret_id': _get_secret_id(vault),
    }


def _get_secret_backend():
    app_name = hookenv.application_name()
    return 'charm-{}'.format(app_name)


def _get_secret_id(vault):
    token = vault.unit_token
    if data_changed('layer.vault-kv.token', token):
        # token is one-shot, but if it changes it might mean that we're
        # being told to rotate the secret ID, or we might not have fetched
        # one yet
        vault_url = vault.vault_url
        secret_id = retrieve_secret_id(vault_url, token)
        unitdata.kv().set('layer.vault-kv.secret_id', secret_id)
        # have to flush immediately because if we don't and hit some error
        # elsewhere, it could get us into a state where we have forgotten the
        # secret ID and can't retrieve it again because we've already used the
        # token
        unitdata.kv().flush()
    else:
        secret_id = unitdata.kv().get('layer.vault-kv.secret_id')
    return secret_id
