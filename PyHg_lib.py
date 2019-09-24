from __future__ import print_function

#------------------------------------------------------------------------------
# MIT License
#
# Copyright (c) 2019 Bob Hood
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#------------------------------------------------------------------------------

"""
Common routines used by the rest of the elements in the HG Suite.
"""

import sys
import os
import re
import shutil
import subprocess
import struct
import tempfile
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser
import tempfile
import binascii
import mimetypes

if sys.version_info[0] < 3:
    import codecs

LF=1
CRLF=2
MANIFEST_VERSION=1

# These are the extensions of common text-based files that we might encounter
# when processing embedded commit comments.
# (FYI: mimetypes.guess_type() will fail on some of these, even though they
# are clearly text-based, so when it fails, we fall back to checking these
# extensions manually)

__valid_extensions = [
                    '.h','.cpp','.c','.i','.xml','.y','.l',
                    '.mm','.htm','.html','.im', '.cfg', '.sln',
                    '.vcproj',
                    '.ls',                      # LScript
                    '.py','.pyw',               # Python
                    '.pl',                      # Perl
                    '.rst',                     # Sphinx
                    '.pro','.pri','.qrc','.ui', # Qt
                    '.dart'                     # Flutter/Dart
                    ]
DISPLAY_PLAIN, DISPLAY_COMMENT, DISPLAY_ANSI, DISPLAY_HTML = range(0, 4)

Colors = {
    'Reset'         : '\033[0m',
    'White'         : '\033[37m',
    'Cyan'          : '\033[36m',
    'Magenta'       : '\033[35m',
    'Red'           : '\033[31m',
    'Green'         : '\033[32m',
    'Yellow'        : '\033[33m',
    'BrightBlack'   : '\033[1;90m',
    'BrightWhite'   : '\033[1;97m',
    'BrightCyan'    : '\033[1;96m',
    'BrightMagenta' : '\033[1;95m',
    'BrightRed'     : '\033[1;91m',
    'BrightGreen'   : '\033[1;92m',
    'BrightYellow'  : '\033[1;93m',
}

# from: https://stackoverflow.com/questions/898669/how-can-i-detect-if-a-file-is-binary-non-text-in-python
__textchars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)) - {0x7f})
__is_binary_string = lambda bytes: bool(bytes.translate(None, __textchars))

class Changeset(object):
    pass

#--------------------------------------------
# helper functions

class MyParser(ConfigParser.ConfigParser):
    def __init__(self, ini_file):
        ConfigParser.ConfigParser.__init__(self)
        if (type(ini_file) is str) and os.path.exists(ini_file):
            self.read(ini_file)

    def as_dict(self):
        d = dict(self._sections)
        for k in d:
            d[k] = dict(self._defaults, **d[k])
            d[k].pop('__name__', None)
        return d

def wrap_line(line, new_lines, col=80):
    while len(line) > col:
        x = col
        while (x > 0) and (not line[x].isspace()):
            x -= 1
        if x > 0:
            y = x
            while (y > 0) and line[y].isspace():
                y -= 1
        new_lines.append(line[:y+1])
        line = line[x:].strip()
    new_lines.append(line)

def wrap_lines(data, col=80):
    lines = None

    if isinstance(data, str):
        if os.path.exists(data):
            lines = open(data).readlines()
        else:
            if '\\n' in data:
                lines = data.split('\\n')
            elif '<br>' in data:
                lines = data.split('<br>')
            else:
                lines = [data]

            x = 1
            while(x < len(lines)):
                lines.insert(x, '')
                x += 2
    elif isinstance(data, (list, tuple)):
        lines = list(data)
    elif isinstance(data, file):
        lines = data.readlines()

    if lines is None:
        return []

    new_lines = []
    excess = ''

    for line in lines:
        if line.endswith('\n'):
            line = line.rstrip()
        if len(line) == 0:
            # new line
            if len(excess):
                wrap_line(excess, new_lines, col)
                excess = ''
            new_lines.append('')
        else:
            if len(excess):
                if excess.endswith('.'):
                    excess += ' '
                excess += ' '
            excess += line

    if len(excess):
        wrap_line(excess, new_lines, col)

    return new_lines

def find_hg_root():
    """ Find the Mercurial .hg folder location """
    with open(os.devnull, 'w') as f:
        try:
            root = subprocess.check_output(['hg', 'root'], stderr=f).decode("utf-8")
            root = os.path.join(root.rstrip(), '.hg')
        except:
            root = None

    return root

