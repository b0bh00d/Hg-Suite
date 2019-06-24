# Hg-Suite
A collection of Python utilities I developed for personal use that add
workflow enhancements to a command-line Mercurial.

## Summary
Coming from a (pre-Linux) UN*X background, I tend to work frequently from the
command line on all platforms.  This suite of utilities grew out of a
need to enhance the out-of-the-box Mercurial feature set with tools that
fit my particular workflow.  Some tools in this suite may seem to duplicate
existing Mercurial features, but they are designed to function outside of
the boundaries of the working copy in order to support my cross-platform
requirements, or they enhance that functionality beyond vanilla Mercurial.

This collection of commands are not stand-alone Python modules--i.e., they
cannot (or should not) be directly imported into other scripts.  There is
a single entry point for using them, which is designed to create an ecosystem
that supports the larger functionality of the suite.  For example, a state
created by one command my be recognized and utilized by another.

The Suite is compatible with both Python v2 and v3.

## Dependencies
Some commands of this suite depend upon the presence of 7-Zip being
available from the command line ("7z" under Windows, "7za" under OS X,
etc.).

There's a minimum of dependency on third-party Python modules.  If they
are not installed, Hg Suite quitely works without them.

Additionally, there are a few environment variables that the suite will
use to affect its behavior, if found.  Otherwise, less-desireable fallback
options will be employed.

Variable      | Purpose       | Fall-back
------------- | ------------- | -------------
PYHG_MICROBRANCH_ROOT | Path to the microbranch cache folder | "%temp%" under Windows; "/tmp" under UN*X variants
PYHG_COMMENT_EDITOR | The executable to use for editing commit comments | "notepad" under Windows; "vi" under UN*X variants
PYHG_MERGE_TOOL | The merge tool to execute when required; two file paths will be provided, source and target

In the future, I may expand persistent state settings to use the Mercurial
configuration file as well, allowing settings to be placed there instead of
using the environment.

## Command Set
The following sections document the commands available, their purpose, and
where applicable, how best to employ them.

Each command is  executed by running the entry point "PyHg.py" module,
and passing in the command selector along with any additional command-line
arguments.  As an example, I use [Cmdr](https://github.com/cmderdev/cmder) as my
shell under Windows, and it allows me to set a large set of macros, so I
set up each available command in Hg Suite as a macro:

`mergeheads=python %PYHG%\PyHg.py mergeheads $*`

I will use only the command names in examples in the following sections, not
the full command line (above) to activate them.

Some commands are more frequently used than others (such as `commit` and
`update`), and some are more highly specialized.

**NOTE**: Hg Suite commands function with a different scope than Mercurial.
By default, Mercurial processes the *entire* working copy when commands are
executed.  Hg Suite differs in that only the current directory and its
subdirectories are processed with Hg Suite commands.

### Managing Changes
I manage code changes as what I term "microbranches".  These are collections
of related code changes that are usually works-in-progress that I do not want
to make a permanent and official part of the repository until ready.

These commands provide managment of these microbranch changesets that exist in
the working copy where they are executed.  They will bundle up file changes
(modifications, deletions and additions) and archive them using 7-Zip in a
cache location on your system (using the `PYHG_MICROBRANCH_ROOT` environment
variable, if set).

This might sound similar to Mercurials existing "shelf" mechanism, however,
it differs significantly in that the shelf location is *outside* of the working
copy folder.  In my particular workflow, this allows me to deposit microbranch
bundles into a cloud-managed location (e.g., Nextcloud) where I can then change
to another platform (e.g., OS X) and instantly re-apply those work-in-progress
changes for further build and functionality testing before making a permanent
repository commit.

#### shelve
This command will collect all pending modifications in a working copy and
store them as a "microbranch" in a location on your local file system.  It
will attempt to use the `PYHG_MICROBRANCH_ROOT` location first, and then fall
back to the system temp location.

Once successfully shelved, the pending changes in the local working copy
are reverted, leaving the working copy without pending changes.

You can provide a name for the "microbranch" to distinguish it from
other existing branches; if no name is given, the default name "shelf" will
be used and any existing "shelf" archive will be rolled.

A comment can also be provided for the "microbranch" by using the 'comment'
option (-c/--comment).

`shelve -c "Adds a read_state() function to the build_lib.py library" read_state`

> Shelved the following state as microbranch "read_state":<br>
> ! build_system\build_lib.py

The `shelve` command will also bundle up any active staging areas into the
archive and clear them along with the working copy's change states.

#### shelved
You can view the microbranches that you currently have shelved by issuing this command:

`shelved`

> The following microbranches are on the shelf:<br>
> &nbsp;&nbsp;"read_state" (Adds a read_state() function to the build_lib.py library)

#### restore
Any shelved microbranch can be re-applied to the current working directory using this command.

Some things to note about `restore`:

* Executed by itself, it uses the most recent "shelf" microbranch (if it exists) as the source
* You can provide a microbranch name to select a specific microbranch as the source
* The command will compare the source changeset value to the target, and if they differ, it will launch the available merge tool to allow you to safely merge in the code differences
* You can use the overwrite option (-o) to cause the source asset to completely overwrite the target asset, skipping merge checks

`restore -o read_state`

> .<br>
> Restored the following state from microbranch "read_state":<br>
> ! build_system\build_lib.py                                 

If active staging areas were included in the shelving action, `restore` will
replace it along with the shelved working copy change states.  If active
staging areas already exist when `restore` is called, the command will abort
and complain about the unknown state.

#### switch
At its core, the `switch` command is functionally equivalent to
`hg update <branchname>`.  However, it works with the microbranch management
tools `shelve` and `restore` to automatically:

1. Cache any current working-copy modifications under the outgoing branch name
2. Restore any previously cached microbranch bundle for the incoming branch name

Again, in my particular workflow, this places the microbranch bundles into a
managed location where I can instantly access it on other platforms, if neeeded.

`switch default.int`

> Shelving current working copy changes...<br>
> 20 files updated, 0 files merged, 9 files removed, 0 files unresolved

`switch default.bob.features`

> 29 files updated, 0 files merged, 0 files removed, 0 files unresolved<br>
> Restoring shelved working copy changes...

#### conflicts
This command compares the assets in the current "shelf" (if they exist) against
their counterparts in the working copy, and prints them if their changesets are
no longer equal, or their CRC32 values differ.

I don't use this one much (one of those "seemed-like-a-good-idea-at-the-time"
features).  Might be removed in the future.

