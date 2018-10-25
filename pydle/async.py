## async.py
# Light wrapper around whatever async library pydle uses.
import functools
import datetime
import traceback
import asyncio
import aiosocks

FUTURE_TIMEOUT = 30


class Future(asyncio.Future):
    """
    A future. An object that represents a result that has yet to be created or returned.
    """


def coroutine(f):
    return asyncio.coroutine(f)


def parallel(*futures):
    return asyncio.gather(*futures)


class EventLoop:
    """ A light wrapper around what event loop mechanism pydle uses underneath. """

    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.future_timeout = FUTURE_TIMEOUT
        self._future_timeouts = {}
        self._tasks = []

    def __del__(self):
        self.loop.close()

    @property
    def running(self):
        return self.loop.is_running()

    def create_future(self):
        return Future(loop=self.loop)

    @asyncio.coroutine
    def connect(
        self,
        dest,
        tls=None,
        proxy_host=None,
        proxy_port=None,
        proxy_user=None,
        proxy_pass=None,
        proxy_version=5,
        **kwargs
    ):
        (host, port) = dest

        connection = None
        if proxy_host is None or proxy_port is None:
            connection = asyncio.open_connection(
                host=host, port=port, ssl=tls, **kwargs
            )
        else:
            connection = self._create_proxy_connection(
                dest, proxy_host, proxy_port, proxy_user, proxy_pass, **kwargs
            )

        return connection

    def _create_proxy_connection(
        self,
        dest,
        proxy_host,
        proxy_port,
        proxy_user,
        proxy_pass,
        proxy_version,
        **kwargs
    ):
        addr = None
        auth = None
        if proxy_version == 5:
            addr = aiosocks.Socks5Addr(proxy_host, proxy_port)
            auth = (
                aiosocks.Socks5Auth(proxy_user, proxy_pass)
                if proxy_user is not None and proxy_pass is not None
                else None
            )
        elif proxy_version == 4:
            addr = aiosocks.Socks4Addr(proxy_host, proxy_port)
            auth = aiosocks.Socks4Auth(proxy_user) if proxy_user is not None else None
        else:
            raise ValueError("Proxy version can only be 4 or 5")

        return aiosocks.create_connection(None, proxy=addr, proxy_auth=auth, dst=dest, **kwargs)

    def on_future(self, _future, _callback, *_args, **_kwargs):
        """ Add a callback for when the given future has been resolved. """
        callback = functools.partial(self._do_on_future, _callback, _args, _kwargs)

        # Create timeout handler and regular handler.
        self._future_timeouts[_future] = self.schedule_in(self.future_timeout, callback)
        future.add_done_callback(callback)

    def _do_on_future(self, callback, args, kwargs, future):
        # This was a time-out.
        if not future.done():
            future.set_exception(
                TimeoutError("Future timed out before yielding a result.")
            )
            del self._future_timeouts[future]
        # This was a time-out that already has been handled.
        elif isinstance(future.exception(), TimeoutError):
            return
        # A regular result. Cancel the timeout.
        else:
            self.unschedule(self._future_timeouts.pop(future))

        # Call callback.
        callback(*args, **kwargs)

    def schedule(self, _callback, *_args, **_kwargs):
        """
        Schedule a callback to be ran as soon as possible in this loop.
        Will return an opaque handle that can be passed to `unschedule` to unschedule the function.
        """

        @coroutine
        @functools.wraps(_callback)
        def inner():
            _callback(*_args, **_kwargs)

        return self.schedule_async(inner())

    def schedule_async(self, _callback):
        """
        Schedule a coroutine to be ran as soon as possible in this loop.
        Will return an opaque handle that can be passed to `unschedule` to unschedule the function.
        """

        @coroutine
        @functools.wraps(_callback)
        def inner():
            try:
                return (yield from _callback)
            except (GeneratorExit, asyncio.CancelledError):
                raise
            except:
                traceback.print_exc()

        task = asyncio.ensure_future(inner())
        self._tasks.append(task)
        return task

    def schedule_in(self, _when, _callback, *_args, **_kwargs):
        """
        Schedule a callback to be ran as soon as possible after `when` seconds have passed.
        Will return an opaque handle that can be passed to `unschedule` to unschedule the function.
        """
        if isinstance(_when, datetime.timedelta):
            _when = _when.total_seconds()

        @coroutine
        @functools.wraps(_callback)
        def inner():
            yield from asyncio.sleep(_when)
            _callback(*_args, **_kwargs)

        return self.schedule_async(inner())

    def schedule_async_in(self, _when, _callback):
        """
        Schedule a coroutine to be ran as soon as possible after `when` seconds have passed.
        Will return an opaque handle that can be passed to `unschedule` to unschedule the function.
        """
        if isinstance(_when, datetime.timedelta):
            _when = _when.total_seconds()

        @coroutine
        @functools.wraps(_callback)
        def inner():
            yield from asyncio.sleep(_when)
            yield from _callback

        return self.schedule_async(inner())

    def schedule_periodically(self, _interval, _callback, *_args, **_kwargs):
        """
        Schedule a callback to be ran every `interval` seconds.
        Will return an opaque handle that can be passed to unschedule() to unschedule the interval function.
        A function will also stop being scheduled if it returns False or raises an Exception.
        """
        if isinstance(_interval, datetime.timedelta):
            _interval = _interval.total_seconds()

        @coroutine
        @functools.wraps(_callback)
        def inner():
            while True:
                yield from asyncio.sleep(_when)
                ret = _callback(*_args, **_kwargs)
                if ret is False:
                    break

        return self.schedule_async(inner())

    def schedule_async_periodically(self, _interval, _callback, *_args, **_kwargs):
        """
        Schedule a coroutine to be ran every `interval` seconds.
        Will return an opaque handle that can be passed to unschedule() to unschedule the interval function.
        A function will also stop being scheduled if it returns False or raises an Exception.
        """
        if isinstance(_when, datetime.timedelta):
            _when = _when.total_seconds()

        @coroutine
        @functools.wraps(_callback)
        def inner():
            while True:
                yield from asyncio.sleep(_when)
                ret = yield from _callback(*_args, **_kwargs)
                if ret is False:
                    break

        return self.schedule_async(inner())

    def is_scheduled(self, handle):
        """ Return whether or not the given handle is still scheduled. """
        return not handle.cancelled()

    def unschedule(self, handle):
        """ Unschedule a given timeout or periodical callback. """
        if self.is_scheduled(handle):
            self.schedule(handle.cancel)

    def _unschedule_all(self):
        for task in self._tasks:
            task.cancel()

    def run(self):
        """ Run the event loop. """
        if not self.running:
            self.loop.run_forever()

    def run_with(self, func):
        """ Run loop, call function, stop loop. If function returns a future, run until the future has been resolved. """

        @coroutine
        @functools.wraps(func)
        def inner():
            yield from func
            self._unschedule_all()

        self.loop.run_until_complete(asyncio.ensure_future(inner()))

    def run_until(self, future):
        """ Run until future is resolved. """

        @coroutine
        def inner():
            yield from future
            self._unschedule_all()

        self.loop.run_until_complete(asyncio.ensure_future(inner()))

    def stop(self):
        """ Stop the event loop. """
        if self.running:
            self._unschedule_all()
            self.loop.stop()
