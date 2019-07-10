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

import Stage

from Action import Action
from PyHg_lib import find_hg_root, \
                     MyParser, \
                     colorize_status, \
                     fixup_renames, \
                     is_valid, \
                     marshall_comments, \
                     format_seconds, \
                     Colors

#--------------------------------------------

class Status(Action):
    def __init__(self):
        super(Status, self).__init__()

    def execute(self, options, quiet=False, **kwargs):
        def process_workingcopy():
            #command = ['hg', 'status', '--subrepos', '-q', '.']
            command = ['hg', 'status', '--subrepos', '-q', '-C', '.']
            output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
            lines = fixup_renames(output.split('\n'))

            # decorate entries based on any staging information

            orphaned_tag = '^'
            orphaned_count = 0

            root = find_hg_root()

            stage_path = Stage.StageIO().get_staging_root(root, options)
            if os.path.exists(stage_path):
                stage_names = os.listdir(stage_path)

                # if len(stage_names) and len(lines) == 0:
                #     msg = 'ERROR: Orphaned staged entries found in the following areas:\n'
                #     for stage_name in stage_names:
                #         msg += '  [%s]\n' % stage_name
                #     msg += '\nUse "unstage --erase" to clear them.'
                #     self.message = msg
                #     return False

                for stage_name in stage_names:

                    # reference_count = 0
                    # capture_count = 0

                    stage_db_path = os.path.join(stage_path, stage_name)
                    stage_db_file = os.path.join(stage_db_path, 'stage.db')
                    if not os.path.exists(stage_db_file):
                        continue    # odd... should probably print a message

                    stage_db = Stage.StageIO().load_stage_db(stage_db_file)

                    # (yes, yes, I know...quadratic complexity: I don't care :)
                    for key in stage_db:
                        staged_entry = stage_db[key]
                        found = False
                        for i in range(len(lines)):
                            if key == lines[i][2:]:
                                # reference_count += 1 if staged_entry.snapshot is None else 0
                                # capture_count += 1 if staged_entry.snapshot is not None else 0

                                snap = Stage.StageIO().get_staged_entry_tag(stage_db_path, staged_entry, key)

                                lines[i] = '%s [%s] %s (%s)' % (lines[i][:1], stage_name, key, snap)

                                found = True
                                break
                        if not found:
                            snap = Stage.StageIO().get_staged_entry_tag(stage_db_path, staged_entry, key)
                            # if this is a refernce, it's orphaned
                            orphaned = ''
                            if staged_entry.snapshot is None:
                                # reference_count += 1
                                orphaned = orphaned_tag
                                orphaned_count += 1
                            lines.append('%s [%s] %s%s (%s)' % (staged_entry.state, stage_name, orphaned, key, snap))

            self.process_lines(lines, options)

            if orphaned_count != 0:
                print('\n(Use the "staged" command to purge %sorphaned references)' % orphaned_tag)

            return True

        if options.process_all:
            # look at each subfolder of the current folder, and determine if it is a Mercurial folder

            working_copies = False

            for entry in os.listdir('.'):
                hgrc = os.path.join(entry, '.hg', 'hgrc')
                if os.path.isdir(entry) and os.path.exists(hgrc):
                    d = MyParser(hgrc).as_dict()
                    dest = d['paths']['default']

                    working_copies = True

                    os.chdir(entry)
                    print('Scanning %s (%s)...' % (entry, dest))
                    process_workingcopy()
                    os.chdir('..')

            if not working_copies:
                self.message = 'ERROR: No valid Mercurial working copies found under current folder.'
                return False
        else:
            if not options.branch:
                self.message = 'ERROR: No valid branch could found under current folder.'
                return False

            if not process_workingcopy():
                return False

        return True

    def cleanup(self, options, quiet=False):
        return True

    # make our status colorization code available to other classes

    def process_lines(self, lines, options):
        batch_text = ''
        if os.name == 'nt':
            batch_text = '@echo off\n'
            batch_text += 'set FG=%_fg\n'
            batch_text += 'set BG=%_bg\n'
        lines = colorize_status(lines)

        for line in lines:
            filename = line[1]

            full_path = os.path.join(options.working_dir, filename)

            #if not os.path.exists(full_path):
            #    continue

            comments = None

            if ((line[0] == '!') or (line[0] == '+')) and \
               os.path.exists(full_path) and \
               is_valid(filename):
                try:
                    comments = marshall_comments(full_path)
                except Exception as e:
                    print(str(e), file=sys.stderr)
                    comments = None

            if options.ansi_color:
                if options.ansi_color_requires_batch:
                    batch_text += 'echo %s\n' % line[3]
                    if comments:
                        for comment in comments:
                            batch_text += 'echo %s%s\n' % (Colors['BrightGreen'], comment)
                else:
                    print(line[3])
                    if comments:
                        for comment in comments:
                            print('%s%s' % (Colors['BrightGreen'], comment))
                    print(Colors['Reset'], end='')    # reset color
            else:
                print(line[0], line[1])
                if comments:
                    for comment in comments:
                        print(comment)

        if options.ansi_color:
            if options.ansi_color_requires_batch:
                if os.name == 'nt':
                    batch_text += 'color %FG on %BG\n'
                open(options.batch_file_name, 'w').write(batch_text)
                os.system(options.batch_file_name)

class Log(object):
    def __init__(self, options):
        if not options.branch:
            return

        command = ['hg', 'log', '-v']
        if len(options.log_rev) != 0:
            command += ['-r', options.log_rev]
        elif options.log_limit != 0:
            command += ['-l', options.log_limit]

        output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        if len(output) == 0:
            print("ERROR: Invalid revision provided", file=sys.stderr)
            sys.exit(1)

        lines = output.split('\n')

        blank_count = 0
        has_file_changes = False
        id = ''

        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('changeset: '):
                if len(id) != 0:
                    print('-' * 40)
                id = line.split(' ')[-1].split(':')[1]
                print('%s%s%s' % (Colors['BrightGreen'], line, Colors['Reset']))
                has_file_changes = False
            elif line.startswith('description:'):
                print(line)

                blank_count = 0
                i += 1
                while i < len(lines):
                    if len(lines[i].strip()) == 0:
                        blank_count += 1
                    else:
                        if blank_count:
                            print('\n' * blank_count)
                            blank_count = 0
                        print('%s%s%s' % (Colors['BrightYellow'], lines[i], Colors['Reset']))

                    i += 1
                    try:
                        if(lines[i].startswith('changeset: ')):
                            i -= 1 
                            break
                    except IndexError:
                        pass    # we've exceeded the array bounds

                if has_file_changes:
                    print('changes:')
                    command = ['hg', 'status', '-C', '--change', id]
                    output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
                    if len(output) == 0:
                        print("ERROR: Invalid revision provided", file=sys.stderr)
                        sys.exit(1)

                    change_lines = fixup_renames(output.split('\n'))
                    Status().process_lines(change_lines, options)

                print(Colors['Reset'])
            elif line.startswith('files:'):
                has_file_changes = True
            else:
                print(line)

            i += 1
