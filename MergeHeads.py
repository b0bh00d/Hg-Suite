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
import subprocess

#--------------------------------------------

class MergeHeads(object):
    def __init__(self, options):
        if not options.branch:
            return

        # if there's more than one 'changeset:' tag, then there are multiple heads

        command = ['hg', 'heads', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        lines = output.split('\n')
        changeset_count = 0
        for line in lines:
            if line.startswith('changeset:'):
                changeset_count += 1

        if changeset_count < 2:
            print('Branch only contains a single head!')
            sys.exit(0)

        # if there are uncommitted changes, then we abort

        command = ['hg', 'status', '-q', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        if len(output):
            print('Cannot merge heads while uncommitted changes exist!')
            sys.exit(0)

        try:
            subprocess.check_call(['hg', 'merge'])
        except:
            print('Merge failed!')
            sys.exit(0)

        try:
            subprocess.check_call(['hg', 'commit', '-m', 'merged heads'])
        except:
            print('Commit failed!')
            sys.exit(0)

        print('Successfully merged and committed %d heads.' % changeset_count)
