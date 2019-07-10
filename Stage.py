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
import uuid
import time
import shutil
import subprocess

try:
    import cPickle
except:
    import pickle as cPickle

import Info

from PyHg_lib import find_hg_root, fixup_renames, format_seconds

class StageEntry:
    __slots__ = ["version", "snapshot", "state"]
    def __init__ (self, snapshot=None, state=None):
        self.version = 1

        # if 'snapshot' is None, then this is a reference, otherwise it is the base name of the snapshot
        self.snapshot = snapshot

        # change state (modified or added; deleted cannot be snapshotted)
        self.state = state

    # def from_JSON(data):
    #     if 'snapshot' in data:
    #         self.snapshot = None if data['snapshot'] == 'None' else data['snapshot']
    #     if 'state' in data:
    #         self.state = None if data['state'] == 'None' else data['state']

    # def to_JSON():
    #     return "{ 'snapshot' : '%s', 'state' : '%s' }" % (str(self.snapshot), str(self.state))

#--------------------------------------------

class StageIO(object):
    def __init__(self):
        super(StageIO, self).__init__()

    def get_staging_root(self, root, options):
        staging_root = os.path.join(root, "stage")
        # this just complicates my life--not worth supporting.
        # for simplicity with the Shelf, staged metadata needs
        # to remain in proximity to the files it references...
        # if 'PYHG_STAGING_ROOT' in os.environ:
        #     staging_root = os.environ['PYHG_STAGING_ROOT']
        #     if not os.path.exists(staging_root):
        #         os.mkdir(staging_root)
        return staging_root

    def load_stage_db(self, stage_db_file):
        stage_db = {}
        try:
            with open(stage_db_file, 'rb') as f:
                stage_db = cPickle.load(f)
        except:
            pass
        return stage_db

    def save_stage_db(self, data, stage_db_file):
        if not os.path.exists(os.path.dirname(stage_db_file)):
            try:
                os.makedirs(os.path.dirname(stage_db_file))
            except:
                pass
        try:
            with open(stage_db_file, 'wb') as f:
                cPickle.dump(data, f, -1)
        except:
            return False
        return True

    def get_staged_entry_tag(self, stage_db_path, staged_entry, source_file):
        snap = ''
        if staged_entry.snapshot is None:
            snap = '&'
        else:
            snapshot_as_timestamp = False
            if 'PYHG_SNAPSHOT_AS_TIMESTAMP' in os.environ:
                snapshot_as_timestamp = (os.environ['PYHG_SNAPSHOT_AS_TIMESTAMP'] in ["1", "true", "True", "TRUE"])
            snapshot_path = os.path.join(stage_db_path, staged_entry.snapshot)
            snapshot_stat = os.stat(snapshot_path)
            snap = '='  # equivalent
            if snapshot_as_timestamp:
                snap = time.ctime(snapshot_stat.st_mtime)
            else:       # elapsed time
                source_stat = os.stat(source_file)
                if int(snapshot_stat.st_mtime) != int(source_stat.st_mtime):
                    # how old is it?
                    snap = format_seconds(int(source_stat.st_mtime) - int(snapshot_stat.st_mtime))
        return snap

