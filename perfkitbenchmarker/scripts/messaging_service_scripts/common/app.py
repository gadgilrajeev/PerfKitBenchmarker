"""Defines the App class."""
from typing import Type

from absl import flags

from perfkitbenchmarker.scripts.messaging_service_scripts.common import client

_BENCHMARK_SCENARIO = flags.DEFINE_enum(
    'benchmark_scenario',
    'publish_latency', ['publish_latency', 'pull_latency'],
    help='Which part of the benchmark to run.')
_NUMBER_OF_MESSAGES = flags.DEFINE_integer(
    'number_of_messages', 100, help='Number of messages to send on benchmark.')
_MESSAGE_SIZE = flags.DEFINE_integer(
    'message_size',
    10,
    help='Number of characters to have in a message. '
    "Ex: 1: 'A', 2: 'AA', ...")


class App:
  """Benchmarking Application.

  This is a singleton that allows to create a runner instance honoring the flags
  and the client class provided.
  """
  instance = None

  @classmethod
  def get_instance(cls) -> 'App':
    """Gets the App instance.

    On the first call, it creates the instance. For subsequent calls, it just
    returns that instance.

    Returns:
      The App instance.
    """
    if cls.instance is None:
      cls.instance = cls()
    return cls.instance

  @classmethod
  def for_client(cls,
                 client_cls: Type[client.BaseMessagingServiceClient]) -> 'App':
    """Gets the app instance and configures it to use the passed client class.

    Args:
      client_cls: A BaseMessagingServiceClient class.

    Returns:
      The App instance.
    """
    instance = cls.get_instance()
    instance.register_client(client_cls)
    return instance

  def __init__(self):
    """Private constructor. Outside this class, use get_instance instead."""
    self.client_cls = None
    self.runner_registry = {}

  def __call__(self, _) -> None:
    """Runs the benchmark for the flags passed to the script.

    Implementing this magic method allows you to pass this instance directly to
    absl.app.run.

    Args:
      _: Unused. Just for compatibility with absl.app.run.
    """
    client_class = self.get_client_class()
    msgsvc_client = client_class.from_flags()
    try:
      msgsvc_client.run_phase(_BENCHMARK_SCENARIO.value,
                              _NUMBER_OF_MESSAGES.value, _MESSAGE_SIZE.value)
    finally:
      msgsvc_client.close()

  def get_client(self) -> client.BaseMessagingServiceClient:
    """Creates a client instance, using the client class registered.

    Returns:
      A BaseMessagingServiceClient instance.

    Raises:
      Exception: No client class has been registered.
    """
    client_class = self.get_client_class()
    return client_class.from_flags()

  def get_client_class(self) -> Type[client.BaseMessagingServiceClient]:
    """Gets the client class registered.

    Returns:
      A BaseMessagingServiceClient class.

    Raises:
      Exception: No client class has been registered.
    """
    if self.client_cls is None:
      raise Exception('No client class has been registered.')
    return self.client_cls

  def register_client(
      self, client_cls: Type[client.BaseMessagingServiceClient]) -> None:
    """Registers a client class to create instances with.

    Args:
      client_cls: The client class to register.
    """
    self.client_cls = client_cls
