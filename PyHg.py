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
import struct
import tempfile
import atexit

from argparse import ArgumentParser
from PyHg_lib import format_seconds, Colors

#--------------------------------------------

class Options(object):
    def __init__(self):
        self.batch_file_name = ''

        if sys.platform == 'darwin':
            self.seven_zip = '7za'
        elif os.name == 'posix':
            self.seven_zip = '7za'
        elif os.name == 'nt':
            self.seven_zip = '7z'

        # see if we can find some fall-back merge tools already
        # available in the environment
        self.winmerge = ''
        self.diff = ''
        self.patch = ''

        if os.name == 'nt':
            for p in os.environ['PATH'].split(';'):
                if len(self.winmerge) == 0:
                    f = os.path.join(p, 'winmergeu.exe')
                    if os.path.exists(f):
                        self.winmerge = f
                if len(self.patch) == 0:
                    f = os.path.join(p, 'patch.exe')
                    if os.path.exists(f):
                        self.patch = f
                if len(self.diff) == 0:
                    f = os.path.join(p, 'diff.exe')
                    if os.path.exists(f):
                        self.diff = f

        # mercurial_config = ''
        # if os.name == 'nt':
        #     mercurial_config = os.path.join(os.environ['USERPROFILE'], 'mercurial.ini')
        # else:
        #     mercurial_config = os.path.join(os.environ['HOME'], '.hgrc')
        # if os.path.exists(mercurial_config):
        #     # see if we have a section in the the Mercurial config file
        #     # for the PYHG_ environment variable settings
        #     config = ConfigParser.RawConfigParser()
        #     config.read(mercurial_config)
        #     if config.has_section("hgsuite"):
        #         config_settings = config.items("hgsuite")

        # first, look at the action being executed.  we will customize
        # the options being parsed by the action

        cmd_set = ['update', 'commit', 'stage', 'unstage', 'staged', 'incoming',
                   'status', 'log', 'rebase', 'shelve', 'shelved', 'restore', #'backup',
                   'conflicts', 'push', 'mergeheads', 'diff', 'switch']
        StageIO_dependents = ['stage', 'unstage', 'staged', 'commit', 'status', 'shelve', 'restore']

        self.action = None
        if sys.argv[1] in cmd_set:
            self.action = sys.argv[1]
            del sys.argv[1]     # remove it so positional arguments don't get confused
        else:
            print("ERROR: Unknown action:", sys.argv[1], file=sys.stderr)
            sys.exit(1)

        # now process any command-line options for the current action

        parser = ArgumentParser(description="Hg Suite", prog=self.action)
        parser.add_argument("-B", "--use-batch", dest="ansi_color_requires_batch", default=((os.name == 'nt') and ('CMDER_ROOT' not in os.environ)), type=bool, help="Run output through a batch file for ANSI processing.")
        if self.action == 'log':
            parser.add_argument("-l", "--limit", dest="log_limit", default=0, help="Limit the number of log entries displayed.")
            parser.add_argument("-r", "--revision", dest="log_rev", default='', help="Display log info for the specified changeset revision.")
            parser.add_argument("-u", "--user", dest="log_user", default='', help="Display log info for changes applied by a specific user.")
            parser.add_argument("-b", "--branch", dest="log_branch", default='', help="Display log info for the specified branch.")
            parser.add_argument("-d", "--date", dest="log_date", default='', help="Select revisions matching the provided date spec.")
            parser.add_argument("-k", "--keyword", dest="log_keyword", default='', help="Select revisions containing the case-insensitive text.")
            parser.add_argument("-M", "--no-merges", dest="log_no_merges", action="store_true", default=False, help="Exclude revisions that are merges.")
            parser.add_argument("-T", "--template", dest="log_template", default='', help="Display with template.")
            parser.add_argument("-v", "--verbose", dest="detailed", action="store_true", default=False, help="Include as much detail as possible.")
        else:
            # many commands are dependent on this
            if self.action in StageIO_dependents:
                parser.add_argument("-s", "--stage-name", dest="stage_name", default=None, help="Specify the default staging area to use.")

            if self.action == 'commit':
                parser.add_argument("-l", "--log", dest="log_file", default=None, help="Use the specified text file as the commit log.")
                parser.add_argument("-m", "--message", dest="commit_message", default=None, help="Enter a message for use by the command.")
                parser.add_argument("-w", "--wrap", dest="wrap_at", default=80, help="Set the column offset for wrapping log text.")
                parser.add_argument("-P", "--push", action="store_true", dest="push_changes", default=False, help="Push committed changes upstream.")
                parser.add_argument("-x", "--pushex", action="store_true", dest="push_external", default=False, help="Push committed changes to an external destination.")
                parser.add_argument("-A", "--authtoken", dest="auth_token", default=None, help="Insert an authorization token for the commit.")

            # 'switch' may invoke 'shelve', so pass along a subset of its options
            if ('shelve' in self.action) or (self.action == 'switch'):
                parser.add_argument('shelf_name', metavar='MICROBRANCH', default='', nargs='?', help='Optional microbranch id for the operation.')
                parser.add_argument("-n", "--no-revert", dest="no_revert", action="store_true", default=False, help="Bypass any implicit reverting of changes in the working copy.")
                parser.add_argument("-c", "--comment", dest="comment", default='', help="Provide a comment for shelved microbranch.")
                parser.add_argument("-p", "--path", dest="use_path", default=".", help="Specify a path on which to operate.")
                parser.add_argument("-i", "--include", dest="include_filter", default=None, help="Specify a filter value to include detected modifications.")
                parser.add_argument("-X", "--exclude", action="append", dest="exclude_filter", default=[], help="Specify a filter value to exclude detected modifications.")
                parser.add_argument("-r", "--extra", dest="extra_files", action="append", default=[], help="Specify additional, non-managed files to be processed.")
                parser.add_argument("-V", "--ide-state", dest="ide_state", action="store_true", default=False, help="When shelving, save the current state of the Visual Studio IDE for all defined solutions.")
                if self.action == 'shelved':
                    parser.add_argument("-v", "--verbose", dest="detailed", action="store_true", default=False, help="Include as much detail as possible.")

            if self.action == 'restore':
                parser.add_argument('shelf_name', metavar='MICROBRANCH', type=str, default='', nargs='?', help='Optional source microbranch for the restore operation.')
                parser.add_argument("-o", "--overwrite", action="store_true", dest="overwrite", default=False, help="Force replacement of modified destination (no merge check).")
                parser.add_argument("-e", "--erase", action="store_true", dest="erase_cache", help="Erase any cache the command may have available or may have created.")

            if self.action == 'rebase':
                parser.add_argument('source_branch', metavar='BRANCH', type=str, help='Required source branch for the rebase operation.')
                parser.add_argument("-M", "--mergeonly", action="store_true", dest="merge_only", default=False, help="Skip the final commit step in a rebase operation.")

            if 'stage' in self.action:
                if self.action == 'stage':
                    parser.add_argument("-S", "--snapshot", dest="snapshot", action="store_true", default=False, help="Perform an action that is time-based.")
                if (self.action == 'stage') or (self.action == 'unstage'):
                    parser.add_argument("-e", "--erase", action="store_true", dest="erase_cache", help="Erase any cache the command may have available or may have created.")

            if (self.action == 'update') or (self.action == 'status'):
                parser.add_argument("-a", "--process-all", action="store_true", dest="process_all", default=False, help="Process all in commands that have multiple processing options available.")

        options, args = parser.parse_known_args()

        # config options that can be overridden by the user

        # use ANSI terminal color codes?
        self.ansi_color = True # options.ansi_color

        # will the interpreter only process color codes from a batch file?
        self.ansi_color_requires_batch = options.ansi_color_requires_batch

        if self.action == 'log':
            self.log_limit = options.log_limit
            self.log_rev = options.log_rev
            self.detailed = options.detailed
            self.log_user = options.log_user
            self.log_branch = options.log_branch
            self.log_date = options.log_date
            self.log_keyword = options.log_keyword
            self.log_no_merges = options.log_no_merges
            self.log_template = options.log_template
        else:
            if self.action == 'commit':
                self.log_file = None
                if options.log_file and os.path.exists(options.log_file):
                    self.log_file = options.log_file
                self.commit_message = None
                if options.commit_message:
                    self.commit_message = options.commit_message
                self.wrap_at = options.wrap_at
                self.push_external = options.push_external
                self.push_changes = True if options.push_external else options.push_changes
                self.auth_token = options.auth_token

            if ('shelve' in self.action) or (self.action == 'switch'):
                self.shelf_name = options.shelf_name
                self.no_revert  = options.no_revert
                self.comment = options.comment
                self.use_path = options.use_path
                self.include_filter = options.include_filter
                self.exclude_filter = options.exclude_filter
                self.extra_files = options.extra_files
                self.ide_state = options.ide_state
                if self.action == 'shelved':
                    self.detailed = options.detailed

            if self.action == 'restore':
                self.overwrite = options.overwrite
                self.erase_cache = options.erase_cache
                self.shelf_name = options.shelf_name

            if self.action == 'rebase':
                self.source_branch = options.source_branch
                self.merge_only = options.merge_only

            if 'stage' in self.action:
                if self.action == 'stage':
                    self.snapshot = options.snapshot
                if (self.action == 'stage') or (self.action == 'unstage'):
                    self.erase_cache = options.erase_cache

            if (self.action == 'update') or (self.action == 'status'):
                self.process_all = options.process_all

            if self.action in StageIO_dependents:
                self.stage_name = options.stage_name

        # gather some information about the Mercurial working copy

        command = ['hg', 'branch']
        output = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0].decode("utf-8")
        self.branch = output.split('\n')[0]
        if 'no repository found' in self.branch:
            self.branch = None

        self.args = args

        # generate a batch file name for global use
        if os.name == 'nt':
            (_file, _file_name) = tempfile.mkstemp(text=True, suffix='.bat')
        else:
            (_file, _file_name) = tempfile.mkstemp(text=True, suffix='.sh')
        os.close(_file)
        self.batch_file_name = _file_name

        self.working_dir = os.getcwd()

        atexit.register(self.cleanup)

    def cleanup(self):
        if len(self.batch_file_name) and os.path.exists(self.batch_file_name):
            os.remove(self.batch_file_name)