def find_mb_root():
    """ Find the microbranch root location """
    have_first_choice = False
    root = None
    # choice #1: try the environment first
    if 'PYHG_MICROBRANCH_ROOT' in os.environ:
        root = os.environ['PYHG_MICROBRANCH_ROOT']
        if not os.path.exists(root):
            root = None
        else:
            have_first_choice = True

    if not root:
        # choice #2: Root (of the current drive under Windows)
        root = '/microbranches'
        if not os.path.exists(root):
            root = None

    if not root:
        # choice #3: Mercurial folder of the working copy
        with open(os.devnull, 'w') as f:
            try:
                root = subprocess.check_output(['hg', 'root'], stderr=f).decode("utf-8")
                root = os.path.join(root.rstrip(), '.hg')
            except:
                root = None

    if not root:
        # last choice: System temp folder
        root = tempfile.gettempdir()
        if not os.path.exists(root):
            root = None

    if not root:
        # hmm... fail
        print('ERROR: Could not determine a valid microbranch root.', file=sys.stderr)
        sys.exit(1)

    if not have_first_choice:
        print('WARNING: Setting microbranch root to "%s".  Was this intended?' % root, file=sys.stderr)

    return root

def determine_line_endings(file_name):
    endings = LF
    with open(file_name, 'rb') as f:
        c = f.read(1)
        while c != "":
            if c == 13:
                endings = CRLF
                break
            c = f.read(1)
    return endings

def fix_line_endings(from_name, to_name, endings):
    lines = open(from_name, 'r').readlines()
    with open(to_name, 'wb') as f:
        for line in lines:
            line = line.rstrip()
            f.write(line)
            if endings == LF:
                f.write(struct.pack('B', 10))
            else:
                f.write(struct.pack('BB', 13, 10))

def make_path(file_name):
    path = os.path.dirname(file_name)
    elements = path.split(os.sep)
    path = ''
    for element in elements:
        if len(path):
            path += os.sep
        path += element
        if not os.path.exists(path):
            try:
                os.mkdir(path)
            except:
                return False
    return True

def colorize_status(lines):
    default_color = Colors['BrightWhite']
    modified_color = Colors['BrightCyan']
    added_color = Colors['BrightMagenta']
    removed_color = Colors['BrightRed']
    renamed_color = Colors['BrightGreen']
    copied_color = Colors['BrightYellow']
    reset_color = Colors['Reset']

    #if 'CMDER_ROOT' in sys.environ:
    #    # operating under Cmder
    #    default_color = '\033[1;33m'
    #    modified_color = '\033[1;36m'
    #    added_color = '\033[1;35m'
    #    removed_color = '\033[1;31m'
    #    renamed_color = '\033[1;32m'
    #    reset_color = '\nCOLOR'

    new_lines = []
    for line in lines:
        line = line.strip()
        if not len(line):
            continue

        color = default_color
        status = line[0]
        if status == 'M':
            status = '!'
            color = modified_color
        if status == 'A':
            status = '+'
            color = added_color
        if status == 'R':
            status = '-'
            color = removed_color
        if status == 'V':
            status = '*'
            color = renamed_color
        if status == 'C':
            status = '$'
            color = copied_color

        file = line[2:]

        new_lines.append((status, file, color, '%s%s %s%s' % (color, status, file, reset_color)))

    return new_lines

def get_changeset_for(options, file):
    if not options.branch:
        return None

    command = ['hg', 'log', '-l', '1', '-b', options.branch, file]
    output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
    if len(output) == 0:
        # probably no changes for the current branch...use the latest change instead
        command = ['hg', 'log', '-l', '1', file]
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")

    changeset = None
    lines = output.split('\n')
    for line in lines:
        line = line.rstrip()
        if line.startswith('changeset:   '):
            changeset = line[13:].strip()
            break

    return changeset

