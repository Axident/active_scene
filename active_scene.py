
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
    
from customLoader import loadUi
import os
import time
import sys
import ctypes
import numpy
rng = numpy.random.default_rng()

here = os.path.dirname(__file__)


def random_color():
    return rng.random((1, 3))[0]*245

def nudge_color(color):
    nudged = rng.normal(color, 2)
    while nudged.sum() > 600:
        nudged = nudged - 1
    while nudged.sum() < 150:
        nudged = nudged + 1
    return numpy.clip(nudged, 0, 255)


class SceneUpdateWorker(QThread):
    status = Signal(object, object)
    finished = Signal(object)

    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        self.parent = parent
        self.start_item = None
        self.my_cells = set()

    def update_neighbors(self, source, depth=0):
        if depth >= 500:
            return source
        depth += 1
        time.sleep(.02)
        self.my_cells.add(source)
        neighbors = [n for n in source.neighbors if n.updated < 1]
        if not neighbors:
            neighbors = self.spread()
        if neighbors:
            item = rng.choice(neighbors)
            if item not in self.my_cells:
                item.color = item.bleed(force=True)
            item.color = nudge_color(item.color)
            self.status.emit(item, self)
            self.my_cells.add(item)
            source = self.update_neighbors(item, depth=depth)
        return source

    def edges(self):
        return [n for n in self.my_cells.copy() if len(n.get_surrounding_color()) != len(n.neighbors)]

    def spread(self):
        neighbors = self.edges()
        rng.shuffle(neighbors)
        expanded = []
        for n in neighbors[:int(len(neighbors)/10)]:
            fringes = n.neighbors
            bleeder = rng.choice(fringes)
            #bleeder.bleed(force=True)
            bleeder.color = nudge_color(n.color)
            self.my_cells.add(bleeder)
            self.status.emit(bleeder, self)
            expanded.append(bleeder)
        return expanded

    def run(self):
        neighbors = True
        if self.start_item:
            item = self.start_item
        else:
            row = rng.choice(list(range(len(self.parent.data))))
            items = self.parent.data[row]
            item = rng.choice(items)
            if not item.color.sum():
                item.color = random_color()
            self.my_cells.add(item)
            self.status.emit(item, self)
        while neighbors:
            item = self.update_neighbors(item)
            self.status.emit(item, self)
            #copied = list(self.my_cells.copy())
            #rng.shuffle(copied)
            neighbors = self.edges()
            if neighbors:
                item = rng.choice(neighbors)
                item.color = item.average_color(item.get_surrounding_color())
                self.status.emit(item, self)
        self.finished.emit(self)

    def stop(self):
        self.terminate()

class Cell(QGraphicsRectItem):
    def __init__(self, location, parent=None):
        super(Cell, self).__init__(None)
        self.parent = parent
        self.location = location
        self.setRect(QRect(0, 0, 2, 2))
        self.setX(self.location[0] * 2 + 2)
        self.setY(self.location[1] * 2 + 2)
        self.chance = 3
        self.color = numpy.array([0.0, 0.0, 0.0])
        self.neighbors = []
        self.updated = 0

    def discover_neighbors(self):
        maxlen = len(self.parent.data)-1
        self.neighbors = []
        if self.location[0] > 0:
            west = self.parent.data[self.location[1]][self.location[0]-1]
            self.neighbors.append(west)
            if self.location[1] > 0:
                north_west = self.parent.data[self.location[1]-1][self.location[0]-1]
                self.neighbors.append(north_west)
            if self.location[1] < maxlen:
                south_west = self.parent.data[self.location[1]+1][self.location[0]-1]
                self.neighbors.append(south_west)
        if self.location[0] < maxlen:
            east = self.parent.data[self.location[1]][self.location[0]+1]
            self.neighbors.append(east)
            if self.location[1] > 0:
                north_east = self.parent.data[self.location[1]-1][self.location[0]+1]
                self.neighbors.append(north_east)
            if self.location[1] < maxlen:
                south_east = self.parent.data[self.location[1]+1][self.location[0]+1]
                self.neighbors.append(south_east)
        if self.location[1] > 0:
            north = self.parent.data[self.location[1]-1][self.location[0]]
            self.neighbors.append(north)
        if self.location[1] < maxlen:
            south = self.parent.data[self.location[1]+1][self.location[0]]
            self.neighbors.append(south)

    def get_surrounding_color(self):
        return [n.color for n in self.neighbors if n.color.sum()]

    def average_color(self, colors):
        if not len(colors):
            return numpy.array([0.0, 0.0, 0.0])
        return numpy.add.reduce(colors)/len(colors)

    def bleed(self, force=False):
        if not self.color.sum() or force:
            surrounding = self.get_surrounding_color()
            self.color = self.average_color(surrounding)
        return self.color

    def boundingRect(self):
        return QRect(0, 0, 2, 2)

    def paint(self, painter, option=None, widget=None):
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*self.color.tolist()))
        painter.drawRect(0, 0, 2, 2)
        painter.restore()
        
