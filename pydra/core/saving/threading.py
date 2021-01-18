from ..messaging import *
from ..messaging.serializers import *
import threading
import queue
import cv2
from pathlib import Path
from collections import deque
import pandas as pd


class Thread(threading.Thread):

    def __init__(self, path: str, q: queue.Queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = str(path)
        self.q = q

    def setup(self):
        return

    def dump(self, *args):
        return

    def cleanup(self):
        return

    def run(self):
        self.setup()
        while True:
            try:
                data = self.q.get(timeout=0.01)
                if data:
                    self.dump(*data)
                else:
                    break
            except queue.Empty:
                pass
        self.cleanup()


class FrameThread(Thread):

    def __init__(self, path, q, frame_rate, frame_size, fourcc, is_color=False, *args, **kwargs):
        super().__init__(path, q, *args, **kwargs)
        self.frame_rate = frame_rate
        self.frame_size = frame_size
        self.fourcc = fourcc
        self.is_color = is_color
        self.writer = None

    def setup(self):
        fourcc = cv2.VideoWriter_fourcc(*self.fourcc)
        self.writer = cv2.VideoWriter(self.path, fourcc, self.frame_rate, self.frame_size, self.is_color)

    def dump(self, source, frame):
        frame = deserialize_array(frame)
        self.writer.write(frame)

    def cleanup(self):
        self.writer.release()


class IndexedThread(Thread):

    def __init__(self, path, q, *args, **kwargs):
        super().__init__(path, q, *args, **kwargs)
        self.data = None

    def setup(self):
        self.data = {}

    def dump(self, source, t, i, data):
        t, i, data = DataMessage(INDEXED).decode(t, i, data)
        try:
            self.data[source]["time"].append(t)
            self.data[source]["index"].append(i)
            if data:
                for key, val in data.items():
                    self.data[source]["data"][key].append(val)
        except KeyError:
            self.data[source] = dict(time=[t], index=[i])
            if data:
                for key, val in data.items():
                    self.data[source]["data"] = {key: [val]}

    def cleanup(self):
        dfs = []
        for source, data in self.data.items():
            if "data" in data:
                df = pd.DataFrame(data["data"], index=data["index"])
                col_map = {}
                for col in df.columns:
                    col_map[col] = "_".join([source, col])
                df.rename(columns=col_map, inplace=True)
            else:
                df = pd.DataFrame(index=data["index"])
            df[source + "_t"] = data["time"]
            dfs.append(df)
        df = pd.concat(dfs, axis=1)
        df.to_csv(self.path)


class TimestampedThread(Thread):

    def __init__(self, path, q, *args, **kwargs):
        super().__init__(path, q)
        self.data = None

    def setup(self):
        self.data = {}

    def dump(self, source, t, data):
        t, data = DataMessage(TIMESTAMPED).decode(t, data)
        try:
            self.data[source]["time"].append(t)
            for key, val in data.items():
                self.data[source][key].append(val)
        except KeyError:
            self.data[source] = dict(time=[t])
            for key, val in data.items():
                self.data[source][key] = [val]

    def cleanup(self):
        return


class ThreadGroup:

    def __init__(self, name, members):
        self.name = name
        self.members = members
        self.frame_q = queue.Queue()
        self.indexed_q = queue.Queue()
        self.timestamped_q = queue.Queue()
        # Data handling
        self.frame = None
        self.timestamps = deque(maxlen=1000)
        self.data_cache = {}
        self.fourcc = "XVID"

    @property
    def frame_rate(self):
        return len(self.timestamps) / (self.timestamps[-1] - self.timestamps[0])

    @property
    def frame_size(self):
        return deserialize_array(self.frame).shape[:2][::-1]

    @property
    def is_color(self):
        return deserialize_array(self.frame).ndim > 2

    def update(self, source, dtype, *args):
        t = deserialize_float(args[0])
        i = None
        if dtype == "frame":
            self.timestamps.append(t)
            i = deserialize_int(args[1])
            self.frame = args[2]
            data = None
        elif dtype == "indexed":
            i = deserialize_int(args[1])
            data = deserialize_dict(args[2])
        elif dtype == "timestamped":
            data = deserialize_dict(args[1])
        else:
            return
        if source in self.data_cache:
            self.data_cache[source]["time"].append(t)
            if i is not None:
                self.data_cache[source]["index"].append(i)
            if data:
                for key, val in data.items():
                    self.data_cache[source]["data"][key].append(val)
        else:
            self.data_cache[source] = {}
            self.data_cache[source]["time"] = [t]
            if i is not None:
                self.data_cache[source]["index"] = [i]
                if data:
                    for key, val in data.items():
                        self.data_cache[source]["data"] = {key: [val]}

    def flush(self):
        serialized = serialize_dict(self.data_cache)
        self.data_cache = {}
        return serialized

    def save_frame(self, source, t, i, frame):
        self.frame_q.put((source, frame))
        self.indexed_q.put((source, t, i, "null".encode("utf-8")))

    def save_indexed(self, source, t, i, data):
        self.indexed_q.put((source, t, i, data))

    def save_timestamped(self, source, t, data):
        self.timestamped_q.put((source, t, data))

    def start(self, directory, filename):
        # Base name
        directory = Path(directory)
        if not directory.exists():
            directory.mkdir(parents=True)
        filename = str(directory.joinpath(filename + self.name))
        # Frame thread
        self.frame_thread = FrameThread(filename + ".avi", self.frame_q, int(self.frame_rate), self.frame_size, self.fourcc, self.is_color)
        self.frame_thread.start()
        # Indexed thread
        self.indexed_thread = IndexedThread(filename + ".csv", self.indexed_q)
        self.indexed_thread.start()
        # Timestamped thread
        self.timestamped_thread = TimestampedThread(filename + "_events.csv", self.timestamped_q)
        self.timestamped_thread.start()

    def stop(self):
        # Send termination signal
        self.timestamped_q.put(b"")
        self.indexed_q.put(b"")
        self.frame_q.put(b"")
        # Join threads
        self.timestamped_thread.join()
        self.indexed_thread.join()
        self.frame_thread.join()