def fixup_renames(lines):
    # this function assumes an 'hg status' was executed
    # with the '-C' option to identify the "source of
    # copied files".
    #
    # if one is identified, it is either a copy or a
    # rename.  if it's a rename, then the source file
    # will no longer exist.

    renames = {}
    actions = {}

    previous_action = None
    previous_value = None

    for i in range(len(lines)):
        if len(lines[i]) == 0:
            continue
        action = lines[i][0]
        value = lines[i][2:]
        if action == 'A':
            if action not in actions:
                actions[action] = []
            actions[action].append((None,value))
            previous_action = action
            previous_value = value
        elif action == ' ' and previous_action == 'A':
            # this is a copy or a rename

            renames[value] = previous_value
            if 'A' in actions:
                # remove the 'A'
                for i in range(len(actions[previous_action])):
                    if actions[previous_action][i][1] == previous_value:
                        del actions[previous_action][i]
                        break

            previous_action = None
            previous_value = None
        elif action == 'R':
            # if this remove is in the renames map,
            # then it needs to be suppressed
            if value not in renames:
                # this is a remove, not a rename
                if action not in actions:
                    actions[action] = []
                actions[action].append((None,value))
        else:
            # all other status changes are captured
            # without additional processing
            if action not in actions:
                actions[action] = []
            actions[action].append((None,value))

    # process renames (all entries are 'A')
    for source in renames:
        if os.path.exists(source):
            # copy
            if 'C' not in actions:
                actions['C'] = []
            actions['C'].append((source,renames[source]))
        else:
            # rename
            if 'V' not in actions:
                actions['V'] = []
            actions['V'].append((source,renames[source]))

    new_lines = []
    for key in ['M',   # modified
                'A',   # added
                'V',   # renamed
                'R',   # removed
                'C']:  # copied
        if key in actions:
            for item in actions[key]:
                if item[0] is None:
                    new_lines.append('%s %s' % (key, item[1]))
                elif key == 'V':
                    new_lines.append('%s %s --> %s' % (key, item[0], item[1]))
                elif key == 'C':
                    new_lines.append('%s %s ==> %s' % (key, item[0], item[1]))

    return new_lines

def crc32(filename):
    buf = open(filename, 'rb').read()
    return (binascii.crc32(buf) & 0xFFFFFFFF)
    #return "%08X" % buf

def get_common_folder(files):
    def check_path(path, path_list):
        match_count = 0
        for p in path_list:
            if p.startswith(path):
                match_count += 1
        return match_count == len(path_list)

    paths = {}
    for f in files:
        paths[os.path.split(f)[0]] = True

    common_path = ''
    if len(paths) == 1:
        common_path = paths.keys()[0]
    else:
        keys = paths.keys()
        keys.sort(key=len)

        common_path = keys[-1]
        while check_path(common_path, keys) is False:
            common_path = os.path.split(common_path)[0]
            if len(common_path) == 0:
                break

    return common_path