if __name__ == "__main__":
    options = Options()

    if options.action not in 'update|status|shelved':
        if (options.branch == None) and (len(options.args) == 0):
            print('You must be in a valid Mercurial working folder!')
            sys.exit(0)

    if not options.action:
        print('Nothing to do!  Please specify an action.')
        sys.exit(0)

    result = 0
    pyhg_action = None

    if options.action == 'update':
        from Update import Update
        Update(options)
    elif options.action == 'status':
        from Info import Status
        pyhg_action = Status()
    elif options.action == 'log':
        from Info import Log
        Log(options)
    elif options.action == 'incoming':
        from Incoming import Incoming
        Incoming(options)
    elif options.action == 'commit':
        from Commit import Commit
        Commit(options)
    elif options.action == 'stage':
        from Stage import Stage
        Stage(options)
    elif options.action == 'unstage':
        from Stage import Unstage
        Unstage(options)
    elif options.action == 'staged':
        from Stage import Staged
        pyhg_action = Staged()
    elif options.action == 'rebase':
        from Rebase import Rebase
        Rebase(options)
    # elif options.action == 'backup':
    #     from Backup import Backup
    #     Backup(options)
    elif options.action == 'shelve':
        from Shelf import Shelve
        pyhg_action = Shelve()
    elif options.action == 'shelved':
        from Shelf import Shelved
        pyhg_action = Shelved()
    elif options.action == 'restore':
        from Shelf import Restore
        pyhg_action = Restore()
    elif options.action == 'conflicts':
        from Shelf import Conflicts
        Conflicts(options)
    elif options.action == 'push':
        from Push import Push
        Push(options)
    elif options.action == 'mergeheads':
        from MergeHeads import MergeHeads
        MergeHeads(options)
    elif options.action == 'diff':
        from Diff import Diff
        Diff(options)
    elif options.action == 'switch':
        from Switch import Switch
        pyhg_action = Switch()

    if pyhg_action:
        if not pyhg_action.execute(options):
            print(pyhg_action.message, file=sys.stderr)
            result = 1
        else:
            if not pyhg_action.cleanup(options):
                print(pyhg_action.message, file=sys.stderr)
                result = 1

    if os.name != 'nt':
        # reset the console colors to defaults
        print(Colors['Reset'])

    sys.exit(result)
