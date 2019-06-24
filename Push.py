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

from PyHg_lib import MyParser

#--------------------------------------------

class Push(object):
    def __init__(self, options):
        def get_changesets():
            command = ['hg', 'outgoing']
            output = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0].decode("utf-8")
            if ('no changes found' in output) or ('abort:' in output):
                return (None, None, None)

            changesets = []
            lines = output.split('\n')
            for line in lines:
                line = line.rstrip()
                if line.startswith('changeset:   '):
                    changesets.append(line[13:].strip())

            changeset_count = len(changesets)
            label = 'changesets' if changeset_count > 1 else 'changeset'
            return (changesets, changeset_count, label)

        if not os.path.exists('.hg'):
            print("ERROR: Must be in root of working copy to push.", file=sys.stderr)
            sys.exit(1)

        changeset_data = get_changesets()
        if changeset_data[0] is None:
            print("ERROR: No outgoing changesets found in this working copy.", file=sys.stderr)
            sys.exit(1)

        start_dir = os.getcwd()     # in case we push through the chain

        d = MyParser('.hg/hgrc').as_dict()
        if ('paths' not in d) or ('default' not in d['paths']):
            print("ERROR: No upstream repository has been defined.", file=sys.stderr)
        else:
            destination = d['paths']['default']

            print('Pushing %d %s to %s' % (changeset_data[1], changeset_data[2], destination))
            while True:
                command = ['hg', 'push']
                push_process = subprocess.Popen(command, stdout=subprocess.PIPE)
                output = push_process.communicate()[0].decode("utf-8")

                if push_process.returncode:
                    print("ERROR: Push operation failed with %d." % push_process.returncode, file=sys.stderr)
                    print(output, file=sys.stderr)
                    sys.exit(1)

                if (len(options.args) == 0) or \
                (not options.args[0].startswith('extern')) or \
                (not os.path.exists(destination)):
                    break

                os.chdir(destination)
                d = MyParser('.hg/hgrc').as_dict()
                destination = d['paths']['default']

                changeset_data = get_changesets()

                print('--> %d %s to %s' % (changeset_data[1], changeset_data[2], destination))

        os.chdir(start_dir)