class MyMainWindow(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        
        loadUi(r"%s\active_scene.ui" % here, self)
        self.setWindowIcon(QIcon(r"%s\app_icon.png" % here))
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('active_scene')

        self.active_scene = QGraphicsScene(self)
        self.graphix_view.setScene(self.active_scene)
        self.scene_updaters = []
        self.items_to_update = set()
        self.data = []

    def closeEvent(self, event):
        for updater in self.scene_updaters:
            if updater.isRunning():
                updater.stop()

    def generate(self):
        self.data = []
        for r in list(range(300)):
            row = []
            for c in list(range(300)):
                cell = Cell([c, r], parent=self)
                row.append(cell)
            self.data.append(row)

        for row in list(range(len(self.data))):
            items = self.data[row]
            for c in list(range(len(items))):
                item = items[c]
                item.discover_neighbors()
                self.active_scene.addItem(item)
        self.active_scene.setSceneRect(0, 0, (10 + 2*len(self.data)), (10 + 2*len(self.data)))
        self.graphix_view.setSceneRect(self.active_scene.sceneRect())
        self.graphix_view.fitInView(self.active_scene.sceneRect(), Qt.KeepAspectRatio)
        QCoreApplication.processEvents()

        for i in list(range(3)):
            scene_updater = SceneUpdateWorker(parent=self)
            self.scene_updaters.append(scene_updater)
            scene_updater.status.connect(self.update_activity)
            scene_updater.finished.connect(self.finish_activity)
            scene_updater.start()
        print('active threads: %d' % len(self.scene_updaters))

        #self.timer = QTimer(self)
        #self.timer.timeout.connect(self.do_updates)
        #self.timer.start(1000)

    def do_updates(self):
        self.active_scene.update()
        self.timer.setInterval(350*len(self.scene_updaters))

    def update_activity(self, item, thread):
        item.update()
        item.updated = item.updated + 1
        if len(self.scene_updaters) < 5:
            chance = rng.integers(5000, size=1)[0]
            if chance < 2:
                possible = []
                for row in list(range(len(self.data))):
                    items = self.data[row]
                    for item in items:
                        if not item.color.sum():
                            possible.append(item)
                if len(possible):
                    new_thread = SceneUpdateWorker(parent=self)
                    new_thread.my_cells = thread.my_cells
                    new_thread.start_item = rng.choice(possible)
                    self.scene_updaters.append(new_thread)
                    new_thread.status.connect(self.update_activity)
                    new_thread.finished.connect(self.finish_activity)
                    new_thread.start()
                    print('active threads: %d' % len(self.scene_updaters))

    def finish_activity(self, thread):
        self.scene_updaters.remove(thread)
        print('active threads: %d' % len(self.scene_updaters))
        if len(self.scene_updaters) < 1:
            for row in list(range(len(self.data))):
                items = self.data[row]
                for c in list(range(len(items))):
                    items[c].bleed()
                    items[c].update()

def launch_it():
    app = QApplication([])
    window = MyMainWindow()
    window.show()
    window.generate()
    sys.exit(app.exec_())
    
if __name__ == "__main__":
    launch_it()