### Committing
This module is centered around making your changes a part of a repository,
whether just in the local, private working copy, or in an upstream, public
server.

#### commit
Ultimately, `commit` performs the same action as `hg commit`.  However, this
command is considerably deeper in the functionlity it provides.

##### [comments]
If no commit message is provided (i.e., -m/--message), then `commit` will
look for the `PYHG_COMMENT_EDITOR` value, and if not set, will fall-back to
a well-known text editor provided by the platform ("notepad" on Windows,
"vi" on UN*X variants).

If a commit message *is* provided on the command line, the `commit` command
will perform some massaging of the text:

* It will word-wrap the text at 80-column offsets (use the 'wrap' option (-w/--wrap) to change this)
* Text will be broken into separate lines whenever a "\n" sequence is encountered

This means that the following command line:

`commit -m "[PUBLIC] BUG-5129: Re-factored the Port system to automatically locate the most current installation of BufferShuffle if an explicit version is not provided.\n[PUBLIC] BUG-5769: Addressed an uninitialized variable reference occuring when the shell window is opened."`

will result in changeset comments formatted like this:

> files:       ...<br>
> description:<br>
> [PUBLIC] BUG-5129: Re-factored the Port code to automatically locate the most<br>
> current installation of BufferShuffle if an explicit version is not provided.<br>
> <br>
> [PUBLIC] BUG-5769: Addressed an uninitialized variable reference occuring when<br>
> the shell window is opened.

##### [aborting]
When it has all the information it requires, the `commit` command will
provide a list of the changes that are about to be stored in the repository,
and provide you with an opportunity to commit or abort.

> build_system\build_lib.py<br>
> Press ENTER when ready to commit (press Ctrl-C to abort):

##### [comment marshaling]
One particular workflow habit I developed many, *many* years ago was that of
embedding commit comments directly into code--a kind of "comment-as-you-go"
workflow.  By placing comments in proximity to the changes to which they relate,
I did not need to remember at commit time why I made a particular change.  In
cases where there were lots of changes that may not directly relate to one
another, this became quite a time-saver.

`commit` uses a comment-management subsystem to locate and extract embedded
commit comments.  Embedded commit comments begin with an AT symbol (@) followed
by a keyword and a colon.  The keyword determines the kind of prefix the commit
comment will have:

Keyword  | Comment prefix
-------- | --------------
@comment | No prefix (considered private)
@private | "[PRIVATE]" prefix (explicitly private; internal, not for public consumption)
@public | "[PUBLIC]" prefix (external, targeting the public)

Embedded comment tags are shielded from the source langauge via that language's
comment system.  Consider the following examples:

