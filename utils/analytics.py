"""
TODO: Implement
Analytics module for the bot
"""
import time


def register_event(event_type, metadata):
    pass


class Timer:
    def __init__(self):
        self._start_time = None

    def start(self):
        """Start a new timer"""

        self._start_time = time.perf_counter()
        return self

    def stop(self, use_ms=True, round_digits=4):
        """Stop the timer, and report the elapsed time"""
        if self._start_time is None:
            return None

        elapsed_time = time.perf_counter() - self._start_time
        self._start_time = None
        if use_ms:
            return round(elapsed_time / 1000, round_digits)
        else:
            return round(elapsed_time, round_digits)
