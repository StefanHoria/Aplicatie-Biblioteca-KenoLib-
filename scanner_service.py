# scanner_service.py
"""
Serviciu de ascultare pentru scannerul de coduri de bare GM65 (USB, emulat
ca port serial COM). Rulează într-un thread separat pentru a nu bloca
interfața grafică în timp ce așteaptă date de pe port.

Codurile citite (ISBN-uri) sunt puse într-o `queue.Queue` thread-safe;
interfața grafică face polling periodic al acestei cozi din thread-ul
principal (singurul thread în care este permis să se modifice widget-uri
Tkinter/CustomTkinter).
"""

import queue
import threading
import time

import serial
import serial.tools.list_ports

from config import SERIAL_BAUDRATE, SERIAL_READ_TIMEOUT


class ScannerService:
    """Gestionează conexiunea serială și thread-ul de citire continuă."""

    def __init__(self):
        self._serial = None
        self._thread = None
        self._stop_event = threading.Event()
        self.queue = queue.Queue()
        self.connected = False
        self.port = None
        self.last_error = None

    @staticmethod
    def list_ports():
        """Returnează lista porturilor COM disponibile în sistem."""
        return [p.device for p in serial.tools.list_ports.comports()]

    def connect(self, port, baudrate=SERIAL_BAUDRATE):
        """Deschide conexiunea serială și pornește thread-ul de ascultare."""
        self.disconnect()
        try:
            self._serial = serial.Serial(port, baudrate, timeout=SERIAL_READ_TIMEOUT)
        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            raise

        self.port = port
        self.connected = True
        self.last_error = None
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def disconnect(self):
        """Oprește thread-ul de ascultare și închide portul, dacă e deschis."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self.connected = False
        self._thread = None

    def _listen_loop(self):
        """Bucla de fundal: citește linie cu linie ce trimite scannerul GM65."""
        while not self._stop_event.is_set():
            try:
                if self._serial and self._serial.in_waiting:
                    raw = self._serial.readline()
                    code = raw.decode("utf-8", errors="ignore").strip()
                    if code:
                        self.queue.put(code)
                else:
                    time.sleep(0.1)
            except (serial.SerialException, OSError) as exc:
                self.last_error = str(exc)
                self.connected = False
                break
            except Exception:
                time.sleep(0.5)
