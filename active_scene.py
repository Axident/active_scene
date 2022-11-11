
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
    total = nudged.sum()
    if total > 600:
        nudged = nudged - (total-600)
    elif total < 150:
        nudged = nudged + (150-total)
    return numpy.clip(nudged, 0, 255)


class SceneUpdateWorker(QThread):
    status = Signal(object, object)
    finished = Signal(object)

    def __init__(self, parent=None):
        QThread.__init__(self, parent)
        self.parent = parent
        self.start_item = None
        self.my_cells = set()
        self.my_edges = []

    def update_neighbors(self, source, depth=0):
        if depth >= 300:
            return source
        depth += 1
        time.sleep(.02)
        self.my_cells.add(source)
        neighbors = [n for n in source.neighbors if n.updated < 1]
        if not neighbors:
            neighbors = self.spread()
        while neighbors:
            time.sleep(.03)
            depth += 1
            source = rng.choice(neighbors)
            if source not in self.my_cells:
                source.set_color(source.bleed(force=True))
            source.set_color(nudge_color(source.color))
            self.status.emit(source, self)
            self.my_cells.add(source)
            if depth % 30 == 0:
                self.spread()
            neighbors = [n for n in source.neighbors if n.updated < 1]
            if not neighbors:
                neighbors = self.spread()
        return source

    def edges(self):
        return [c for c in self.my_cells.copy() if c.is_edge()]

    def spread(self):
        neighbors = self.edges()
        self.my_cells = set(neighbors)
        rng.shuffle(neighbors)
        expanded = []
        for n in neighbors[:min(int(len(neighbors)/10), 100)]:
            fringes = [f for f in n.neighbors if f.updated < 1]
            if not fringes:
                continue
            bleeder = rng.choice(fringes)
            stranger = [f for f in bleeder.neighbors if f.updated and f not in self.my_cells]
            if stranger:
                bleeder.set_color(bleeder.average_color(bleeder.get_surrounding_color()))
            else:
                bleeder.set_color(nudge_color(n.color))
            self.my_cells.add(bleeder)
            self.status.emit(bleeder, self)
            expanded.append(bleeder)
            #time.sleep(.03)
        return expanded

    def run(self):
        neighbors = True
        if self.start_item:
            self.my_cells.add(self.start_item)
        else:
            row = rng.choice(list(range(len(self.parent.data))))
            items = self.parent.data[row]
            item = rng.choice(items)
            if not item.color.sum():
                item.set_color(random_color())
            self.my_cells.add(item)
            self.status.emit(item, self)
        while neighbors:
            neighbors = self.edges()
            if neighbors:
                last = self.update_neighbors(rng.choice(neighbors))
                last.set_color(last.average_color(last.get_surrounding_color()))
                self.status.emit(last, self)
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
        self.edge = True

        self.setPen(Qt.NoPen)
        self.setBrush(QColor(*self.color.tolist()))

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

    def is_edge(self):
        if self.edge:
            if len(self.get_surrounding_color()) == len(self.neighbors):
                self.edge = False
        return self.edge

    def bleed(self, force=False):
        if not self.color.sum() or force:
            surrounding = self.get_surrounding_color()
            self.color = self.average_color(surrounding)
        return self.color

    def boundingRect(self):
        return QRect(0, 0, 2, 2)

    def set_color(self, color):
        self.setBrush(QColor(*color.tolist()))
        self.color = color

        
class MyMainWindow(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        
        loadUi(r"%s\active_scene.ui" % here, self)
        self.setWindowIcon(QIcon(r"%s\app_icon.png" % here))
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('active_scene')

        self.active_scene = QGraphicsScene(self)
        self.graphix_view.setScene(self.active_scene)
        self.scene_updaters = []
        self.known = set()
        self.items_to_update = set()
        self.data = []
        self.timer = QTimer(self)

    def closeEvent(self, event):
        for updater in self.scene_updaters:
            if updater.isRunning():
                updater.stop()

    def wheelEvent(self, event):
        # zoomIn factor
        factor = 1.15
        # zoomOut factor
        if event.angleDelta().y() < 0:
            factor = 1.0 / factor

        self.graphix_view.scale(factor, factor)
        #self.graphix_view.update()
        event.accept()

    def generate(self):
        self.data = []
        for r in list(range(500)):
            row = []
            for c in list(range(500)):
                cell = Cell([c, r], parent=self)
                row.append(cell)
                self.items_to_update.add(cell)
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
        #QCoreApplication.processEvents()

        for i in list(range(3)):
            scene_updater = SceneUpdateWorker(parent=self)
            scene_updater.status.connect(self.update_activity)
            scene_updater.finished.connect(self.finish_activity)
            scene_updater.start()
            self.scene_updaters.append(scene_updater)
            time.sleep(.1)
        print('active threads: %d' % len(self.scene_updaters))

        #self.timer.timeout.connect(self.do_updates)
        #self.timer.start(750)

    def do_updates(self):
        self.active_scene.update()
        #self.timer.setInterval(350*len(self.scene_updaters))

    def update_activity(self, item, thread):
        if item in self.known:
            return
        self.known.add(item)
        item.update()
        if item in self.items_to_update:
            self.items_to_update.remove(item)
        item.updated = item.updated + 1
        if len(self.scene_updaters) < 5:
            chance = rng.integers(100000, size=1)[0]
            if chance < 2:
                possible = thread.edges()
                if chance == 1:
                    possible = list(self.items_to_update)
                if len(possible):
                    new_thread = SceneUpdateWorker(parent=self)
                    new_thread.my_cells = thread.my_cells
                    new_thread.start_item = rng.choice(possible)
                    new_thread.status.connect(self.update_activity)
                    new_thread.finished.connect(self.finish_activity)
                    new_thread.start()
                    self.scene_updaters.append(new_thread)
                print('active threads: %d' % len(self.scene_updaters))

    def finish_activity(self, thread):
        if thread in self.scene_updaters:
            self.scene_updaters.remove(thread)
        if thread.isRunning():
            thread.stop()
            thread.quit()
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
