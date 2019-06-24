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
import time
import subprocess

from PyHg_lib import MyParser
from Incoming import Incoming

#--------------------------------------------

class Update(object):
    def __init__(self, options, and_pull=True):
        working_copies = ['.']

        if options.process_all:
            # look at each folder in the current folder, and determine:
            #    a. if it is a Mercurial folder
            #    b. the value of its 'default' in .hg/hgrc
            #    c. sync all 'off-world' folders first (those that don't have a valid local path)

            hg_folders = {}
            for entry in os.listdir('.'):
                hgrc = os.path.join(entry, '.hg', 'hgrc')
                if os.path.isdir(entry) and os.path.exists(hgrc):
                    d = MyParser(hgrc).as_dict()
                    dest = d['paths']['default']
                    hg_folders[entry] = dest
                    print('Found %s (%s)...' % (entry, dest))

            working_copies = []

            # non-local first
            for key in hg_folders.keys():
                dest = hg_folders[key]
                if not os.path.exists(dest):
                    working_copies.append(key)

            # then local
            for key in hg_folders.keys():
                dest = hg_folders[key]
                if os.path.exists(dest):
                    working_copies.append(key)

            if len(working_copies) == 0:
                print('No valid Mercurial working copies found under current folder!')
                sys.exit(0)

            print('')
        else:
            if options.branch == None:
                print('You must be in a valid Mercurial working folder!')
                sys.exit(0)

            if len(options.args):
                working_copies = []
                for arg in options.args:
                    if os.path.exists(arg):
                        working_copies.append(arg)

        start_dir = os.getcwd()

        for wc in working_copies:
            os.chdir(start_dir)
            os.chdir(wc)

            command = ['hg', 'root']
            output = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0].decode("utf-8")
            wc_root = output.split('\n')[0]

            command = ['hg', 'branch']
            output = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0].decode("utf-8")
            options.branch = output.split('\n')[0]
            if 'no repository found' in options.branch:
                options.branch = None

            if not options.branch:
                continue

            incoming = Incoming(options, database=True)
            log_text = incoming.format(Incoming.STYLE_PLAIN)

            if and_pull:
                command = ['hg', 'pull']
                output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")

            tally = []
            total_updated = 0
            total_merged = 0
            total_removed = 0
            total_unresolved = 0

            command = ['hg', 'update']
            output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
            lines = output.split('\n')
            for line in lines:
                if 'files updated' in line:
                    result = re.search('(\d+) files updated, (\d+) files merged, (\d+) files removed, (\d+) files unresolved', line)
                    if result:
                        if result.group(1) != '0':
                            total_updated = int(result.group(1))
                            tally.append('%s file%s updated.' % (total_updated, 's' if total_updated > 1 else ''))
                        if result.group(2) != '0':
                            total_merged = int(result.group(2))
                            tally.append('%s file%s merged.' % (total_merged, 's' if total_merged > 1 else ''))
                        if result.group(3) != '0':
                            total_removed = int(result.group(3))
                            tally.append('%s file%s removed.' % (total_removed, 's' if total_removed > 1 else ''))
                        if result.group(4) != '0':
                            total_unresolved = int(result.group(4))
                            tally.append('%s file%s unresolved.' % (total_unresolved, 's' if total_unresolved > 1 else ''))
                    break

            if len(tally) == 0:
                if wc == '.':
                    incoming.print_("No changes applied to working copy, branch")
                else:
                    incoming.print_("No changes applied to %s/, branch" % wc)
            else:
                if and_pull:
                    # get additional file details from locally known changesets
                    incoming.gather_file_details()

                print('[ %s:%s ]' % (wc, options.branch))
                incoming.print_()
                print('%s' % '\n'.join(tally))

            open(os.path.join(wc_root, 'sync.txt'), 'a').write('\n--[ UPDATE ]--------------\n%s\n\n%s\n' % \
                         (time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime()),\
                         '\n'.join(log_text)))
