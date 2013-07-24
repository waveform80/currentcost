# vim: set et sw=4 sts=4 fileencoding=utf-8:

from __future__ import (
    unicode_literals,
    print_function,
    absolute_import,
    division,
    )

import logging
import serial
from datetime import datetime
from collections import namedtuple
try:
    from xml.etree.cElementTree import fromstring
except ImportError:
    from xml.etree.ElementTree import fromstring


# Sensor types (currently only electricity)
ELECTRIC = 1


class CC128ElectricReading(object):
    """
    Represents a reading from a CC-128 electric sensor channel.
    """
    def __init__(self, watts):
        self.watts = watts

    def __repr__(self):
        return repr(self.watts)


class CC128RealTimeMessage(object):
    """
    Represents a real-time reading from a CC-128 meter.
    """
    def __init__(
            self, source, age, timestamp, temperature, sensor_id, radio_id,
            sensor_type, channels):
        self.source = source
        self.age = age
        self.timestamp = timestamp
        self.temperature = temperature
        self.sensor_id = sensor_id
        self.radio_id = radio_id
        self.sensor_type = sensor_type
        self.channels = list(channels)

    def __repr__(self):
        return '<CC128RealTimeMessage(timestamp=%r, temperature=%r, channels=%r, ...)>' % (
                self.timestamp, self.temperature, self.channels)

    @classmethod
    def from_xml(cls, msg):
        return cls(
            source=msg.find('src').text,
            age=int(msg.find('dsb').text),
            timestamp=datetime.strptime(msg.find('time').text, '%H:%M:%S').time(),
            temperature=float(msg.find('tmpr').text),
            sensor_id=int(msg.find('sensor').text),
            radio_id=int(msg.find('id').text),
            sensor_type=int(msg.find('type').text),
            channels=[
                CC128ElectricReading(
                    watts=int(msg.find('ch%d' % channel).find('watts').text))
                        if msg.find('ch%d' % channel)
                else None
                for channel in range(1, 10)
                ]
            )


class CC128HistoryMessage(object):
    """
    Represents a history reading from a CC-128 meter.
    """
    def __init__(self):
        pass

    @classmethod
    def from_xml(cls, msg):
        pass


class CC128Reader(object):
    """
    Provides an infinite iterator that parses data from a CC-128 meter.
    """
    def __init__(self, port):
        logging.warning('Connecting to CC-128 Meter on %s' % port)
        self.port = serial.Serial(
            port, baudrate=57600, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=None, rtscts=True)

    def close(self):
        self.port.close()

    def __iter__(self):
        while True:
            line = self.port.readline()
            logging.debug('RX: %r', line)
            if not line:
                raise ValueError('Timed out')
            msg = fromstring(line)
            if msg.tag != 'msg':
                raise ValueError('Unexpected root element %s' % msg.tag)
            if msg.find('hist'):
                # Ignore the history message
                logging.warning('Ignoring history message')
                continue
            yield CC128RealTimeMessage.from_xml(msg)