* `/* @comment: Corrected a pre-increment error */`
* `// @public: BUG-5093: Envelopes will no longer drop their final keyframes`
* `# @private: Refactored intramodule data exchange to use queues`
* `<!-- @comment: The user is now prompted to enter a path for image asssets. -->`

These embedded comments are extracted from their source files before the commit
is performed.  Backups are made of the original files (containing the embedded
comments) as aborting the commit will leave the "cleansed" files in place.

Embedded commit comments can also span lines.  If you terminate a comment line
with a backslash, and begin the next line with an at symbol (@), Hg Suite
will consider it a continuation and will process it as the same commit message:

`# @private: Refactored intramodule data exchange to use queues \`<br>
`# @instead of TCP/IP sockets`

The `status` command (discuss later) also employs this comment-management
subsystem when displaying the working copy's current state:

`status`

> ! Scripts\Python\add_connection.py<br>
> ... [PRIVATE] Refactored intramodule data exchange to use queues instead of TCP/IP<br>
> &nbsp;&nbsp;&nbsp;&nbsp;sockets

##### [staging]
The `commit` comand detects and works with staged files.  Staging is discussed a later section all its own.

#### push
The `push` command is a pretty thin wrapper around the `hg push` command.

It exists, however, to provide an enhanced function to chain pushing of
changesets through all ancestors of the current working copy up until an
external source is encountered.  This is triggered with the `extern`
option.  Once an external source is found (a push target that doesn't
exist on the local machine), changesets are pushed to that source, and
then chaining stops.

### Staging
Staging is part of the Commit system, but it deserves it's own section.

The Hg Suite provides a git-like change-staging system.  Cherry picked changes
can be added to a staging area with the `stage` command (discussed below).
When staged, only those file changes in the staging area will be considered
by the `commit` command when executed.

**NOTE**: *The staging system is the most recent, and inarguably the most
complex, addition to the Hg Suite, and should be considered "beta" in
comparison to the other commands available in the suite.  Bugs may be
present and additional work be required to complete the feature.*

The staging system will take pains to keep its view of its staged files as
accurate as possible.  This means that the state of the files in a staging
area are reevaluated each time that staging area is processed by any command.
So, if a staged file is reverted to an unmodified (or untracked) state,
then Hg Suite will automatically purge it from the staging area if required
the next time the staging area is processed.

Hg Suite's staging system provides two kinds of staged types: **references**
and **snapshots**.  Snapshots are more like git's system, where a snapshot of
the source file is captured at a point in time, and is independent of the
state of the source file.

References are "light" staged entries, simply maintaining a pointer to
the source file.  The state of the source file is not independent of its
staged reference.  For example, if the state of a source file for a staged
reference is cleared, the staged reference becomes invalid ("orphaned").
The staging system will detect this, and will either automatically purge
the orphaned file, or notify you of the invalid state (depending on the
command executed).  See the `staged` command for more info on this condition.

A staged snapshot is an actual copy of the source file at a point in time.
This means that it is divorced from the state of the source file, and can
continue to be managed in the staging area even *after* the source files
state is changed (even if it is removed from the repository).  At the time
of `commit`, Hg Suite will determine how to handle a snapshot using the
following logic:

1. If the timestamps of the snapshot and source file are identical, the staged entry is treated like a reference
2. If the timestamps differ, Hg Suite will swap the files, perform the commit, and restore the source file as it was before the commit.

It is **important to note** that references can refer to just about any state of a repository file--modified, added, deleted, renamed--while snapshots can *only* be made from existing repository files that have a modified state (i.e., "M").

You can create custom staging areas using the 'stage name' option
(-s/--stage-name).  If one is not provided, then the "default" staging
area will be the target of the commands.

By default, references are staged.  You can specify that a snapshot
should be created instead by specifying the 'snapshot' command (-S/--snapshot).

The `status` comand also recognizes staged files (see below).

#### stage
You can provide full file paths to the `stage` command, or you can provide
just partial text values and `stage` will stage all entries that contain the
text (handy for staging files without all the extra typing).

If your `stage` command detects duplicate entries being staged, they will
"refreshed".  References are no really affected, but snapshots will have their
captured states updated to the current state of their source files.  Be sure
this is the intended outcome--you cannot retreive the lost snapshot state.

`stage build_lib.py`

> The following new reference entries were added to the "default" staging area:<br>
> ! build_system\build_lib.py<br>

If instead, you wanted to create a snapshot, you would include the 'snapshot'
option:

`stage -S build_lib.py`

> The following new snapshot entries were added to the "default" staging area:<br>
> ! build_system\build_lib.py<br>

