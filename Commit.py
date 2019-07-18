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
import shutil
import subprocess

try:
    import pyperclip
except:
    pass

from Info import Status
from PyHg_lib import wrap_line, \
                     wrap_lines, \
                     find_hg_root, \
                     is_valid, \
                     extract_comments, \
                     DISPLAY_COMMENT, \
                     Colors
from Stage import StageEntry, StageIO, Staged

#--------------------------------------------

class Commit(object):
    def __init__(self, options):
        if not options.branch:
            return

        working_dir = os.getcwd()

        staged_entries = Staged().get_staged_entries(options)
        if len(staged_entries) and len(options.args):
            print("ERROR: You have staged entries pending; those must be committed or cleared.", file=sys.stderr)
            sys.exit(1)

        if len(staged_entries) > 1:
            print("ERROR: You may only commit staged modifications from one area at a time.", file=sys.stderr)
            sys.exit(1)

        if (options.stage_name is not None) and (options.stage_name not in staged_entries):
            print('ERROR: You have specified a staging area ("%s") that does not exist.' % options.stage_name, file=sys.stderr)
            sys.exit(1)

        output = []
        root = options.working_dir

        stage_db = {}

        if len(staged_entries):
            # staged entries are all relative to the root of the working copy
            # so we need to put ourselves there...
            root = find_hg_root()
            if root is None:
                print("ERROR: Could not find the root of the working copy.", file=sys.stderr)
                sys.exit(1)

            # need root before we alter it
            stage_name = staged_entries.keys()[0]
            stage_path = StageIO().get_staging_root(root, options)
            stage_db_path = os.path.join(stage_path, stage_name)
            stage_db_file = os.path.join(stage_db_path, 'stage.db')
            stage_db = StageIO().load_stage_db(stage_db_file)

            lines = stage_db.keys()

            os.chdir(root)
            os.chdir("..")
            root = os.getcwd()
        else:
            command = ['hg', 'status', '-q', '.']
            output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
            lines = output.split('\n')

        if len(options.args):
            newlines = []
            # they are specifying files to be committed...filter 'lines'
            # based on them
            for item in options.args:
                found = -1
                for i in range(len(lines)):
                    if item in lines[i]:
                        newlines.append(lines[i])
                        break

            if len(newlines) == 0:
                print("Your specified filter(s) did not match any pending changes in the working copy.", file=sys.stderr)
                sys.exit(1)

            lines = newlines

        all_comments = {}

        batch_text = ''
        if os.name == 'nt':
            batch_text = '@echo off\n'
            batch_text += 'set FG=%_fg\n'
            batch_text += 'set BG=%_bg\n'

        files_to_commit = ['.']
        if len(staged_entries) or len(options.args):
            files_to_commit = []

        snapshot_backups = False

        for line in lines:
            line = line.strip()
            if not len(line):
                continue

            if len(stage_db):
                status = stage_db[line].state
                filename = line
            else:
                status = line[0]
                filename = line[2:]

            staged_entry = None
            if len(stage_db):
                staged_entry = stage_db[filename]
                if staged_entry.state != status:
                    # must be the same state; abort
                    print('ERROR: Staged version of "%s" has different state (%s != %s).' (filename, staged_entry.state, status), file=sys.stderr)
                    sys.exit(1)
                full_path = os.path.join(root, filename)
            else:
                full_path = os.path.join(options.working_dir, filename)

            if not os.path.exists(full_path):
                print('WARNING: Skipping non-existent file "%s".' % full_path, file=sys.stderr)
                continue

            # if this is a referenced entry, then no additional processing is
            # required; a snapshot, however, requires  some more complicated
            # heuristics...
            if len(stage_db) and (staged_entry.snapshot is not None):

                # staged snapshot heuristics:
                # 1. if the timestamps are equal, the snapshot becomes a reference

                snapshot_path = os.path.join(stage_db_path, staged_entry.snapshot)
                snapshot_stat = os.stat(snapshot_path)
                source_stat = os.stat(full_path)

                if int(snapshot_stat.st_mtime) == int(source_stat.st_mtime):
                    # the current state of the source version is identical
                    # to the snapshot, so that is what will be committed
                    # (reference behavior)
                    pass
                else:
                    # 2. if timestamps differ, then the snapshot becomes the commit target
                    #  a. a backup of the source file is made and then it is reverted
                    #  b. the source backup uses the snapshot's filename with a ".bak" extension
                    #  c. the snapshot contents replace the source file using the snapshot's state
                    #  d. committing proceeds as though the staged file is a reference
                    #  e. when committing is complete, the source's backup and state are restored

                    snapshot_bak_path = os.path.join(stage_db_path, '%s.bak' % staged_entry.snapshot)

                    try:
                        shutil.copy2(full_path, snapshot_bak_path)
                    except:
                        print('ERROR: Backup of "%s" could created for version in "%s" staging area..' % (filename, staged_entries.keys()[0]), file=sys.stderr)
                        sys.exit(1)

                    try:
                        shutil.copy2(snapshot_path, full_path)
                    except:
                        print('ERROR: Staged version of "%s" in "%s" staging area could placed for comitting.' (filename, staged_entries.keys()[0]), file=sys.stderr)
                        sys.exit(1)

                    snapshot_backups = True

            comments = None

            if ((status == 'M') or (status == 'A')):
                if len(stage_db) or len(options.args):
                    files_to_commit.append(filename)
                if (options.log_file is None) and (options.commit_message is None) and is_valid(filename):
                    try:
                        comments = extract_comments(full_path, display=DISPLAY_COMMENT)
                    except Exception as e:
                        os.chdir(working_dir)
                        print(str(e), file=sys.stderr)
                        comments = None

            stage_prefix = ''
            if len(stage_db):
                stage_prefix = '[%s] ' % (options.stage_name if options.stage_name is not None else staged_entries.keys()[0])
            if options.ansi_color:
                if options.ansi_color_requires_batch:
                    batch_text += 'echo %s%s%s\n' % (stage_prefix, Colors['BrightYellow'], filename)
                else:
                    print('%s%s%s' % (stage_prefix, Colors['BrightYellow'], filename))
            else:
                print('%s%s' % (stage_prefix, line))

            if comments:
                all_comments[filename] = comments
                #all_comments.append('[ %s ]' % file)
                #all_comments += comments

        if options.ansi_color:
            if options.ansi_color_requires_batch:
                if os.name == 'nt':
                    batch_text += 'color %FG on %BG\n'
                open(options.batch_file_name, 'w').write(batch_text)
                os.system(options.batch_file_name)

        comment_count = len(all_comments.keys())

        if comment_count > 0:
            comment_keys = list(all_comments.keys())
            comment_keys.sort()

            with open(options.batch_file_name, 'w') as f:
                for key in comment_keys:
                    if comment_count > 1:
                        f.write('[ %s ]\n' % key)
                    f.write('\n'.join(all_comments[key]))
                    f.write('\n')
            if 'PYHG_COMMENT_EDITOR' in os.environ:
                subprocess.call([os.environ['PYHG_COMMENT_EDITOR'], options.batch_file_name])
            else:
                if os.name == 'nt':
                    # probably not the best editor, but it's known
                    subprocess.call([r'C:\Windows\System32\notepad.exe', options.batch_file_name])
                else:
                    # same here (although vi is MY personal favorite :)
                    subprocess.call(['vi', options.batch_file_name])

        if options.log_file is not None:
            # ensure the log file text is wrapped at specific column offsets
            log_lines = wrap_lines(options.log_file, options.wrap_at)

            if options.auth_token is not None:
                log_lines.append('(%s)' % options.auth_token)

            # write it out to the 'batch_file_name' target
            open(options.batch_file_name, 'w').write('\n'.join(log_lines))

            # set a flag to trip the log version of the HG command
            all_comments[options.log_file] = True

        elif options.commit_message is not None:
            # ensure the log file text is wrapped at specific column offsets
            log_lines = wrap_lines(options.commit_message, options.wrap_at)

            if options.auth_token is not None:
                log_lines.append('(%s)' % options.auth_token)

            # write it out to the 'batch_file_name' target
            open(options.batch_file_name, 'w').write('\n'.join(log_lines))

            # set a flag to trip the log version of the HG command
            all_comments[options.commit_message] = True

        try:
            input('Press ENTER when ready to commit (press Ctrl-C to abort):')
        except SyntaxError:
            pass

        if len(stage_db):
            assert len(files_to_commit) == len(stage_db), "Staged files have been missed in the commit!"

        if len(all_comments):
            command = ['hg', 'commit', '-l', options.batch_file_name] + files_to_commit
        else:
            command = ['hg', 'commit'] + files_to_commit

        if len(stage_db):
            output = subprocess.Popen(command, stdout=subprocess.PIPE, cwd=root).communicate()[0].decode("utf-8")
        else:
            output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")

        first_line = True
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            if first_line and len(line) == 0:
                continue
            print(line)
            first_line = False

        if options.push_changes:
            options.args = []
            if options.push_external:
                options.args = ["extern"]
            Push(options)

        # put the comment text on the system clipboard (if available)

        if len(all_comments):
            comment_text = open(options.batch_file_name).readlines()
            try:
                pyperclip.copy(comment_text)
            except:
                pass

        os.chdir(working_dir)

        # if we committed from staged files, remove the area
        if len(stage_db):
            if snapshot_backups:
                # we need to restore snapshot backups to their proper place
                # in the repository before we blow away the staging area
                for key in stage_db:
                    entry = stage_db[key]
                    if entry.snapshot is not None:
                        snapshot_bak_path = os.path.join(stage_db_path, '%s.bak' % entry.snapshot)
                        if os.path.exists(snapshot_bak_path):
                            # restore the contents of this file
                            shutil.copy2(snapshot_bak_path, key)
                            # if state is 'M', then the copy itself will set it
                            if entry.state == 'A':
                                # execute an add on the file
                                command = ['hg', 'add', key]
                                output = subprocess.Popen(command, stdout=subprocess.PIPE, cwd=root).communicate()[0].decode("utf-8")
                                if len(output.strip()) != 0:
                                    print('ERROR: Failed to restore snapshot backup for entry "%s" in the "%s" staging area.' % (key, staged_entries.keys()[0]), file=sys.stderr)
                                    sys.exit(1)

            shutil.rmtree(stage_db_path)
