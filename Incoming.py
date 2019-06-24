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

import sys
import os
import re
import subprocess

from PyHg_lib import Changeset

#--------------------------------------------

class Incoming(object):
    (STYLE_UNDEFINED, STYLE_PLAIN, STYLE_COLOR) = (0, 1, 2)

    def __init__(self, options, command=['hg', 'incoming', '-v', '-n', '-M'], database=False, target_branch=None, ignore_branch=False):
        if not options.branch:
            return

        self.options = options

        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        lines = output.split('\n')

        self.changesets = []

        max_lines = len(lines)
        i = 0

        while True:
            try:
                line = lines[i].strip()
            except:
                break

            result = re.search('changeset:(.+)$', line)
            if result:
                cs = Changeset()
                setattr(cs, 'changeset', result.group(1).strip())

                while not line.startswith('description:'):
                    result = re.search('(\w+)\s*:\s*(.+)$', line)
                    key = result.group(1).strip()
                    value = result.group(2).strip()
                    if key == 'files':
                        value = value.split()
                    setattr(cs, key, value)

                    i += 1
                    line = lines[i].rstrip()

                # this is the "description" line, so we need to gather up
                # the description before pressing on.

                desc = []
                while True:
                    i += 1

                    try:
                        line = lines[i].rstrip()
                    except:
                        break

                    if line.startswith('changeset:'):
                        break

                    desc.append(line)

                setattr(cs, 'description', desc)

                if ignore_branch:
                    self.changesets.append(cs)
                else:
                    if target_branch:
                        if target_branch == getattr(cs, 'branch', None):
                            self.changesets.append(cs)
                    else:
                        if self.options.branch == getattr(cs, 'branch', 'default'):
                            self.changesets.append(cs)
            else:
                i += 1

        if not database:
            self.print_()

    def gather_file_details(self):
        if len(self.changesets) == 0:
            return

        for cs in self.changesets:
            # see if this changeset is known locally.  if not,
            # don't modify the 'files' attribute

            output = subprocess.Popen(['hg', 'status', '--rev', cs.changeset], stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0].decode("utf-8")
            if 'unknown revision' not in output:
                output = subprocess.Popen(['hg', 'status', '--change', cs.changeset], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                lines = output.split('\n')

                files = []
                for file in lines:
                    if file.endswith('\n'):
                        file = file.rstrip()
                    if (len(file) == 0) or (' ' not in file):
                        continue
                    try:
                        files.append(file.split(' ')[1])
                    except:
                        print("ERROR: Invalid format detected: '%s'" % file, file=sys.stderr)

                if len(files):
                    setattr(cs, 'files', files)

    def format(self, style=0, no_changes_message="No changes pending for branch"):
        lines = []
        if len(self.changesets) == 0:
            if (style == self.STYLE_COLOR) or ((style == self.STYLE_UNDEFINED) and self.options.ansi_color):
                if self.options.ansi_color_requires_batch:
                    if os.name == 'nt':
                        lines.append('@echo off')
                        lines.append('set FG=%_fg')
                        lines.append('set BG=%_bg')
                    lines.append('echo \033[1;32m%s "\033[1;35m%s\033[1;32m".\n' % (no_changes_message, self.options.branch))
                    if os.name == 'nt':
                        lines.append('color %FG on %BG')
                else:
                    lines.append('\033[1;32m%s "\033[1;35m%s\033[1;32m".' % (no_changes_message, self.options.branch))
            else:
                lines.append('%s "%s".' % (no_changes_message, self.options.branch))
        else:
            if (style == self.STYLE_COLOR) or ((style == self.STYLE_UNDEFINED) and self.options.ansi_color):
                if self.options.ansi_color_requires_batch:
                    if os.name == 'nt':
                        lines.append('@echo off')
                        lines.append('set FG=%_fg')
                        lines.append('set BG=%_bg')
                    for cs in self.changesets:
                        cs_user = cs.user.split()[0] if ' ' in cs.user else cs.user
                        lines.append('echo `\033[1;35m%s: \033[1;32m(%s)`' % (cs.changeset, cs_user))
                        if getattr(cs, 'files', None) != None:
                            for file in cs.files:
                                lines.append('echo `   \033[1;32m- \033[1;33m%s`' % file)
                        for line in cs.description:
                            if len(line):
                                first_line = True
                                max_width = 80
                                if len(line) > max_width:
                                    while len(line) > max_width:
                                        batch_line = ''
                                        x = max_width
                                        while line[x] != ' ':
                                            x -= 1
                                        text = line[:x]
                                        line = line[x+1:]
                                        #text = re.sub(' ', '&nbsp;', text)
                                        if len(text) != 0:
                                            if first_line:
                                                batch_line += 'echo `   \033[1;35m*'
                                                first_line = False
                                                max_width = 78
                                            else:
                                                batch_line += 'echo `   \033[1;35m...'
                                            batch_line += ' \033[1;32m%s`\n' % text
                                            lines.append(batch_line)
                                if len(line) != 0:
                                    if first_line:
                                        lines.append('echo `   \033[1;35m* \033[1;32m%s`' % line)
                                    else:
                                        lines.append('echo `   \033[1;35m... \033[1;32m%s`' % line)
                            else:
                                lines.append('')

                        ndx = -1
                        while lines[ndx] == '':
                            ndx -= 1
                        lines = lines[:ndx+1]

                        lines.append('-----------------------')

                    for ndx in range(len(lines)):
                        if lines[ndx] == '':
                            lines[ndx] = 'echo `   \033[1;35m*`'
                        elif lines[ndx].startswith('-'):
                            lines[ndx] = 'echo.\n'

                    if os.name == 'nt':
                        lines.append('color %FG on %BG')
                else:
                    for cs in self.changesets:
                        cs_user = cs.user.split()[0] if ' ' in cs.user else cs.user
                        lines.append('\033[1;35m%s: \033[1;32m(%s)' % (cs.changeset, cs_user))
                        if getattr(cs, 'files', None) != None:
                            for file in cs.files:
                                lines.append('   \033[1;32m- \033[1;33m%s' % file)
                        for line in cs.description:
                            first_line = True
                            max_width = 80
                            if len(line) > max_width:
                                while len(line) > max_width:
                                    x = max_width
                                    while (line[x] not in ' -/\\_.:;') and (x > 0):
                                        x -= 1
                                    if x == 0:
                                        text = line[:max_width+1]
                                        line = line[max_width+1:]
                                    else:
                                        if line[x] == ' ':
                                            text = line[:x]
                                            line = line[x+1:]
                                        else:
                                            text = line[:x+1]
                                            line = line[x+1:]
                                    if len(text) != 0:
                                        if first_line:
                                            lines.append('   \033[1;35m* \033[1;32m%s' % text)
                                            first_line = False
                                            max_width = 78
                                        else:
                                            lines.append('   \033[1;35m... \033[1;32m%s' % text)
                            if len(line) != 0:
                                if first_line:
                                    lines.append('   \033[1;35m* \033[1;32m%s' % line)
                                else:
                                    lines.append('   \033[1;35m... \033[1;32m%s' % line)
            else:
                for cs in self.changesets:
                    lines.append('%s:' % cs.changeset)
                    try:
                        for file in cs.files:
                            lines.append('   %s: %s' % (cs.user, file))
                    except:
                        pass
                    lines.extend(cs.description)

        return lines

    def print_(self, no_changes_message="No changes pending for branch"):
        lines = self.format(self.STYLE_UNDEFINED, no_changes_message)

        if self.options.ansi_color and self.options.ansi_color_requires_batch:
            open(self.options.batch_file_name, 'w').write('\n'.join(lines))
            os.system(self.options.batch_file_name)
        else:
            print('\n'.join(lines))
