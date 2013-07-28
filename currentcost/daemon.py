# vim: set et sw=4 sts=4 fileencoding=utf-8:

"""\
A small command line application for dumping real-time data from a CC-128
meter.
"""

from __future__ import (
    unicode_literals,
    print_function,
    absolute_import,
    division,
    )

import os
import io
import sys
import serial
import select
import signal
import logging
import csv
import json
import sqlite3
import urlparse
import urllib
import urllib2
import xml.etree.ElementTree as et
from datetime import datetime, date, timedelta

from daemon import DaemonContext

from currentcost import __version__
from currentcost.terminal import TerminalApplication
from currentcost.reader import CC128Reader


class CC128Application(TerminalApplication):
    def __init__(self):
        super(CC128Application, self).__init__(
            version=__version__,
            usage='%prog [options]',
            description=__doc__)
        self.handle_sigint = None
        self.handle_sigterm = None
        self.terminated = False
        self.parser.set_defaults(
            port='COM1' if sys.platform.startswith('win') else '/dev/ttyUSB0',
            daemon=False,
            system_clock=True,
            csv_file=None,
            json_file=None,
            xml_file=None,
            rrd_file=None,
            db_table=None,
            get_url=None,
            post_url=None,
            )
        self.parser.add_option(
            '-p', '--port', dest='port', action='store',
            help='specify the port which the OxiTop Data Logger is connected '
            'to. This will be something like /dev/ttyUSB0 on Linux or COM1 '
            'on Windows. Default: %default')
        self.parser.add_option(
            '-d', '--daemon', dest='daemon', action='store_true',
            help='if specified, start the application as a background daemon')
        self.parser.add_option(
            '--meter-clock', dest='system_clock', action='store_false',
            help="if specified, use the meter's clock instead of the system's")
        self.parser.add_option(
            '--output-json', dest='json_file', action='store',
            help='write readings to the specified JSON file (overwriting it if it exists)')
        self.parser.add_option(
            '--output-xml', dest='xml_file', action='store',
            help='write readings to the specified XML file (overwriting it if it exists)')
        self.parser.add_option(
            '--output-csv', dest='csv_file', action='store',
            help='append readings to the specified CSV file')
        self.parser.add_option(
            '--output-sqlite', dest='db_table', action='store',
            help='append readings to the specified database:table')
        self.parser.add_option(
            '--output-rrd', dest='rrd_file', action='store',
            help='append readings to the specified RRDtool database')
        self.parser.add_option(
            '--output-http-get', dest='get_url', action='store',
            help='make an HTTP GET request for each reading to the specified URL')
        self.parser.add_option(
            '--output-http-post', dest='post_url', action='store',
            help='make an HTTP POST request for each reading to the specified URL')

    def handle(self, exc_type, exc_value, exc_trace):
        "Global application exception handler"
        if issubclass(exc_type, select.error):
            # Extend simple exception handling to select errors
            logging.critical(str(exc_value[1]))
        elif issubclass(exc_type, serial.SerialException):
            # Extend simple exception handling to serial exceptions
            logging.critical(str(exc_value))
            return 1
        else:
            return super(CC128Application, self).handle(
                    exc_type, exc_value, exc_trace)

    def terminate(self, signum, frame):
        logging.info('Received SIGTERM')
        self.terminated = True

    def interrupt(self, signum, frame):
        logging.info('Received SIGINT')
        self.terminated = True

    def write_csv(self, f, writer, msg):
        logging.info('Writing values to CSV file')
        writer.writerow(
            [msg.timestamp, msg.temperature] +
            [reading.watts
                if reading is not None else None
                for reading in msg.channels]
            )
        f.flush()

    def write_json(self, f, msg, first=False):
        logging.info('Writing values to JSON file')
        s = json.dumps({
            'timestamp':   msg.timestamp.isoformat(),
            'temperature': msg.temperature,
            'channels':    [
                reading.watts if reading is not None else None
                for reading in msg.channels],
            })
        if first:
            s = '%s\n]' % s
        else:
            f.seek(-2, io.SEEK_END)
            s = ',\n%s\n]' % s
        f.write(s)
        f.flush()

    def write_xml(self, f, msg, first=False):
        logging.info('Writing values to XML file')
        e = et.Element('reading')
        e.attrib['timestamp'] = msg.timestamp.isoformat()
        e.attrib['temperature'] = '%f' % msg.temperature
        for num, reading in enumerate(msg.channels):
            if reading is not None:
                c = et.SubElement(e, 'channel')
                c.attrib['id'] = str(num + 1)
                c.attrib['watts'] = str(reading.watts)
        s = et.tostring(e) + '\n</readings>'
        if not first:
            f.seek(-11, io.SEEK_END)
        f.write(s)
        f.flush()

    def write_rrd(self, f, msg):
        logging.info('Writing values to RRDtool')
        pass

    def create_sqlite(self, db, table):
        conn = sqlite3.connect(db, detect_types=sqlite3.PARSE_DECLTYPES)
        try:
            with conn:
                exists = False
                for row in conn.execute('PRAGMA table_info("%s")' % table):
                    exists = True
                    break
                if not exists:
                    conn.execute("""
                        CREATE TABLE %s (
                            TS      TIMESTAMP NOT NULL,
                            CHANNEL INTEGER NOT NULL,
                            WATTS   FLOAT NOT NULL
                        )""" % table)
        finally:
            conn.close()
        return os.path.abspath(db)

    def write_sqlite(self, db, table, msg):
        logging.info('Writing rows to SQLite table')
        for num, reading in enumerate(msg.channels):
            if reading is not None:
                with db:
                    db.execute("INSERT INTO %s VALUES (?, ?, ?)" % table,
                            (msg.timestamp, num, reading.watts))

    def http_get_request(self, url, msg):
        logging.info('Executing HTTP GET request')
        url = urlparse.urlsplit(url)
        query = urlparse.parse_qs(url.query)
        query['timestamp'] = msg.timestamp
        query['temperature'] = msg.temperature
        for num, reading in enumerate(msg.channels):
            if reading is not None:
                query['channel%d' % (num + 1)] = reading.watts
        url = urlparse.urlunsplit((
            url.scheme,
            url.netloc,
            url.path,
            urllib.urlencode(query),
            url.fragment,
            ))
        f = urllib2.urlopen(url)
        try:
            if not (200 <= f.getcode() < 300):
                raise ValueError('Response code %s while opening %s' % (
                    f.getcode(), f.geturl()))
        finally:
            f.close()

    def http_post_request(self, url, msg):
        logging.info('Executing HTTP POST request')
        pass

    def main(self, options, args):
        meter = CC128Reader(options.port)
        files_preserve = [meter.port]
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.FileHandler):
                files_preserve.append(handler.stream)
        if not options.daemon:
            files_preserve.append(sys.stderr)
        # Configure destination objects
        json_file = xml_file = csv_file = csv_writer = db = table = None
        if options.json_file:
            logging.warning('Creating JSON file %s' % options.json_file)
            json_file = io.open(options.json_file, 'wb')
            json_file.write('[\n')
            files_preserve.append(json_file)
        if options.xml_file:
            logging.warning('Creating XML file %s' % options.xml_file)
            xml_file = io.open(options.xml_file, 'wb')
            xml_file.write('<?xml version="1.0" encoding="UTF-8"?>\n<readings>\n')
            files_preserve.append(xml_file)
        if options.csv_file:
            logging.warning('Appending to CSV file %s' % options.csv_file)
            csv_file = io.open(options.csv_file, 'ab')
            csv_writer = csv.writer(csv_file)
            files_preserve.append(csv_file)
        if options.db_table:
            if not ':' in options.db_table:
                self.parser.error('Missing table in db:table specification for --output-sqlite')
            db, table = options.db_table.rsplit(':', 1)
            logging.warning('Connecting to SQLite database %s' % db)
            db = self.create_sqlite(db, table)
        # Launch the daemon
        with DaemonContext(
                files_preserve=files_preserve,
                # The following odd construct is to ensure detachment only
                # where sensible (see default setting of detach_process)
                detach_process=None if options.daemon else False,
                stdout=None if options.daemon else sys.stdout,
                stderr=None if options.daemon else sys.stderr,
                signal_map={
                    signal.SIGTERM: self.terminate,
                    signal.SIGINT: self.interrupt,
                    }):
            logging.info('Starting read loop')
            # If we're writing to a SQLite database, open it within the daemon
            # context. We can't preserve its file handle because the sqlite3
            # module provides no means for us to get the file handle
            if db:
                db = sqlite3.connect(db, detect_types=sqlite3.PARSE_DECLTYPES)
            try:
                first = True
                for msg in meter:
                    now = datetime.now()
                    if options.system_clock:
                        msg.timestamp = now
                    else:
                        # The meter's timestamp lacks a date component...
                        msg.timestamp = datetime.combine(date.today(), message.timestamp)
                        # Compensate for clock drift over day boundaries
                        if msg.timestamp - now > timedelta(hours=12):
                            msg.timestamp -= timedelta(hours=24)
                        elif msg.timestamp - now < -timedelta(hours=12):
                            msg.timestamp += timedelta(hours=24)
                    if options.csv_file:
                        self.write_csv(csv_file, csv_writer, msg)
                    if options.json_file:
                        self.write_json(json_file, msg, first)
                    if options.xml_file:
                        self.write_xml(xml_file, msg, first)
                    if options.db_table:
                        self.write_sqlite(db, table, msg)
                    if options.get_url:
                        self.http_get_request(options.get_url, msg)
                    if options.post_url:
                        self.http_post_request(options.post_url, msg)
                    if self.terminated:
                        break
                    first = False
            except (SystemExit, KeyboardInterrupt) as exc:
                pass
            logging.info('Exiting')

main = CC128Application()
