
# -*- coding: utf-8 -*-

import os

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .mongodb_data_loader_dialog import MongodbDataLoaderDialog


class MongodbDataLoader:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = self.tr('&MongoDB Data Loader')
        self.first_start = True
        self.dlg = None

        locale = QSettings().value('locale/userLocale', 'en')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'MongodbDataLoader_{}.qm'.format(locale)
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

    def tr(self, message):
        return QCoreApplication.translate('MongodbDataLoader', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        parent=None
    ):
        action = QAction(QIcon(icon_path), text, parent)
        action.triggered.connect(callback)

        self.iface.addPluginToMenu(self.menu, action)
        self.iface.addToolBarIcon(action)

        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')

        self.add_action(
            icon_path,
            self.tr('MongoDB Data Loader'),
            self.run,
            self.iface.mainWindow()
        )

    def unload(self):
        if self.dlg:
            self.dlg.close()
            self.dlg.deleteLater()
            self.dlg=None
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        if self.dlg is None:
            self.dlg = MongodbDataLoaderDialog(self.iface)

        self.dlg.show()
        self.dlg.exec_()
