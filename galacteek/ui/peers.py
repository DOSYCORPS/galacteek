import os.path
import asyncio

from PyQt5.QtWidgets import QMenu, QHeaderView, QPushButton, QComboBox
from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtCore import QObject, QCoreApplication

from galacteek import ensure, log
from galacteek.ipfs.wrappers import ipfsOp
from galacteek.ipfs.cidhelpers import *
from galacteek.ipfs.ipfsops import *

from . import ui_peersmgr
from .widgets import *
from .modelhelpers import *
from .helpers import *
from .dialogs import *


def iUsername():
    return QCoreApplication.translate('PeersManager', 'Username')


def iPeerId():
    return QCoreApplication.translate('PeersManager', 'Peer ID')


def iPingAvg():
    return QCoreApplication.translate('PeersManager', 'Ping Average (ms)')


def iLocation():
    return QCoreApplication.translate('PeersManager', 'Location')


def iInvalidDagCID(dagCid):
    return QCoreApplication.translate('PeersManager',
                                      'Invalid DAG CID: {0}').format(dagCid)


class PeersModel(QStandardItemModel):
    pass


class PeersTracker(QObject):
    def __init__(self, ctx):
        super().__init__()
        self.model = PeersModel()
        self.model.setHorizontalHeaderLabels([
            iUsername(),
            iPeerId(),
            iPingAvg(),
            iLocation(),
            ''
        ])
        self.ctx = ctx
        self.ctx.peers.changed.connect(self.onPeersChange)
        self.ctx.peers.peerAdded.connect(self.onPeerAdded)
        self.ctx.peers.peerModified.connect(self.onPeerModified)
        self.ctx.peers.peerLogout.connect(self.onPeerLogout)
        self._peersRows = {}

    @property
    def modelRoot(self):
        return self.model.invisibleRootItem()

    @property
    def peersRows(self):
        return self._peersRows

    def onPeerLogout(self, peerId):
        modelSearch(self.model,
                    parent=self.modelRoot.index(),
                    search=peerId, delete=True)
        if peerId in self._peersRows:
            del self._peersRows[peerId]

    def onPeerModified(self, peerId):
        peerCtx = self.ctx.peers.getByPeerId(peerId)
        if not peerCtx:
            return

        row = self._peersRows.get(peerId, None)
        if row:
            row[0].setText(peerCtx.ident.username)
            row[1].setText(peerId)
            row[3].setText(peerCtx.ident.location)

    def onPeerAdded(self, peerId):
        peerCtx = self.ctx.peers.getByPeerId(peerId)
        if not peerCtx:
            return

        self.addPeerFromEntry(peerId, peerCtx)

    def addPeerFromEntry(self, peerId, peerCtx):
        row = [
            UneditableItem(peerCtx.ident.username),
            UneditableItem(peerId),
            UneditableItem(str(peerCtx.pingavg)),
            UneditableItem(peerCtx.ident.location),
            UneditableItem(''),
        ]
        rowStatus = [
            UneditableItem('Joined: {0}'.format(peerCtx.ident.dateCreated)),
            UneditableItem(peerId),
        ]

        self.modelRoot.appendRow(row)
        row[0].appendRow(rowStatus)
        self._peersRows[peerId] = row

    def onPeersChange(self):
        pass


class PeersManager(GalacteekTab):
    def __init__(self, gWindow, peersTracker, **kw):
        super().__init__(gWindow, **kw)

        self.lock = asyncio.Lock()
        self.peersTracker = peersTracker
        self.ui = ui_peersmgr.Ui_PeersManager()
        self.ui.setupUi(self)

        self.ui.tree.setModel(self.peersTracker.model)
        self.ui.tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.ui.tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.ui.tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)

        self.ui.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.tree.customContextMenuRequested.connect(self.onContextMenu)
        self.ui.tree.doubleClicked.connect(self.onDoubleClick)

        self.ui.search.returnPressed.connect(self.onSearch)

        self.app.ipfsCtx.peers.changed.connect(self.onPeersChange)
        self.app.ipfsCtx.peers.peerAdded.connect(self.onPeerAdded)
        ensure(self.refreshControls())

    @property
    def model(self):
        return self.peersTracker.model

    def onSearch(self):
        search = self.ui.search.text()
        if len(search) > 0:
            self.ui.tree.keyboardSearch(search)

    def onPeersChange(self):
        self.ui.peersCountLabel.setText(str(self.app.ipfsCtx.peers.peersCount))

    def onPeerAdded(self, peerId):
        ensure(self.refreshControls())

    async def refreshControls(self):
        def openPeerHome(idx, id):
            log.debug('openPeerHome: {0} {1}'.format(idx, id))
            method = 'ipns' if idx == 1 else 'direct'
            peerCtx = self.peersTracker.ctx.peers.getByPeerId(id)
            ensure(self.explorePeerHome(peerCtx, method=method))

        def followPeer(id):
            peerCtx = self.peersTracker.ctx.peers.getByPeerId(id)

            runDialog(AddFeedDialog, self.app.marksLocal,
                      joinIpns(peerCtx.ident.dagIpns),
                      feedName=peerCtx.ident.username)

        with await self.lock:
            for peerId, row in self.peersTracker.peersRows.items():
                idx = self.model.indexFromItem(row[4])
                if self.ui.tree.indexWidget(idx) is not None:
                    continue

                btnHomeCombo = QComboBox()
                btnHomeCombo.addItem('Browse homepage (direct)')
                btnHomeCombo.addItem('Browse homepage (IPNS)')
                btnHomeCombo.activated.connect(
                    lambda idx: openPeerHome(idx, peerId))

                self.ui.tree.setIndexWidget(idx, btnHomeCombo)

    def onContextMenu(self, point):
        idx = self.tree.indexAt(point)
        if not idx.isValid():
            return

        menu = QMenu()
        menu.exec(self.tree.mapToGlobal(point))

    def onDoubleClick(self, idx):
        idxPeerId = self.model.sibling(idx.row(), 1, idx)
        peerId = self.model.data(idxPeerId)
        peerCtx = self.peersTracker.ctx.peers.getByPeerId(peerId)

        ensure(self.explorePeerHome(peerCtx))

    @ipfsOp
    async def explorePeerHome(self, op, peerCtx, method='direct'):
        identMsg = peerCtx.ident

        dagCid = identMsg.dagCid
        if not cidValid(dagCid):
            log.debug('invalid DAG CID: {}'.format(dagCid))
            return messageBox(iInvalidDagCID(dagCid))

        if method == 'ipns':
            self.gWindow.addBrowserTab().browseFsPath(
                os.path.join(joinIpns(identMsg.dagIpns), 'index.html'))
        elif method == 'direct':
            self.gWindow.addBrowserTab().browseFsPath(
                os.path.join(joinIpfs(identMsg.dagCid), 'index.html'))