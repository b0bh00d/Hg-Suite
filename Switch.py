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
This module switches the working directory to another (specified) branch.  This
action is simple enough, but if the current branch has modifications, this module
will utilize the Shelve and Restore modules to slot changes away for the current
branch, and then re-apply any pending changes for the incoming branch.
"""

import os
import re
import sys
import urllib
import shutil
import subprocess

from Action import Action
from Shelf import Shelve, Restore
from PyHg_lib import find_hg_root, find_mb_root

#--------------------------------------------

class Switch(Action):
    def __init__(self):
        super(Switch, self).__init__()

        self.mb_root = None
        self.mb_switch = None

    def execute(self, options, quiet=False, **kwargs):
        if not options.branch:
            self.message = 'ERROR: Could not determine branch.'
            return False

        working_dir = os.getcwd()

        root = find_hg_root()
        if root:
            os.chdir(root)
            os.chdir("..")

        if not os.path.exists('.hg'):
            os.chdir(working_dir)
            self.message = 'ERROR: Must be in root of working copy to use the switch command.'
            return False

        if (len(options.args) == 0) and (len(options.shelf_name) == 0):
            os.chdir(working_dir)
            self.message = 'ERROR: A target branch name must be specified.'
            return False

        if len(options.shelf_name):
            options.args = [options.shelf_name]
            #options.shelf_name = ''

        self.mb_root = find_mb_root()   # this will not return if we can't find a working location
        self.mb_switch = os.path.join(self.mb_root, 'switch')
        if not os.path.exists(self.mb_switch):
            try:
                os.mkdir(self.mb_switch)
            except:
                self.message = 'ERROR: Could not create folder "%s".' % self.mb_switch
                return False

        target_branch = options.args[0]

        # validate the target branch name
        output = subprocess.Popen(['hg', 'branches'], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        found = False
        for line in output.split('\n'):
            data = re.search('([a-zA-Z0-9\.]+)\s+', line)
            if not data:
                continue
            if target_branch == data.group(1):
                found = True
                break

        if not found:
            os.chdir(working_dir)
            self.message = 'ERROR: The specified target branch "%s" cannot be validated.' % target_branch
            return False

        # are there any pending changes?
        output = subprocess.Popen(['hg', 'status', '--quiet'], stdout=subprocess.PIPE).communicate()[0].decode("utf-8")
        if len(output):
            # shelve the changes
            if not self.shelve(options):
                os.chdir(working_dir)
                return False

        # now the easy part...
        if subprocess.call(['hg', 'update', target_branch]) != 0:
            self.message = 'ERROR: Switching to the target branch "%s" failed.' % target_branch
            # ok, restore the shelved work above, if any
            if not self.restore(options):
                # whoa..everything's going to Hell in a handbasket...
                self.message = '%s\nERROR: Failed to restore the shelved microbranch for current branch "%s".' % options.branch
            return False

        # apply any cached micro-branch work
        options.args[0] = target_branch
        # make sure we overwrite things
        options.overwrite = True
        if not self.restore(options):
            print(self.message, file=sys.stderr)
            self.message = 'ERROR: Failed to apply cached micro-branch to branch "%s".' % target_branch
            return False

        # if restore() is successful, any cached data for the target
        # branch is deleted

        # we're done!

        os.chdir(working_dir)
        return True

    def cleanup(self, options, quiet=False):
        return True

    def shelve(self, options):
        if sys.version_info[0] > 2:
            microbranch_base_name = urllib.parse.quote(options.branch,'')
        else:
            microbranch_base_name = urllib.quote(options.branch,'')
        microbranch_backup_name = '_%s' % microbranch_base_name
        microbranch_base_path = os.path.join(self.mb_switch, microbranch_base_name)
        backup_base_name = os.path.join(self.mb_switch, microbranch_backup_name)

        for filename in ['%s.7z' % backup_base_name, '%s.manifest' % backup_base_name]:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except:
                    self.message = "Failed to remove backup file %s" % filename
                    return False

        # there should be no lingering shelf items for this branch
        #cached_microbranch = os.path.join(self.mb_switch, '%s.7z' % urllib.quote(options.branch,''))
        filename = '%s.7z' % microbranch_base_path
        assert not os.path.exists(filename)

        options.args[0] = options.branch
        #shelve_options = deepcopy(options)
        #shelve_options.args[0] = options.branch
        print('Shelving current working copy changes...')
        shelve = Shelve()
        if not shelve.execute(options, quiet=True, mb_root=self.mb_switch):
            self.message = shelve.message
            return False
        else:
            if not shelve.cleanup(options):
                self.message = shelve.message
                return False

        # if Shelve completes successfully, everything is reverted, and
        # the branch has been reset...

        return True

    def restore(self, options, clear_cache=True):
        if sys.version_info[0] > 2:
            microbranch_base_name = urllib.parse.quote(options.args[0],'')
        else:
            microbranch_base_name = urllib.quote(options.args[0],'')
        microbranch_backup_name = '_%s' % microbranch_base_name
        microbranch_base_path = os.path.join(self.mb_switch, microbranch_base_name)

        filename = '%s.7z' % microbranch_base_path
        if not os.path.exists(filename):
            return True     # nothing to do; all good

        print('Restoring shelved working copy changes...')
        restore = Restore()
        if not restore.execute(options, quiet=True, mb_root=self.mb_switch):
            self.message = restore.message
            return False
        else:
            if not restore.cleanup(options):
                self.message = restore.message
                return False

        if clear_cache:
            try:
                os.rename(filename, '%s.7z' % os.path.join(self.mb_switch, microbranch_backup_name))
            except:
                self.message = 'ERROR: Failed to remove cached micro-branch item "%s".' % filename
                return False

            filename = '%s.manifest' % microbranch_base_path
            if os.path.exists(filename):
                try:
                    os.rename(filename, '%s.manifest' % os.path.join(self.mb_switch, microbranch_backup_name))
                except:
                    self.message = 'ERROR: Failed to remove cached micro-branch item "%s".' % filename
                    return False
        return True
