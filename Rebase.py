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
import time
import subprocess

from Incoming import Incoming

#--------------------------------------------

class Rebase(object):
    def __init__(self, options):
        if not options.branch:
            return

        if (options.source_branch is None) or (len(options.source_branch) == 0):
            print("ERROR: Source branch name required for rebase", file=sys.stderr)
            sys.exit(1)

        command = ['hg', 'status', '-q', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        if len(output):
            print("ERROR: Working copy has uncommittted modifications", file=sys.stderr)
            sys.exit(1)

        if options.source_branch.startswith(options.branch) and (len(options.source_branch) > len(options.branch)):
            # they're merging upstream from a sub-branch.  make sure this is what
            # they want!
            if sys.version_info[0] > 2:
                approval = input('You are merging upstream.  Are you sure? (y/N) ')
            else:
                approval = raw_input('You are merging upstream.  Are you sure? (y/N) ')
            if (len(approval) == 0) or (approval.lower() == 'n'):
                return

        incoming = Incoming(options, command=['hg', 'merge', '-P', '-v', options.source_branch], database=True, ignore_branch=True)

        if len(incoming.changesets) > 0:
            log_text = incoming.format(Incoming.STYLE_PLAIN)
            command = ['hg', 'merge', options.source_branch]
            output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
            if not options.merge_only:
                msg = 'rebase with %s' % options.source_branch
                if hasattr(options, 'auth_token') and (options.auth_token is not None):
                    msg += ' (%s)' % options.auth_token
                command = ['hg', 'commit', '-m', msg]
                output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")

                open('sync.txt', 'a').write('\n--[ REBASE ]--------------\n%s\n\n%s\n' % \
                             (time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime()),\
                             '\n'.join(log_text)))
            else:
                open('sync.txt', 'a').write('\n--[ MERGE ]--------------\n%s\n\n%s\n' % \
                             (time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime()),\
                             '\n'.join(log_text)))

        incoming.print_()