class Stage(StageIO):
    def __init__(self, options):
        super(Stage, self).__init__()

        def generate_snapshot(options, stage_db_path, file_path, entry):
            if (entry is None) or (entry.snapshot is None):
               if (not options.snapshot) or (not os.path.exists(file_path)):
                    return StageEntry(None, entry.state)
            if entry.state != 'M':
                print("ERROR: Only (M)odified files can be captured by snapshot.", file=sys.stderr)
                sys.exit(1)
            ss = entry.snapshot
            if ss is None:
                ss = str(uuid.uuid4()).replace('-', '')
            snapshot_file_name = os.path.join(stage_db_path, ss)
            if os.path.exists(snapshot_file_name):
                os.remove(snapshot_file_name)   # we are refreshing the snapshot
            if not os.path.exists(stage_db_path):
                os.mkdir(stage_db_path)
            # use copy2() to make sure the snapshot shares the timestamp of
            # the source file at the time of creation
            shutil.copy2(file_path, snapshot_file_name)
            return StageEntry(ss, entry.state)

        if not options.branch:
            print('ERROR: Could not determine branch.', file=sys.stderr)
            sys.exit(1)

        root = find_hg_root()
        if root:
            os.chdir(root)
            os.chdir("..")

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            print('ERROR: Must be in root of working copy to stage.', file=sys.stderr)
            sys.exit(1)

        stage_name = "default" if options.stage_name is None else options.stage_name

        stage_db = {}
        stage_path = super(Stage, self).get_staging_root(root, options)
        if not os.path.exists(stage_path):
            os.mkdir(stage_path)
        stage_db_path = os.path.join(stage_path, stage_name)
        stage_db_file = os.path.join(stage_db_path, 'stage.db')
        if os.path.exists(stage_db_file):
            if options.erase_cache:
                print('All staged entries in "%s" cleared.' % stage_name)
                shutil.rmtree(stage_db_path)
            else:
                stage_db = super(Stage, self).load_stage_db(stage_db_file)

        if options.erase_cache:
            return  # nothing else to do

        if (len(options.args) == 0):
            capture_count = 0
            for key in stage_db:
                if stage_db[key].snapshot is not None:
                    capture_count += 1
            if capture_count:
                try:
                    print('You are about to refresh snapshot entries in the "%s" staging area.' % stage_name)
                    input('Press ENTER if this is the intent (or press Ctrl-C to abort):')
                except SyntaxError:
                    pass

        command = ['hg', 'status', '-q', '-C', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        output_lines = fixup_renames(output.split('\n'))

        lines = []
        if len(options.args):
            newlines = []
            # they are specifying files to be staged...filter 'lines'
            # based on them
            for item in options.args:
                found = -1
                for i in range(len(output_lines)):
                    if item in output_lines[i]:
                        newlines.append(output_lines[i][2:])
                        break

            if len(newlines) == 0:
                print("ERROR: Your specified filter(s) did not match any pending changes in the working copy.", file=sys.stderr)
                sys.exit(1)

            lines = newlines
        else:
            # strip off the status bit
            for i in range(len(output_lines)):
                lines.append(output_lines[i][2:])

        if len(lines) == 0:
            print("ERROR: No files have been selected for staging.", file=sys.stderr)
            sys.exit(1)

        # filter out duplicate entries
        status_db = {}
        for path in output_lines:
            key = path[2:].strip()
            status_db[key] = StageEntry(None, path[:1])

        added_files = []
        refreshed_files = []

        # all the files in lines[] are to be added to the staging database
        for path in lines:
            if path in stage_db:
                stage_db[path] = generate_snapshot(options, stage_db_path, path, stage_db[path])
                refreshed_files.append('%s %s' % (stage_db[path].state, path))
            else:
                for l in output_lines:
                    if path in l:
                        added_files.append(l)
                        break
                entry = StageEntry()
                if path in status_db:
                    entry = status_db[path]
                stage_db[path] = generate_snapshot(options, stage_db_path, path, entry)

        bad_keys = []
        for key in stage_db:
            if key not in status_db:
                # this file had been staged, but is now no longer modified
                bad_keys.append(key)

        for key in bad_keys:
            if stage_db[key].snapshot is not None:
                # it's a snapshot, delete it as well
                snapshot_file = os.path.join(stage_db_path, stage_db[key].snapshot)
                os.remove(snapshot_file)
            del status_db[key]

        # save the new database
        super(Stage, self).save_stage_db(stage_db, stage_db_file)

        if len(added_files) or len(refreshed_files):
            s = Info.Status()
            if len(added_files):
                print('The following new %s entries were added to the "%s" staging area:' % ('snapshot' if options.snapshot else 'reference', stage_name))
                s.process_lines(added_files, options)
            if len(refreshed_files):
                print('The following snapshot entries were refreshed in the "%s" staging area:' % stage_name)
                s.process_lines(refreshed_files, options)
        else:
            print('No unique entries were added to the "%s" staging area.' % stage_name)

class Unstage(StageIO):
    def __init__(self, options):
        super(Unstage, self).__init__()

        if not options.branch:
            print('ERROR: Could not determine branch.', file=sys.stderr)
            sys.exit(1)

        root = find_hg_root()
        if root:
            os.chdir(root)
            os.chdir("..")

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            print('ERROR: Must be in root of working copy to stage.', file=sys.stderr)
            sys.exit(1)

        stage_name = "default" if options.stage_name is None else options.stage_name

        stage_path = super(Unstage, self).get_staging_root(root, options)
        if not os.path.exists(stage_path):
            os.mkdir(stage_path)
        stage_db_path = os.path.join(stage_path, stage_name)
        stage_db_file = os.path.join(stage_db_path, 'stage.db')
        if not os.path.exists(stage_db_path):
            if options.erase_cache:
                return      # nothing more to do
            print('ERROR: No modifications are currently staged in "%s" for committing.' % stage_name, file=sys.stderr)
            sys.exit(1)

        if options.erase_cache:
            print('All entries in the "%s" staging area were cleared.' % stage_name)
            shutil.rmtree(stage_db_path)
            return

        if len(options.args) == 0:
            print('ERROR: No filter(s) specified for unstaging.', file=sys.stderr)
            sys.exit(1)

        stage_db = {}
        if os.path.exists(stage_db_file):
            stage_db = super(Unstage, self).load_stage_db(stage_db_file)

        command = ['hg', 'status', '-q', '-C', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        output_lines = fixup_renames(output.split('\n'))

        bad_keys = []
        for key in stage_db:
            for item in options.args:
                if item in key:
                    bad_keys.append(key)

        if len(bad_keys) == 0:
            print('ERROR: Your specified filter(s) did not match any entries in the "%s" staging area.' % stage_name, file=sys.stderr)
            sys.exit(1)

        unstaged_entries = []
        for key in bad_keys:
            for line in output_lines:
                if key in line:
                    unstaged_entries.append(line)

        for key in bad_keys:
            if stage_db[key].snapshot is not None:
                # it's a snapshot, delete it as well
                snapshot_file = os.path.join(stage_db_path, stage_db[key].snapshot)
                os.remove(snapshot_file)
            del stage_db[key]

        if len(stage_db) == 0:
            if os.path.exists(stage_db_path):
                shutil.rmtree(stage_db_path)
        else:
            # save the new database
            super(Unstage, self).save_stage_db(stage_db, stage_db_file)

            if len(unstaged_entries):
                print('The following existing entries were removed from the "%s" staging area:' % stage_name)
                s = Info.Status()
                s.process_lines(unstaged_entries, options)
            else:
                print('No unique entries were removed from the "%s" staging area.' % stage_name)

class Staged(StageIO):
    def __init__(self):
        super(Staged, self).__init__()

        self.message = None

    def execute(self, options, quiet=False, **kwargs):
        if not options.branch:
            self.message = 'ERROR: Could not determine branch.'
            return False

        staged_entries = self.get_staged_entries(options)
        if len(staged_entries):
            for stage in staged_entries:
                print('The following entries are pending in the "%s" staging area:' % stage)
                s = Info.Status()
                s.process_lines(staged_entries[stage], options)
        else:
            if self.message is None:
                self.message = 'No currently staged entries were found.'
            return False

        return True

    def cleanup(self, options, quiet=False):
        return True

    def get_staged_entries(self, options):
        working_dir = os.getcwd()

        root = find_hg_root()
        if root:
            os.chdir(root)
            os.chdir("..")

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            self.message = 'ERROR: Must be in root of working copy to stage.'
            return []

        command = ['hg', 'status', '-q', '-C', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        output_lines = fixup_renames(output.split('\n'))

        stage_name = options.stage_name

        self.stage_path = super(Staged, self).get_staging_root(root, options)
        if not os.path.exists(self.stage_path):
            os.mkdir(self.stage_path)
        stage_names = []
        if stage_name is None:
            # gather up all staging area names
            for entry in os.listdir(self.stage_path):
                stage_names.append(entry)
        else:
            stage_names.append(stage_name)
        staged_entries = {}
        for stage_name in stage_names:
            stage_db_path = os.path.join(self.stage_path, stage_name)
            stage_db_file = os.path.join(stage_db_path, 'stage.db')
            if not os.path.exists(stage_db_file):
                continue    # odd... should probably print a message

            stage_db = super(Staged, self).load_stage_db(stage_db_file)

            reference_count = 0
            capture_count = 0

            entries = []
            bad_keys = []
            for key in stage_db:
                staged_entry = stage_db[key]

                reference_count += 1 if staged_entry.snapshot is None else 0
                capture_count += 1 if staged_entry.snapshot is not None else 0

                found = False
                for line in output_lines:
                    if (key in line) or (staged_entry.snapshot is not None):
                        snapshot_path = None
                        snap = super(Staged, self).get_staged_entry_tag(stage_db_path, staged_entry, key)
                        entries.append('%s (%s)' % (line, snap))
                        found = True
                        break

                if not found:
                    if staged_entry.snapshot is None:
                        bad_keys.append(key)
                    else:
                        # note: snapshots are independent of the state of their source files
                        snap = super(Staged, self).get_staged_entry_tag(stage_db_path, staged_entry, key)
                        entries.append('%s %s (%s)' % (staged_entry.state, key, snap))

            if len(bad_keys):
                # all 'bad_keys' are references
                for key in bad_keys:
                    del stage_db[key]

            if len(stage_db):
                # save the corrected database
                super(Staged, self).save_stage_db(stage_db, stage_db_file)
                staged_entries[stage_name] = entries
            else:
                if (len(output_lines) == 0) and (reference_count != 0) and (capture_count == 0):
                    print('WARNING: Purging orphaned staging area "%s".' % stage_name)

                # if (len(output_lines) == 0) and (reference_count != 0) and (capture_count == 0):
                #     # orphaned references found
                #     os.chdir(working_dir)
                #     msg = 'ERROR: Orphaned reference entries found in the following staging areas:\n'
                #     for stage_name in stage_names:
                #         msg += '  [%s]\n' % stage_name
                #     msg += '\nUse "unstage --erase" to clear them.'
                #     self.message = msg
                #     return []

                if os.path.exists(stage_db_path):
                    shutil.rmtree(stage_db_path)

        os.chdir(working_dir)

        return staged_entries
