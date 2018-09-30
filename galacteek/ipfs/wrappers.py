
import functools

from PyQt5.QtWidgets import QApplication

from galacteek import log
from galacteek.ipfs.ipfsops import *

def _getOp():
    return IPFSOpRegistry.getDefault()

def appTask(fn, *args, **kw):
    app = QApplication.instance()
    app.task(fn, *args, **kw)

def ipfsFunc(func):
    @functools.wraps(func)
    async def wrapper(*args, **kw):
        app = QApplication.instance()
        if not app:
            raise Exception('No Application')
        return await func(app.ipfsClient, *args, **kw)
    return wrapper

def ipfsOpFn(func):
    @functools.wraps(func)
    async def wrapper(*args, **kw):
        op = IPFSOpRegistry.getDefault()
        if op:
            return await func(op, *args, **kw)
        log.debug('ipfsopfn: op is null')
    return wrapper

class ipfsClassW:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.name = wrapped.__name__

class ipfsOp(ipfsClassW):
    """
    Wraps an async class method, calling it with an IPFSOperator
    """
    def __get__(self, inst, owner):
        async def wrapper(*args, **kw):
            op = IPFSOpRegistry.getDefault()
            if op:
                return await self.wrapped(inst, op, *args, **kw)
        return wrapper

class ipfsStatOp(ipfsClassW):
    def __get__(self, inst, owner):
        async def wrapper(*args, **kw):
            op = IPFSOpRegistry.getDefault()
            path = args[0]

            stat = op.objStatCtxGet(path)
            if not stat:
                stat = await op.objStatCtxUpdate(path)

            args = args + (stat,)

            return await self.wrapped(inst, op, *args, **kw)
        return wrapper
