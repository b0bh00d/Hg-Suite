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

#from Info import Status

#--------------------------------------------

class Diff(object):
    def __init__(self, options, command=['hg', 'wdiff'], database=False, target_branch=None, ignore_branch=False):
        if not options.branch:
            return

        self.options = options

        command_ = ['hg', 'status', '--subrepos', '-q', '.']
        output = subprocess.Popen(command_, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        lines = output.split('\n')
        if len(lines) == 0:
            print('No modified files detected for Diff operation!')
            sys.exit(0)

        files_to_diff = []
        for line in lines:
            line = line.rstrip()
            if len(line) == 0:
                continue

            if line.startswith('M '):
                line = line[2:]
                filename = os.path.basename(line)
                for arg in self.options.args:
                    if arg in filename:
                        files_to_diff.append(line)

        if len(files_to_diff) == 0:
            print('No modified files matched provided arguments ("%s")!' % self.options.args)
            sys.exit(0)

        if ('wdiff' in command) and ('PYHG_MERGE_TOOL' in os.environ):
            command += ['--config', 'extdiff.cmd.vdiff=%s' % os.environ['PYHG_MERGE_TOOL']]

        for file in files_to_diff:
            command_ = command + [file]
            subprocess.call(command_)
