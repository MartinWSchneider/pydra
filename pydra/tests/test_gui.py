from pydra import Pydra, ports, config
from pydra.core import Worker, Acquisition
from pydra.gui.module import ModuleWidget
from PyQt5 import QtWidgets
import numpy as np
import time


class AcquisitionWorker(Acquisition):

    name = "acquisition"

    def __init__(self, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = value
        self.i = 0
        self.events["set_value"] = self.set_value

    def set_value(self, value, **kwargs):
        self.value = value
        print(f"{self.name}.value was set to: {self.value}")

    def acquire(self):
        frame = np.random.random((250, 250))
        frame *= 255
        frame = frame.astype("uint8")
        t = time.time()
        time.sleep(0.01)
        self.send_frame(t, self.i, frame)
        self.i += 1


class AcquisitionWidget(ModuleWidget):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWidget(QtWidgets.QWidget())
        self.widget().setLayout(QtWidgets.QFormLayout())
        self.value_widget = QtWidgets.QSpinBox()
        self.value_widget.valueChanged.connect(self.set_value)
        self.widget().layout().addRow("Value:", self.value_widget)

    def set_value(self, val):
        self.send_event("set_value", value=val)

    def enterRunning(self):
        self.setEnabled(False)

    def enterIdle(self):
        self.setEnabled(True)


class TrackingWorker(Worker):

    name = "tracking"
    subscriptions = ("acquisition",)
    plot = ("x", "y")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def recv_frame(self, t, i, frame, **kwargs):
        data = dict(x=np.random.rand(), y=np.random.rand())
        self.send_indexed(t, i, data)


ACQUISITION = {
    "worker": AcquisitionWorker,
    "params": {"value": 1},
    "widget": AcquisitionWidget,
}


TRACKING = {
    "worker": TrackingWorker
}


config["modules"] = [ACQUISITION, TRACKING]


if __name__ == "__main__":
    config = Pydra.configure(config, ports)
    pydra = Pydra.run(working_dir="D:\pydra_tests", **config)