def __pull_comments(lines, delete_comments=False, display_type=DISPLAY_PLAIN):
    has_comments = False
    gen_diff = False
    quiet = False

    comments = []

    for i in range(len(lines)):
        line = lines[i].rstrip()

        if ('@comment: ' in line) or \
           ('@public: ' in line) or \
           ('@private: ' in line):
            has_comments = True
            comment_text = ''

            result = re.search('@comment: (.+)$', line)
            if result != None:
                # 'comment:' is 'private' by default
                comment_text = result.group(1)
            else:
                result = re.search('@public: (.+)$', line)
                if result != None:
                    comment_text = '[PUBLIC] %s' % result.group(1)
                else:
                    result = re.search('@private: (.+)$', line)
                    if result != None:
                        comment_text = '[PRIVATE] %s' % result.group(1)

            if len(comment_text):

                # if it's multi-line, gather up the additional text
                # additional comment text begins on each additional
                # line after an '@' token

                while comment_text.endswith('\\'):
                    comment_text = comment_text[:-1]
                    i += 1
                    line = lines[i].rstrip()
                    if line.endswith('*/'):
                        index = -3
                        if line[index] == ' ':
                            while line[index] == ' ':
                                index -= 1
                        line = line[:index + 1]
                    result = re.search('@(.+)$', line)
                    if result:
                        comment_text += result.group(1)

                index = 0
                if comment_text.endswith('*/'):
                    index = -3
                elif comment_text.endswith('-->'):
                    index = -4
                if index != 0:
                    if comment_text[index] == ' ':
                        while comment_text[index] == ' ':
                            index -= 1
                    comment_text = comment_text[:index + 1]

                comments.append(comment_text)

        elif '@cleaner: ' in line:
            # this line should be one or more directives that enable
            # processing actions for just this file.  display it along
            # with any other comments.

            result = re.search('@cleaner: (.+)$', line)
            if result != None:
                cleaner_text = result.group(1)

                # are we being told to be 'quiet' about this file?
                if '(qt)' in cleaner_text:
                    return ['@cleaner: (qt)']

                index = 0
                if cleaner_text.endswith('*/'):
                    index = -3
                elif cleaner_text.endswith('-->'):
                    index = -4
                if index != 0:
                    if cleaner_text[index] == ' ':
                        while cleaner_text[index] == ' ':
                            index -= 1
                    cleaner_text = cleaner_text[:index + 1]

                comments.append('@cleaner: %s' % cleaner_text)

        elif '@diff:' in line:
            gen_diff = True

    fixed_comments = []
    if len(comments):
        if display_type == DISPLAY_COMMENT:
            prefix = '- ' if len(comments) > 1 else ''
            for comment in comments:
                fixed_comments.append('%s%s' % (prefix, comment))
        else:
            first_line = True
            for comment in comments:
                if (len(comment) > 80) and (not comment.startswith(':: ')):
                    first_line = True
                    while len(comment) > 80:
                        x = 80
                        while comment[x] != ' ':
                            x -= 1
                        text = comment[:x]
                        comment = comment[x+1:]

                        if display_type == DISPLAY_HTML:
                            text = re.sub(' ', '&nbsp;', text)

                        if first_line:
                            if display_type == DISPLAY_PLAIN:
                                fixed_comments.append('... %s' % text)
                            elif display_type == DISPLAY_HTML:
                                fixed_comments.append('...&nbsp;<i>%s</i>' % text)
                            first_line = False
                        else:
                            if display_type == DISPLAY_PLAIN:
                                fixed_comments.append('    %s' % text)
                            elif display_type == DISPLAY_HTML:
                                fixed_comments.append('&nbsp;&nbsp;&nbsp;&nbsp;<i>%s</i>' % text)

                    if display_type == DISPLAY_HTML:
                        comment = re.sub(' ', '&nbsp;', comment)

                    if first_line:
                        if display_type == DISPLAY_PLAIN:
                            fixed_comments.append('... %s' % comment)
                        elif display_type == DISPLAY_HTML:
                            fixed_comments.append('...&nbsp;<i>%s</i>' % comment)
                    else:
                        if display_type == DISPLAY_PLAIN:
                            fixed_comments.append('    %s' % comment)
                        elif display_type == DISPLAY_HTML:
                            fixed_comments.append('&nbsp;&nbsp;&nbsp;&nbsp;<i>%s</i>' % comment)
                else:
                    if display_type == DISPLAY_PLAIN:
                        line_prefix = '... '
                        line_postfix = ''
                    elif display_type == DISPLAY_HTML:
                        line_prefix = '...&nbsp;<i>'
                        line_postfix = '</i>'

                    if comment.startswith(':: '):
                        if display_type == DISPLAY_PLAIN:
                            line_prefix = '    '
                            line_postfix = ''
                        elif display_type == DISPLAY_HTML:
                            line_prefix = '&nbsp;&nbsp;&nbsp;&nbsp;<tt>'
                            line_postfix = '</tt>'
                    else:
                        if display_type == DISPLAY_HTML:
                            comment = re.sub(' ', '&nbsp;', comment)

                    fixed_comments.append('%s%s%s' % (line_prefix, comment, line_postfix))

    fixed_lines = []
    if delete_comments:
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            if ('@comment: ' in line) or \
               ('@public: ' in line) or \
               ('@private: ' in line):
                if line.endswith('\\'):
                    while line.endswith('\\'):
                        i += 1
                        line = lines[i].rstrip()
            else:
                fixed_lines.append(lines[i])
            i += 1

    return (fixed_lines, fixed_comments)

def marshall_comments(filename, display=DISPLAY_PLAIN):
    if not os.path.exists(filename):
        raise Exception("The provided file ('%s') does not exist." % filename)

    lines = []
    if sys.version_info[0] < 3:
        try:
            with codecs.open(filename, encoding='utf-8', errors='backslashreplace') as f:
                for l in f:
                    lines.append(l)
        except:
            raise Exception("Failed to read file '%s'" % filename)
    else:
        try:
            with open(filename, encoding='utf-8', errors='backslashreplace') as f:
                for l in f:
                    lines.append(l)
        except:
            raise Exception("Failed to read file '%s'" % filename)

    fixed_lines, comments = __pull_comments(lines, display_type=display)

    return comments

