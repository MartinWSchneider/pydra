import psychopy.monitors

from pydra import Pydra, ports, config
from pydra.modules.visual_stimulation import PSYCHOPY
from pathlib import Path



PSYCHOPY["worker"].window_params = dict(allowGUI=False,
                                        monitor="Martin_theia_projector",
                                        fullscr=True,
                                        units="degFlatPos",
                                        colorSpace=u"rgb",
                                        screen=1,
                                        color=(-1, -1, -1))

PSYCHOPY["params"] = {"stimulus_file": Path.cwd().joinpath("dotstim.py")}

config["modules"] = [PSYCHOPY]


if __name__ == "__main__":
    config = Pydra.configure(config, ports)
    pydra = Pydra.run(working_dir=r"F:\Martin\20211202", **config)