When adding, you can target custom staging areas using the 'stage name'
option:

`stage -s BUG-4354 build_lib.py`

> The following new reference entries were added to the "BUG-4354" staging area:<br>
> ! build_system\build_lib.py<br>

**Be careful running `stage` without options!**  This will cause all
files in the working folder to be staged into the "default" area as
references.  Additionally, if you have snapshot entries already in the
target staging area, those snapshots will be "refreshed" automatically,
with their previously captured states being irretrievably lost.

Just as a safety net, Hg Suite will prompt you to perform the action should
it detect existing snapshots in the target stging area:

> You are about to refresh snapshot entries in the "default" staging area.<br>
> Press ENTER if this is the intent (or press Ctrl-C to abort):

#### staged
Similar to `shelved`, this command displays the active entries in all the
currently defined areas.

`staged`

> The following entries are pending in the "default" staging area:<br>
> ! Purge.bat (=)<br>
> ! build_system\test_build_system.py (&)

Note in the above output that each entry is trailed by a different symbol.
References are denoted by an ampersand symbol (&).  Snapshots, however,
will have varying symbols depending on their states in relation to their
source files.

When the timestamps between a snapshot and its source file are equal, an
equal sign (=) will be displayed.  When the timestamps differ (e.g., the
source file has been modified or reverted), then the elapsed time difference
between the two files will be displayed.

> The following entries are pending in the "default" staging area:<br>
> ! Purge.bat (15m27s)<br>
> ! build_system\test_build_system.py (&)

The `staged` command will list the entries and states of all entries in all
staging areas is one isn't explicitly named using the 'stage name' option
(-s/--stage-name):

> The following entries are pending in the "default" staging area:<br>
> ! Purge.bat (&)<br>
> The following entries are pending in the "Xpermiment" staging area:<br>
> &plus; test.h (&)<br>
> &plus; test.cpp (&)

A situation can arise where a staged reference loses the linkage with its
source file state.  This happens when the source file for a staged reference
has its state reset.  In these situations, the reference becomes an "orphan".
Such abberations in a staging area are automatically (and silently) purged by
the `staged` command when detected.

`hg revert Purge.bat`<br>
`staged`

> The following entries are pending in the "Xpermiment" staging area:<br>
> &plus; test.h (&)<br>
> &plus; test.cpp (&)

#### unstage
This command will remove entries from a staging area.  Entries are identified
by path, or by filename.

For example, to remove module files "test.cpp" and "test.h" from a staging area:

`staged`

> The following entries are pending in the "Xperiment" staging area:<br>
> &plus; test.h (&)<br>
> &plus; test.cpp (&)

provide the file names to `unstage` them.

`unstage -s Xperiment test.h test.cpp`

If the staging area is left without entries after a call to `unstage`, then
the area is summarily remove from the system.

You can purge all staging areas in your repository by passing the 'erase' option
(-X/--erase) to the `unstage` command.  This will remove **ALL** staged entries, so
**use this with caution**, or you may have to do some rebuilding.

### Updating
Updating is concerned with synchronizing your working copy with other
repositories or branches.

#### update
The `update` command is a fairly light wrapper around the the `hg pull`
and `hg update` Mercurial commands.

It adds some functionality when you pass the 'all' option
(-a/--process-all).  In that case, the command will recursively locate
all working-copy folders under the current working directory and perform
the command on each.

When processing 'all', it sorts the source of the working copies to ensure
that working copies linked to external sources are synchronized first, and
then it processes those that depend on local repositories.  This ensures
that local working copies that depend on other working copies that get their
updates from off site get the most current data.

For clarification, assume you have working copy A, which is a clone of a
github.com project.  Working copy B is a clone of working copy A.  If you run
`update` with the 'all' option in a folder that contains both working copy
A and B, working copy A will be synchronized first to ensure that working
copy B gets updated from the most current version of the upstream files.

#### rebase
Anything other than a trivial repository will eventually need to merge
changes between branches, so the `rebase` command encapsulates that
functionality.

It's a pretty thin wrapper around the `hg merge` command, but performs
some sanity checks--like checking for existing modifications and upstream
merging.  It automatically generates an automatic commit message, indicating
that the changeset is a rebase with a specific branch, and commits the
merge.

You can avoid this final commit step by specifying the 'merge only' option
(-M/--merge-only), in which case the uncommitted merge files will be left
in the working copy for you to dispose of as you wish (undo the merge after
testing the changes, or commit with your own message).  Make sure you know
how to undo a merge if you use this option with that intent--a simple
`hg revert` is not sufficient.

