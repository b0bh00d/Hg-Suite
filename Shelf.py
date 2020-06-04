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
This module implements the 'microbranches' toolset.  It takes the current
modifications in a working directory and 'archives' them for later retrieval
(by the Restore command).

These archives are rolled, so a history is maintained.

Additionally, these microbranch archives can be stored anywhere on system,
allowing them to be synchronized with other machines (e.g., transfer
work-in-progress changes between Windows, OS X and Linux for testing without
explicit commits).
"""

import sys
import os
import time
import glob
import hashlib
try:
    from urllib.parse import quote
    from urllib.parse import unquote
except ImportError:
    from urllib import quote
    from urllib import unquote
import shutil
import tempfile
import subprocess

from Action import Action
from PyHg_lib import MANIFEST_VERSION, \
                     colorize_status, \
                     get_changeset_for, \
                     find_hg_root, \
                     find_mb_root, \
                     fixup_renames, \
                     determine_line_endings, \
                     fix_line_endings, \
                     make_path, \
                     crc32
from Commit import StageEntry, StageIO

#--------------------------------------------

class Shelve(Action):
    def __init__(self):
        super(Shelve, self).__init__()

    def execute(self, options, quiet=False, **kwargs):
        if not options.branch:
            self.message = 'ERROR: Could not determine branch.'
            return False

        working_dir = os.getcwd()

        root = find_hg_root()
        if root:
            os.chdir(root)
            os.chdir("..")

        stage_path = StageIO().get_staging_root(root, options)
        if os.path.exists(stage_path):
            stages = os.listdir(stage_path)
            stage_path = os.path.join(".hg", "stage") if len(stages) != 0 else None
        else:
            stage_path = None

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            self.message = 'ERROR: Must be in root of working copy to shelf.'
            return False

        command = ['hg', 'status', '-q', '-C']
        if (options.include_filter is None) and (len(options.exclude_filter) == 0):
            command.append(options.use_path)

        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        if len(output) > 0:
            lines = fixup_renames(output.split('\n'))

            shelf_name = 'shelf'
            if len(options.shelf_name) != 0:
                shelf_name = options.shelf_name
            shelf_name_unquoted = shelf_name
            shelf_name = quote(shelf_name,'')

            if 'mb_root' in kwargs:
                root = kwargs['mb_root']
            else:
                root = find_mb_root()   # this will not return if we can't find a working location

            manifest_version = 0
            manifest = []
            manifest_name = os.path.join(root, '%s.manifest' % shelf_name)
            manifest_archive = os.path.join(root, '%s.7z' % shelf_name)
            manifest_comment = ''

            timestamp = hex(int(time.time()))[2:]
            if os.path.exists(manifest_name):
                # grab the previous comment
                manifest_lines = open(manifest_name).readlines()
                if manifest_lines[0].startswith('version '):
                    manifest_version = int(manifest_lines[0][8:])
                    if manifest_version >= 1:
                        manifest_comment = manifest_lines[1].rstrip()
                else:
                    manifest_comment = manifest_lines[0].rstrip()
                manifest_lines = None
                try:
                    os.rename(manifest_name, '%s.%s' % (manifest_name, timestamp))
                except:
                    os.chdir(working_dir)
                    self.message = 'ERROR: Could not back up previous shelf.'
                    return False
            if os.path.exists(manifest_archive):
                try:
                    os.rename(manifest_archive, '%s.%s' % (manifest_archive, timestamp))
                except:
                    os.chdir(working_dir)
                    self.message = 'ERROR: Could not back up previous shelf.'
                    return False

            if len(options.comment):
                manifest_comment = options.comment

            shelve_command = [options.seven_zip, 'a', manifest_archive, '@%s.list' % shelf_name]

            for line in lines:
                line = line.strip()
                if not len(line):
                    continue

                if (options.include_filter is not None) or len(options.exclude_filter):
                    if options.include_filter is not None:
                        if options.include_filter in line:
                            manifest.append(line)
                    if len(options.exclude_filter):
                        exclude = [f for f in options.exclude_filter if f in line]
                        if len(exclude) == 0:
                            manifest.append(line)
                else:
                    manifest.append(line)

            if options.ide_state:
                # find all the .suo files and add them to the archive
                # (the Visual Studio .suo file maintains a record of all files that
                # were last open in the IDE)
                if os.path.exists('.vs'):       # VS2017+
                    for root, dirs, files in os.walk('.vs'):
                        if '.suo' in files:
                            manifest.append('X %s' % os.path.join(root, '.suo'))
                            options.extra_files.append(os.path.join(root, '.suo'))
                else:                           # +VS2013
                    files = glob.glob('*.suo')
                    if len(files):
                        options.extra_files += files
                        for file in files:
                            manifest.append('X %s' % file)

            lines_written = 0
            with open('%s.list' % shelf_name, 'w') as f:
                if stage_path is not None:
                    f.write('%s\n' % stage_path)    # capture current staging metadata
                if isinstance(options.extra_files, (list, tuple)) and len(options.extra_files):
                    # should be a path relative to the root of the working copy
                    f.write('%s\n' % '\n'.join(options.extra_files))
                for line in manifest:
                    action = line[0]
                    if action == 'M' or action == 'A':
                        f.write('%s\n' % line[2:])
                        lines_written += 1
                    if action == 'V':
                        # rename; place the current file into the backup in case it holds changes
                        f.write('%s\n' % line[2:].split(',')[1])
                        lines_written += 1

            if lines_written:
                output = subprocess.Popen(shelve_command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                lines = output.split('\n')

                something_went_wrong = True
                for line in lines:
                    line = line.rstrip()
                    if line == 'Everything is Ok':
                        something_went_wrong = False
                        break

                if something_went_wrong:
                    os.chdir(working_dir)
                    self.message = 'ERROR: Failed to construct shelf archive:\n%s' % output
                    return False

            os.remove('%s.list' % shelf_name)

            if (options.include_filter is not None) or len(options.exclude_filter):
                for line in manifest:
                    action = line[0]
                    filename = line[2:]
                    if action == 'V':
                        filename =  line[2:].split(',')[1]
                    command = ['hg', 'revert', filename]
                    output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
            elif not options.no_revert:
                command = ['hg', 'revert', '--all']
                if options.use_path != '.':
                    command.append(options.use_path)
                output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                if stage_path is not None:
                    shutil.rmtree(stage_path)   # remove current staging metadata

            with open(manifest_name, 'w') as f:
                f.write('version %d\n' % MANIFEST_VERSION)
                f.write('%s\n' % manifest_comment)
                for line in manifest:
                    action = line[0]
                    if os.name == 'nt':
                        file_name = line[2:].replace('/', '\\')
                    else:
                        file_name = line[2:].replace('\\', '/')
                    #timestamp = 0.0
                    changeset = ''

                    if action == 'M':
                        changeset = hashlib.md5(open(file_name,'rb').read()).hexdigest()

                    elif action == 'V':
                        # the revert above may have left the renamed file in place
                        # we are nice, and clean it up for them...
                        from_name, to_name = file_name.split(',')
                        if os.path.exists(to_name):
                            try:
                                os.remove(to_name)
                            except:
                                self.message = 'ERROR: Failed to remove renamed file "%s"!' % to_name
                                return False

                        changeset = hashlib.md5(open(from_name,'rb').read()).hexdigest()

                    f.write('%s?%s?%s\n' % (action, file_name, changeset))

            batch_text = ''
            if os.name == 'nt':
                batch_text = '@echo off\n'
                batch_text += 'set FG=%_fg\n'
                batch_text += 'set BG=%_bg\n'

            manifest = colorize_status(manifest)

            if not quiet:
                print('Shelved the following state as microbranch "%s":' % shelf_name_unquoted)
                for line in manifest:
                    if options.ansi_color:
                        if options.ansi_color_requires_batch:
                            batch_text += 'echo %s\n' % line[3]
                        else:
                            print(line[3])
                    else:
                        print(line[0], line[1])

                if options.ansi_color:
                    if options.ansi_color_requires_batch:
                        if os.name == 'nt':
                            batch_text += 'color %FG on %BG\n'
                        open(options.batch_file_name, 'w').write(batch_text)
                        os.system(options.batch_file_name)
                if options.no_revert:
                    print('\nAs requested, changes have been left in the working copy.')
        else:
            if not quiet:
                print('Nothing to shelve.')

        os.chdir(working_dir)
        return True

    def cleanup(self, options, quiet=False):
        return True

"""
This module is part of the 'microbranches' toolset (the others being Restore and Shelve).
It displays the currently archived microbranches within the working directory.
"""

class Shelved(Action):
    def __init__(self):
        super(Shelved, self).__init__()

    def execute(self, options, quiet=False, **kwargs):
        working_dir = os.getcwd()

        root = find_hg_root()
        if root:
            # set working directory to the top of the working copy
            os.chdir(root)
            os.chdir("..")

        root = find_mb_root()   # this will not return if we can't find a working location

        shelf_name = None
        if len(options.shelf_name) != 0:
            shelf_name = quote(options.shelf_name,'')

        import glob
        files = glob.glob(os.path.join(root,'*.manifest'))
        if len(files) == 0:
            if not quiet:
                print('No microbranches are currently shelved.')
        else:
            if not shelf_name:
                if not quiet:
                    print('The following microbranches are on the shelf:')

            for file in files:
                microbranch_name = os.path.basename(file).split('.')[0]
                if shelf_name and shelf_name != microbranch_name:
                    continue

                if shelf_name and options.detailed:
                    if not quiet:
                        print('Microbranch "%s" caches the following changes:' % options.args[0])

                manifest_file = file
                manifest_lines = open(manifest_file).readlines()
                if manifest_lines[0].startswith('version '):
                    manifest_version = int(manifest_lines[0][8:])
                    del manifest_lines[0]
                    if manifest_version == 1:
                        manifest_comment = manifest_lines[0].rstrip()
                else:
                    manifest_comment = manifest_lines[0].rstrip()
                del manifest_lines[0]

                if not quiet:
                    if len(manifest_comment):
                        print('  "%s" (%s)' % (microbranch_name, manifest_comment))
                    else:
                        print('  "%s"' % microbranch_name)

                    if options.detailed:
                        for line in manifest_lines:
                            line = line.rstrip()
                            items = line.split('?')
                            print('     %s -> %s' % (items[0], items[1]))

        os.chdir(working_dir)
        return True

    def cleanup(self, options, quiet=False):
        return True

"""
This module is part of the 'microbranches' toolset (the others being Shelve and Shelved).
It re-applies the changes contained within a specified microbranch to the current working
directory.

