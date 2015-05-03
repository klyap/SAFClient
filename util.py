# coding=utf-8

"""
Util module for datetime handling.

Notes
-----
Module should be shared between client/tools, but a symlink is not provided.
Common functions between this file and saf/util should also be shared.

"""

import datetime
import logging
import os


# Parses ISO format, with or without microseconds.
DATETIME_FMT = '%Y-%m-%dT%H:%M:%S.%f'
URL_DATE_FORMAT = '%Y-%m-%dT%H-%M-%S.%f'
# ISO order, but without separators ([:.] not allowed by taskqueue).
JOB_DATE_FORMAT = '%Y%m%d%H%M%S%f'


def date_format(datetime_obj, url_format=False):
    """
    Put date in expected ISO serialized format without microseconds.

    Parameters
    ----------
    datetime_obj : datetime.datetime
        The date to format into `DATETIME_FMT` format.

    Returns
    -------
    datetime_str : string
        The `string` version of the provided `datetime` object.

    Notes
    -----
    Both date functions belong in a utility class, but creating one for just
    these two functions is a bit much. They can live in `base_handler` for now.

    Examples
    --------
    >>> import util
    >>> util.date_format(datetime.datetime.utcnow())
    '2013-02-26T19:50:43.912'

    """
    if url_format:
        return datetime_obj.strftime(URL_DATE_FORMAT)[:-3]
    else:
        # Using .isoformat() strips the fractional seconds if there are none.
        return datetime_obj.strftime(DATETIME_FMT)[:-3]


def parse_date(datetime_str, url_format=False):
    """
    Return `datetime` object from expected ISO serialized format.

    Parameters
    ----------
    datetime_str : string
        The ISO formatted date to convert back to a `datetime` object.

    Returns
    -------
    datetime_obj : datetime.datetime
        The `datetime` object represented by the provided `string`.

    Examples
    --------
    >>> import util
    >>> util.parse_date('2013-02-26T19:50:43.912')
    datetime.datetime(2013, 2, 26, 19, 50, 43, 912000)

    """
    if url_format:
        return datetime.datetime.strptime(datetime_str, URL_DATE_FORMAT)
    else:
        return datetime.datetime.strptime(datetime_str, DATETIME_FMT)


def system_time():
    return datetime.datetime.utcnow()


class DateFormattedFileHandler(logging.FileHandler):

    def __init__(self, filename, utc=True, **kwargs):
        date = datetime.datetime.utcnow() if utc else datetime.datetime.now()
        filename = filename.format(date=date)
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        super(DateFormattedFileHandler, self).__init__(filename, **kwargs)