### Miscellaneous

#### status
Generates a report about the state of the working copy.

Like `update`, `status` accepts the 'all' option (-a/--process-all) and
will recurse into working copies beneath the current working directory
and product a status report for each.

The state indicators used by `status` differ from Mercurial.  Modified
files are flagged with an exclamation (!), added files with a plus
sign (+), and deleted files with a minus (-).

The `status` command will detect and display any embedded commit
comments that exist in modified files in the working copy (see the
example in the "[comment marshaling]" section above).

`status` will attempt to correlate modified files in the working copy
against their staged entries, if any, and will display their staging
area and type data.

In cases where it cannot correlate, it will display staged entries based
on their types.  In other words, references will display differently from
their snapshot cousins when their source files are no longer of note.

For example, in the following output, a snapshot file is present along
with a reference in the "default" staging area:

`status`

> ! [default] Purge.bat (=)<br>
> ! [default] build_system\build_lib.py (&)

In cases where a reference has been orphaned, the `status` command
will take pains to make that situation known to you:

`hg revert build_system\build_lib.py`<br>
`status`

> ! [default] ^build_system\build_lib.py (&)              
> ! [default] Purge.bat (16m59s)                          
>                                                        
> (Use the "staged" command to purge ^orphaned references)

Note that the referenece entry contains a caret (^) symbol which
flags it as being orphaned.  Hg Suite provides some helpful advice
on how to correct the situation.

#### diff
The `diff` command scans the current location in the working copy for
any modified files, and then runs a difference command (`hg wdiff`)
on each.  This command peforms a comparison between the working copy
file and its previous version in the repository.

If you have a diff/merge tool defined by `PYHG_MERGE_TOOL`, this tool
will be passed to `hg wdiff` as the tool to use.  Otherwise, `hg wdiff`
will check your Mercurial configuration file for a value in the
"extdiff.cmd.wdiff" setting.  If that isn't set, Mercurial will likely
fall-back to producing a command-line difference.

This command explicitly includes subrepos in locating modified files.

#### mergeheads
If you are collaborating with others on a given repository, merging heads
in Mercurial can become a frequent pasttime.  The `mergeheads` command
is a thin wrapper around the `hg merge` function that performs some
sanity checks, such as ensuring divergent heads *actually* exist and
that no pending changes are present in the working copy.

This command will automatically commit a successful merge with a
fixed commit message.

#### incoming
This command is a thin wrapper around the `hg incoming` command, with
some 'pretty printing' support.  The module is employed by the `update`
command for its delta printing.

# Mercurial-based macros

I'm including here the command-line macros I use (Windows, in this
case) when interacting with Mercurial (whether or not they reference
Hg Suite) just in case somebody might find them useful.

The "$T" token in the macros below is a [Cmdr](https://github.com/cmderdev/cmder) macro idiom used to separate unique commands.  The "$*" token expands to all provided command line arguments.

* `status=py %PYHG%\PyHg.py status $*`
* `comment=py %PYHG%\PyHg.py status $*`
* `commit=py %PYHG%\PyHg.py commit $*`
* `push=py %PYHG%\PyHg.py push $*`
* `pushex=py %PYHG%\PyHg.py push extern $*`
* `mergeheads=py %PYHG%\PyHg.py mergeheads $*`
* `rebase=py %PYHG%\PyHg.py rebase $*`
* `shelve=py %PYHG%\PyHg.py shelve $*`
* `shelved=py %PYHG%\PyHg.py shelved $*`
* `restore=py %PYHG%\PyHg.py restore $*`
* `diff=py %PYHG%\PyHg.py diff $*`
* `conflicts=py %PYHG%\PyHg.py conflicts $*`
* `switch=py %PYHG%\PyHg.py switch -V $*`
* `stage=py %PYHG%\PyHg.py stage $*`
* `unstage=py %PYHG%\PyHg.py unstage $*`
* `staged=py %PYHG%\PyHg.py staged $*`
* `sync=py %PYHG%\PyHg.py update $*`
* `outgoing=hg -v outgoing`
* `pull=hg pull`
* `reset=hg revert --all`
* `serve=hg serve`
* `keepmerge=hg commit -m "rebase with default"`
* `undomerge=hg rollback $T hg update -C -r .`
* `abortgraft=hg update --clean .`
* `ammend=hg commit --ammend -m "$1"`
* `heads=hg log -r tip -T '{count(revset("head()"))}'`
* `hash=hg id -i --debug`
* `diffbranch=hg diff --stat -r $1:$2`