It will invoke WinMerge to apply the changes per-file if the modification dates differ,
unless the 'overwrite' flag is specified (in which case, it will simply overwrite the
target file).
"""

class Restore(Action):
    def __init__(self):
        super(Restore, self).__init__()

        self.mb_root = None

    def execute(self, options, quiet=False, **kwargs):
        abort_cleanups = []
        def abort_cleanup(cleanups):
            for cleanup in cleanups:
                cleanup()

        if not options.branch:
            self.message = 'ERROR: Could not determine branch.'
            return False

        shelf_name = 'shelf'
        if len(options.shelf_name) != 0:
            shelf_name = options.shelf_name

        shelf_name_unquoted = shelf_name
        shelf_name = quote(shelf_name,'')

        working_dir = os.getcwd()

        root = find_hg_root()
        if root:
            os.chdir(root)
            os.chdir("..")

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            self.message = 'ERROR: Must be in root of working copy to restore.'
            return False

        if 'mb_root' in kwargs:
            self.mb_root = kwargs['mb_root']
        else:
            self.mb_root = find_mb_root()   # this will not return if we can't find a working location

        if not os.path.exists(os.path.join(self.mb_root, '%s.manifest' % shelf_name)):
            os.chdir(working_dir)
            self.message = 'ERROR: A valid shelf state could not be found.'
            return False

        command = ['hg', 'status', '-q', '.']
        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        if len(output) != 0:
            os.chdir(working_dir)
            self.message = 'Cannot restore into pending changes.'
            return False

        working_folder = os.path.join(tempfile.gettempdir(), '__%s__' % shelf_name)
        if os.path.exists(working_folder):
            try:
                shutil.rmtree(working_folder)
            except:
                os.chdir(working_dir)
                self.message = 'ERROR: Failed to remove remnants of previous restore atttempt.'
                return False

        manifest_name = os.path.join(self.mb_root, '%s.manifest' % shelf_name)
        manifest_archive = os.path.join(self.mb_root, '%s.7z' % shelf_name)

        if not os.path.exists(manifest_archive):
            os.chdir(working_dir)
            self.message = 'ERROR: The specified microbranch "%s" does not exist.' % shelf_name
            return False

        restore_command = [options.seven_zip, 'x', '-o%s' % working_folder, manifest_archive]
        output = subprocess.Popen(restore_command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        lines = output.split('\n')

        something_went_wrong = True
        for line in lines:
            line = line.rstrip()
            if line == 'Everything is Ok':
                something_went_wrong = False
                break

        if something_went_wrong:
            os.chdir(working_dir)
            self.message = 'ERROR: Failed to extract shelf archive:\n%s' % output
            return False

        # does this archive contain any staging areas?  it won't be in the
        # archive unless it has staging areas
        shelved_stage = os.path.join(working_folder, '.hg', 'stage')
        stage_path = StageIO().get_staging_root(root, options)
        if os.path.exists(shelved_stage):
            # ok, check to make sure there isn't one lingering
            if os.path.exists(stage_path):
                stage_areas = os.listdir(stage_path)
                if len(stage_areas) != 0:
                    # we have to abort; cleanup() will remove the working_folder
                    os.chdir(working_dir)
                    self.message = 'ERROR: Active staging areas found; cannot overwrite with shelved version'
                    return False
                shutil.rmtree(stage_path)
            shutil.copytree(shelved_stage, stage_path)
            abort_cleanups.append(lambda: shutil.rmtree(stage_path))
        else:
            shelved_stage = None

        manifest_version = 0
        manifest_lines = open(manifest_name).readlines()
        if manifest_lines[0].startswith('version '):
            manifest_version = int(manifest_lines[0][8:])
            del manifest_lines[0]
            if manifest_version >= 1:
                manifest_comment = manifest_lines[1].rstrip()
            del manifest_lines[0]
        else:
            manifest_comment = manifest_lines[0].rstrip()
            del manifest_lines[0]

        abort_cleanups.append(lambda: subprocess.check_output(['hg', 'revert', '--all']))
        abort_cleanups.append(lambda: os.chdir(working_dir))

        merge_status = {}
        add_status = {}
        for line in manifest_lines:
            line = line.rstrip()
            status, file_name, previous_key = line.split('?')  # 'previous_key' will be an md5 hash starting with MANIFEST_VERSION 2
            if os.name == 'nt':
                file_name = file_name.replace('/', '\\')
            else:
                file_name = file_name.replace('\\', '/')
            if status == 'A':
                if os.path.exists(file_name):
                    output = subprocess.Popen(['hg', 'add', file_name], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                    if not len(output):
                        add_status[file_name] = True
                        if not quiet:
                            print('.', end='')
                    else:
                        abort_cleanup(abort_cleanups)
                        self.message = 'ERROR: Failed to restore added file "%s":\n%s\n...aborting restore...' % (file_name, output)
                        return False
                else:
                    if not os.path.exists(os.path.join(working_folder, file_name)):
                        add_status[file_name] = False
                        if not quiet:
                            print("WARNING: Added file '%s' no longer exists; skipping..." % file_name, file=sys.stderr)
                    else:
                        if not make_path(file_name):
                            abort_cleanup(abort_cleanups)
                            self.message = 'ERROR: Failed to recreate path for added file "%s"; aborting restore...' % file_name
                            return False
                        try:
                            shutil.copyfile(os.path.join(working_folder, file_name), file_name)
                            if not quiet:
                                print('.', end='')
                        except:
                            abort_cleanup(abort_cleanups)
                            self.message = 'ERROR: Failed to restore added file "%s"; aborting restore...' % file_name
                            return False
                    output = subprocess.Popen(['hg', 'add', file_name], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                    if not len(output):
                        add_status[file_name] = True
                        if not quiet:
                            print('.', end='')
                    else:
                        abort_cleanup(abort_cleanups)
                        self.message = 'ERROR: Failed to restore added file "%s":\n%s\n...aborting restore...' % (file_name, output)
                        return False

            elif status == 'M':
                files_are_equal = False
                # see if the file is unchanged by the merge; in that case, just copy it
                if manifest_version <= 1:
                    new_key = get_changeset_for(options, file_name)
                    if not new_key:
                        if shelved_stage is not None:
                            shutil.rmtree(stage_path)
                        os.chdir(working_dir)
                        self.message = 'ERROR: Failed to determine changeset for file "%s".' % file_name
                        return False

                    old_crc32 = crc32(os.path.join(working_folder, file_name))
                    new_crc32 = crc32(file_name)

                    files_are_equal = (previous_key == new_key) and (old_crc32 == new_crc32)
                else:
                    # make sure the target file hasn't changed since we last shelved
                    new_key = hashlib.md5(open(file_name,'rb').read()).hexdigest()
                    files_are_equal = new_key == previous_key

                if options.overwrite or files_are_equal:
                    try:
                        shutil.copyfile(os.path.join(working_folder, file_name), file_name)
                        if not quiet:
                            print('.', end='')
                    except:
                        abort_cleanup(abort_cleanups)
                        self.message = 'ERROR: Failed to restore modified file "%s":\n...aborting restore...' % file_name
                        return False
                else:
                    # the file has been altered, so we have to merge...see what we have available
                    merge_tool = ''
                    if 'PYHG_MERGE_TOOL' in os.environ:
                        merge_tool = os.environ['PYHG_MERGE_TOOL']
                    elif os.name == 'nt':
                        if len(options.winmerge):
                            merge_tool = options.winmerge
                        elif len(options.patch):
                            merge_tool = options.patch
                        elif len(options.diff):
                            merge_tool = options.diff
                    if len(merge_tool):
                        previous_key = hashlib.md5(open(os.path.join(working_folder, file_name),'rb').read()).hexdigest()
                        os.system('%s "%s" "%s"' % (merge_tool, os.path.join(working_folder, file_name), file_name))
                        new_key = hashlib.md5(open(os.path.join(working_folder, file_name),'rb').read()).hexdigest()
                        merge_status[file_name] = (previous_key != new_key)
                        if previous_key != new_key:
                            try:
                                shutil.copyfile(os.path.join(working_folder, file_name), file_name)
                                if not quiet:
                                    print('.', end='')
                            except:
                                abort_cleanup(abort_cleanups)
                                self.message = 'ERROR: Failed to restore merged file "%s":\n...aborting restore...' % file_name
                                return False
                        else:
                            print("WARNING: Skipping '%s'; no merge performed..." % file_name, file=sys.stderr)
                    else:
                        if not quiet:
                            print("WARNING: Skipping '%s'; no merge solution available..." % file_name, file=sys.stderr)

            elif status == 'R':
                if os.path.exists(file_name):
                    output = subprocess.Popen(['hg', 'remove', file_name], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                if len(output):
                    abort_cleanup(abort_cleanups)
                    self.message = 'ERROR: Failed to remove file "%s":\n%s\n...aborting restore...' % (file_name, output)
                    return False
                else:
                    if not quiet:
                        print('.', end='')

            elif status == 'V':
                # rename
                output = ''
                from_name, to_name = file_name.split(',')

                # first, perform a 'move' (i.e., rename) on the existing file
                if os.path.exists(from_name):
                    output = subprocess.Popen(['hg', 'mv', from_name, to_name], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                if len(output):
                    abort_cleanup(abort_cleanups)
                    self.message = 'ERROR: Failed to rename file "%s":\n%s\n...aborting restore...' % (from_name, output)
                    return False

                # next, copy the contents of the archived version if it differs
                files_are_equal = False
                if manifest_version <= 1:
                    old_crc32 = crc32(os.path.join(working_folder, to_name))
                    new_crc32 = crc32(to_name)
                    files_are_equal = (previous_key == new_key) and (old_crc32 == new_crc32)
                else:
                    new_key = hashlib.md5(open(to_name,'rb').read()).hexdigest()
                    files_are_equal = new_key == previous_key

                if options.overwrite or files_are_equal:
                    try:
                        shutil.copyfile(os.path.join(working_folder, to_name), to_name)
                        if not quiet:
                            print('.', end='')
                    except:
                        abort_cleanup(abort_cleanups)
                        self.message = 'ERROR: Failed to restore renamed file "%s":\n...aborting restore...' % to_name
                        return False
                else:
                    # the file has been altered, so we have to merge...see what we have available
                    merge_tool = ''
                    if 'PYHG_MERGE_TOOL' in os.environ:
                        merge_tool = os.environ['PYHG_MERGE_TOOL']
                    elif os.name == 'nt':
                        if len(options.winmerge):
                            merge_tool = options.winmerge
                        elif len(options.patch):
                            merge_tool = options.patch
                        elif len(options.diff):
                            merge_tool = options.diff
                    if len(merge_tool):
                        previous_key = hashlib.md5(open(os.path.join(working_folder, to_name),'rb').read()).hexdigest()
                        os.system('%s "%s" "%s"' % (merge_tool, os.path.join(working_folder, to_name), to_name))
                        new_key = hashlib.md5(open(os.path.join(working_folder, to_name),'rb').read()).hexdigest()
                        merge_status[file_name] = (previous_key != new_key)
                        if previous_key != new_key:
                            try:
                                shutil.copyfile(os.path.join(working_folder, to_name), to_name)
                                if not quiet:
                                    print('.', end='')
                            except:
                                abort_cleanup(abort_cleanups)
                                self.message = 'ERROR: Failed to restore merged file "%s":\n...aborting restore...' % file_name
                                return False
                        else:
                            print("WARNING: Skipping '%s'; no merge performed..." % file_name, file=sys.stderr)
                    else:
                        if not quiet:
                            print("WARNING: Skipping '%s'; no merge solution available..." % file_name, file=sys.stderr)

            elif status == 'X':
                # extra file -- just put it back where it was exactly as it was, no additional handling
                if os.path.exists(file_name):
                    try:
                        os.remove(file_name)
                    except:
                        abort_cleanup(abort_cleanups)
                        self.message = 'ERROR: Failed to remove extra file "%s":\n...aborting restore...' % file_name
                        return False

                restore_command = [options.seven_zip, 'x', manifest_archive, file_name]
                try:
                    output = subprocess.Popen(restore_command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                except:
                    abort_cleanup(abort_cleanups)
                    self.message = 'ERROR: Failed to restore extra file "%s":\n...aborting restore...' % file_name
                    return False

                something_went_wrong = True
                for line in output.split('\n'):
                    line = line.rstrip()
                    if line == 'Everything is Ok':
                        something_went_wrong = False
                        break

                if something_went_wrong:
                    abort_cleanup(abort_cleanups)
                    self.message = 'ERROR: Failed to restore extra file "%s":\n...aborting restore...' % file_name
                    return False

                if not quiet:
                    print('.', end='')

        if not quiet:
            for i in range(len(manifest_lines)):
                line = manifest_lines[i].rstrip()
                #status, file_name, timestamp = line.split(':')
                status, file_name, changeset = line.split('?')
                manifest_lines[i] = '%s %s' % (status, file_name)
                if file_name in merge_status:
                    if not merge_status[file_name]:
                        manifest_lines[i] = '? %s' % file_name
                elif file_name in add_status:
                    if not add_status[file_name]:
                        manifest_lines[i] = '? %s' % file_name

            batch_text = ''
            if os.name == 'nt':
                batch_text = '@echo off\n'
                batch_text += 'set FG=%_fg\n'
                batch_text += 'set BG=%_bg\n'

            manifest_lines = colorize_status(manifest_lines)

            print('\nRestored the following state from microbranch "%s":' % shelf_name_unquoted)
            for line in manifest_lines:
                if options.ansi_color:
                    if options.ansi_color_requires_batch:
                        batch_text += 'echo %s\n' % line[3]
                    else:
                        print(line[3])
                else:
                    print(line[0], line[1])

            if options.ansi_color:
                if options.ansi_color_requires_batch:
                    if os.name == 'nt':
                        batch_text += 'color %FG on %BG\n'
                    open(options.batch_file_name, 'w').write(batch_text)
                    os.system(options.batch_file_name)

            if options.erase_cache:
                print('Removing cached microbranch "%s".' % shelf_name_unquoted)
                try:
                    os.remove(manifest_name)
                    os.remove(manifest_archive)
                except:
                    os.chdir(working_dir)
                    self.message = 'ERROR: Failed to remove cached files.'
                    return False

        os.chdir(working_dir)
        return True

    def cleanup(self, options, quiet=False):
        if not self.mb_root:
            self.message = 'ERROR: Missing microbranch path.'
            return False

        shelf_name = 'shelf'
        if len(options.shelf_name) != 0:
            shelf_name = options.shelf_name

        shelf_name = quote(shelf_name, '')

        folder = os.path.join(tempfile.gettempdir(), '__%s__' % shelf_name)
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
            except:
                self.message = 'ERROR: Failed to remove cached microbranch item "%s".' % folder
                return False

        return True

"""
This module compares the assets in the current shelf (if they exist) against
their counterparts in the working copy, and prints them if their changesets are
no longer equal, or their CRC32 values differ.
"""

class Conflicts(object):
    def __init__(self, options):
        if not options.branch:
            return

        working_dir = os.getcwd()
        root = find_hg_root()
        if root:
            # set working directory to the top of the working copy
            os.chdir(root)
            os.chdir("..")

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            print("ERROR: Must be in root of working copy to shelf.", file=sys.stderr)
            sys.exit(1)

        shelf_name = 'shelf'
        if len(options.shelf_name):
            shelf_name = options.shelf_name

        shelf_name_unquoted = shelf_name
        shelf_name = quote(shelf_name, '')

        root = find_mb_root()   # this will not return if we can't find a working location
        manifest_file = os.path.join(root, '%s.manifest' % shelf_name)
        if not os.path.exists(manifest_file):
            if shelf_name == 'shelf':
                print('Working copy has no cached default microbranch.')
            else:
                print('Cannot access microbranch "%s".' % shelf_name_unquoted)
        else:
            manifest_version = 0
            manifest_lines = open(manifest_name).readlines()
            if manifest_lines[0].startswith('version '):
                manifest_version = int(manifest_lines[0][8:])
                del manifest_lines[0]
                if manifest_version >= 1:
                    manifest_comment = manifest_lines[1].rstrip()
                del manifest_lines[0]
            else:
                manifest_comment = manifest_lines[0].rstrip()
                del manifest_lines[0]

            conflict_count = 0
            for line in manifest_lines:
                line = line.rstrip()
                if len(line) == 0:
                    continue
                status, file_name, previous_key = line.split('?')  # 'previous_key' will be an md5 hash starting with MANIFEST_VERSION 2
                if status == 'M':
                    if os.name == 'nt':
                        file_name = file_name.replace('/', '\\')
                    else:
                        file_name = file_name.replace('\\', '/')

                    files_are_equal = False
                    # see if the file is unchanged by the merge; in that case, just copy it
                    if manifest_version <= 1:
                        new_key = get_changeset_for(options, file_name)
                        if not new_key:
                            print("ERROR: Failed to determine changeset for file '%s'!" % file_name, file=sys.stderr)
                            os.chdir(working_dir)
                            sys.exit(1)

                        old_crc32 = crc32(os.path.join(working_folder, file_name))
                        new_crc32 = crc32(file_name)

                        files_are_equal = (previous_key == new_key) and (old_crc32 == new_crc32)
                    else:
                        new_key = hashlib.md5(open(file_name,'rb').read()).hexdigest()
                        files_are_equal = new_key == previous_key

                    if not files_are_equal:
                        if conflict_count == 0:
                            print('Intervening differences detected for the following "%s" microbranch assets:' % (shelf_name_unquoted if shelf_name_unquoted != "shelf" else "default"))
                        print('\t', file_name)
                        conflict_count += 1

            if conflict_count == 0:
                print('No intervening differences detected for "%s" microbranch.' % (shelf_name_unquoted if shelf_name_unquoted != "shelf" else "default"))

        os.chdir(working_dir)
