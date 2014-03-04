from datetime import datetime
import locale
locale.setlocale(locale.LC_ALL, '')


def format_currency(number):
    return "%s ISK" % (locale.currency(number, symbol=False, grouping=True).replace(",", " "))


def to_roman(n):
    return ['I', 'II', 'III', 'IV', 'V'][n - 1]


def timestamp_to_string(timestamp, reverse=False):
    completion = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    if reverse:
        age = now - completion
    else:
        age = completion - now
    agestr = []
    if age.days > 0:
        agestr.append("%dd" % age.days)
    secs = age.seconds
    hours, minutes, seconds = secs // 3600, secs // 60 % 60, secs % 60
    if hours > 0:
        agestr.append("%02dh" % hours)
    if minutes > 0:
        agestr.append("%02dm" % minutes)
    if seconds > 0:
        agestr.append("%02ds" % seconds)
    return " ".join(agestr)
