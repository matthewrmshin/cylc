# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2018 NIWA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Provides a Jinja2 filter for formatting ISO8601 duration strings."""

from isodatetime.parsers import DurationParser

SECONDS_PER_HOUR = 3600.0

def duration_to_hours(iso8601_duration):
    """Format an iso8601 duration string as floating-point hours.

    Args:
        iso8601_duration (str): Any valid ISO8601 duration as a string.

    Return:
        The total number of hours contained in the specified duration
        as a floating-point number.

    Raises:
        ISO8601SyntaxError: In the event of an invalid datetime string.

    Examples:
        >>> # Basic usage.
        >>> duration_to_hours('P1D')
        24.0
        >>> duration_to_hours('PT1H')
        1.0

        >>> # Exceptions.
        >>> try:
        ...     duration_to_hours('invalid')  # Invalid duration
        ... except Exception as exc:
        ...     print type(exc)
        <class 'isodatetime.parsers.ISO8601SyntaxError'>
    """
    s = DurationParser().parse(duration).get_seconds()
    return s / SECONDS_PER_HOUR