def extract_comments(filename, display=DISPLAY_PLAIN):
    if not os.path.exists(filename):
        raise Exception("The provided file ('%s') does not exist." % filename)

    try:
        lines = []
        with open(filename) as f:
            for line in f:
                lines.append(line)
    except:
        raise Exception("Failed to read file '%s'" % filename)

    if os.path.exists('%s.ht' % filename):
        try:
            os.remove('%s.ht' % filename)
        except:
            raise Exception("Failed to remove file '%s.ht'" % filename)

    try:
        shutil.copyfile(filename, '%s.ht' % filename)
    except:
        raise Exception("Failed to create backup of '%s'" % filename)

    fixed_lines, comments = __pull_comments(lines, delete_comments=True, display_type=display)

    try:
        open(filename, 'w').write(''.join(fixed_lines))
    except:
        raise Exception("Failed to write to file '%s'" % filename)

    return comments

def is_valid(filename):
    _is_valid = False
    # 1. try the quickest test first: known file extensions
    for ext in __valid_extensions:
        if filename.endswith(ext):
            _is_valid = True
            break
    if not _is_valid:
        # 2. see if mimetypes has any luck
        types = mimetypes.guess_type(filename)
        _is_valid = (types[0] == 'text/plain')
    if not _is_valid:
        # 3. last, brute force
        _is_valid = not __is_binary_string(open(filename, 'rb').read(1024))
    return _is_valid

ONEYEAR   = 31536000
ONEMONTH  = 2592000
ONEWEEK   = 604800
ONEDAY    = 86400
ONEHOUR   = 3600
ONEMINUTE = 60

YEARS, MONTHS, WEEKS, DAYS, HOURS, MINUTES = range(6)

def format_seconds(seconds, limits=[]):
    true_count = 0
    for i in limits: true_count += 1 if i else 0

    _str = ''
    if true_count == 1:
        if limits[YEARS]:
            amount = seconds / ONEYEAR
            plural = "s" if seconds > ONEYEAR else ""
            _str = '%d year%s' (amount, plural)
        elif limits[MONTHS]:
            amount = seconds / ONEMONTH
            plural = "s" if seconds > ONEMONTH else ""
            _str = '%d month%s' (amount, plural)
        elif limits[WEEKS]:
            amount = seconds / ONEWEEK
            plural = "s" if seconds > ONEWEEK else ""
            _str = '%d week%s' (amount, plural)
        elif limits[DAYS]:
            amount = seconds / ONEDAY
            plural = "s" if seconds > ONEDAY else ""
            _str = '%d day%s' (amount, plural)
        elif limits[HOURS]:
            amount = seconds / ONEHOUR
            plural = "s" if seconds > ONEHOUR else ""
            _str = '%d hour%s' (amount, plural)
        elif limits[MINUTES]:
            amount = seconds / ONEMINUTE
            plural = "s" if seconds > ONEMINUTE else ""
            _str = '%d minute%s' (amount, plural)
    else:
        if (len(limits) == 0 or limits[YEARS]) and seconds >= ONEYEAR:      # 31,536,000 seconds in 365 days
            years = seconds / ONEYEAR
            seconds -= (years * ONEYEAR)
            _str += '%dy' % years

        if (len(limits) == 0 or limits[MONTHS]) and seconds >= ONEMONTH:    # 2,592,000 seconds in a 30-day month
            months = seconds / ONEMONTH
            seconds -= (months * ONEMONTH)
            _str += '%d' % months
            _str += 'M' if (len(limits) == 0 or limits[MINUTES]) else 'm'

        if (len(limits) == 0 or limits[WEEKS]) and seconds >= ONEWEEK:      # 604,800 seconds in a 7-day week
            weeks = seconds / ONEWEEK
            seconds -= (weeks * ONEWEEK)
            _str += '%dw' % weeks

        if (len(limits) == 0 or limits[DAYS]) and seconds >= ONEDAY:        # 86,400 seconds in a 24-hour day
            days = seconds / ONEDAY
            seconds -= (days * ONEDAY)
            _str += '%dd' % days

        if (len(limits) == 0 or limits[HOURS]) and seconds >= ONEHOUR:      # 3,600 seconds in a 60-minute hour
            hours = seconds / ONEHOUR
            seconds -= (hours * ONEHOUR)
            _str += '%dh' % hours

        if (len(limits) == 0 or limits[MINUTES]) and seconds >= ONEMINUTE:
            minutes = seconds / ONEMINUTE
            seconds -= (minutes * ONEMINUTE)
            _str += '%dm' % minutes

        if seconds < ONEMINUTE:
            _str += '%ds' % seconds

    return _str
