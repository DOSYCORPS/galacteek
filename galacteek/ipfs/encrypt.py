from io import BytesIO

from galacteek.ipfs.wrappers import ipfsOp
from galacteek.core.asynclib import asyncReadFile
from galacteek import log

import aioipfs


class IpfsRSAAgent:
    """
    IPFS RSA Agent

    :param rsaExecutor: RSA Executor object
    :param pubKeyPem: PEM-encoded public key
    :param privKeyPath: Path to private RSA key
    """

    def __init__(self, rsaExecutor, pubKeyPem, privKeyPath):
        self.rsaExec = rsaExecutor
        self.pubKeyPem = pubKeyPem
        self.privKeyPath = privKeyPath

    def debug(self, msg):
        log.debug('RSA Agent: {0}'.format(msg))

    async def encrypt(self, data, pubKey):
        return await self.rsaExec.encryptData(BytesIO(data), pubKey)

    async def decrypt(self, data):
        return await self.rsaExec.decryptData(BytesIO(data),
                                              await self.__rsaReadPrivateKey())

    @ipfsOp
    async def storeSelf(self, op, data):
        """
        Encrypt some data with our pubkey and store it in IPFS
        Returns the CID of the encrypted file
        """
        try:
            encrypted = await self.encrypt(data, self.pubKeyPem)
            if encrypted is None:
                return
            entry = await op.client.add_bytes(encrypted)
            if entry:
                self.debug(
                    'self-encrypt: encoded {0} bytes to {1}'.format(
                        len(data), entry['Hash'])
                )
                return entry['Hash']
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))

    @ipfsOp
    async def encryptToMfs(self, op, data, mfsPath):
        try:
            encrypted = await self.encrypt(data, self.pubKeyPem)
            if not encrypted:
                return False
            return await op.filesWrite(mfsPath, encrypted,
                                       create=True, truncate=True)
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))

    @ipfsOp
    async def decryptIpfsObject(self, op, data):
        privKey = await self.__rsaReadPrivateKey()
        try:
            decrypted = await self.rsaExec.decryptData(BytesIO(data), privKey)
            if decrypted:
                self.debug('RSA: decrypted {0} bytes'.format(
                    len(decrypted)))
                return decrypted
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))
        except Exception as e:
            self.debug('RSA: unknown error while decrypting {}'.format(str(e)))

    @ipfsOp
    async def decryptMfsFile(self, op, path):
        try:
            data = await op.client.files.read(path)
            if data is None:
                raise ValueError('Invalid file')
        except aioipfs.APIError as err:
            self.debug('IPFS error {}'.format(err.message))
        else:
            return await self.decryptIpfsObject(data)

    async def __rsaReadPrivateKey(self):
        return await asyncReadFile(self.privKeyPath)