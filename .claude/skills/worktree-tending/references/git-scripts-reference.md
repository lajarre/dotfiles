# Git Worktree Scripts Reference

Complete documentation of custom git scripts for worktree management located in `~/bin/`.

## git-newtree

Creates a new git worktree in the `.tree/` directory.

### Usage

```bash
git newtree <name> [branch-name]
```

### Arguments

- `<name>` (required) - Folder name in `.tree/` for the worktree
- `[branch-name]` (optional) - Branch name (defaults to `<name>`)

### Behavior

1. Creates `.tree/` directory if it doesn't exist
2. Creates worktree at `.tree/<name>`
3. If branch exists: checks it out; otherwise creates new branch
4. Copies `.env` and `.envrc` files to the worktree if present in the parent repo

### Examples

```bash
git newtree feature-x          # Creates .tree/feature-x with branch 'feature-x'
git newtree fix main           # Creates .tree/fix using existing 'main' branch
```

### Output

```
Creating worktree at .tree/feature-x with new branch 'feature-x'
✓ Worktree created at .tree/feature-x
✓ New branch 'feature-x' created
✓ Copied .env to .tree/feature-x/.env
To switch to this worktree: cd .tree/feature-x
```

### Script Location

`~/bin/git-newtree`

---

## git-killtree

Removes a git worktree and optionally deletes its branch.

### Usage

```bash
git killtree <path> [-f|--force]
```

### Arguments

- `<path>` (required) - Path to the worktree directory
- `-f, --force` (optional) - Force removal of unclean worktree and force-delete branch

### Behavior

1. Removes worktree at the specified path
2. Without `--force`: deletes branch only if fully merged (`git branch -d`)
3. With `--force`: removes dirty worktree and force-deletes branch (`git branch -D`)

### Examples

```bash
git killtree .tree/feature-x        # Remove worktree, delete branch if merged
git killtree .tree/fix --force      # Force remove worktree and force-delete branch
```

### Output (Normal)

```
Removing worktree at .tree/feature-x
✓ Worktree removed
Deleting branch 'feature-x' (only if merged)
✓ Branch 'feature-x' deleted
Done
```

### Output (Branch Not Merged)

```
Removing worktree at .tree/feature-x
✓ Worktree removed
Deleting branch 'feature-x' (only if merged)
✗ Branch 'feature-x' is not fully merged
  Use --force to force-delete the branch
```

### Script Location

`~/bin/git-killtree`

---

## git-maingulp

Rebases main onto a branch, pushes, and cleans up the worktree and branch. This is the standard workflow for completing feature work.

### Usage

```bash
git maingulp <branch> <worktree-path>
```

### Requirements

- **Must be run from the 'main' branch** (typically in `.tree/maincomp`)
- Branch must exist
- Worktree path must exist

### Arguments

- `<branch>` (required) - Name of the branch to rebase onto main
- `<worktree-path>` (required) - Path to the worktree directory to remove

### Behavior

1. Rebases main onto the specified branch (fast-forward merge)
2. Pushes main to the remote
3. Force-removes the worktree at the specified path
4. Deletes the local branch (only if fully merged)

### Examples

```bash
cd .tree/maincomp
git maingulp feature-x .tree/feature-x
```

### Output

```
Rebasing main onto 'feature-x'...
Pushing main...
Removing worktree at '.tree/feature-x'...
Deleting branch 'feature-x'...
✓ Successfully completed main gulp workflow
```

### Error Handling

- **Not on main branch:** `Error: must be on 'main' (currently on 'feature-x')`
- **Branch doesn't exist:** `Error: branch 'feature-x' does not exist`
- **Rebase fails:** `Error: rebase failed`
- **Push fails:** `Error: push failed`

### Script Location

`~/bin/git-maingulp`

---

## git-archivebranch

Archives a branch by tagging it and deleting it both locally and remotely (for GitHub repos).

### Usage

```bash
git archivebranch <branch-name>
```

### Arguments

- `<branch-name>` (required) - Name of the branch to archive

### Behavior

1. Creates a tag: `archive/<branch-name>`
2. Removes any worktrees associated with the branch
3. Force-deletes the local branch
4. For GitHub repos:
   - Checks for open PRs using this branch as base
   - Deletes the remote branch if no blocking PRs
5. For non-GitHub repos: only local operations

### Examples

```bash
git archivebranch feature-x
git archivebranch old-experiment
```

### Output

```
Removing worktrees for branch feature-x
Checking if branch is used in some github pulls
Tagging archive/feature-x
Force-deleting branch feature-x
Deleting the branch in origin
✓ Branch feature-x archived successfully
```

### Restrictions

- **Cannot archive main/master:** `Error: Don't archive main.`
- **Branch is PR base:** Lists affected PRs and exits

### Restoring Archived Branch

```bash
git checkout -b <branch-name> archive/<branch-name>
```

### Script Location

`~/bin/git-archivebranch`

---

## git-substat

Utility for checking submodule status (not directly related to worktree workflow).

### Script Location

`~/bin/git-substat`

---

## Git Config Aliases

Relevant git aliases from `~/.gitconfig`:

### Branch Management

```gitconfig
b = !git --no-pager branch --sort=-committerdate    # List branches by commit date
co = checkout
cb = branch --show-current                           # Show current branch name
```

### Commit Workflow

```gitconfig
ci = "!staged_files=... && git commit"  # Commit with [XXX] check
cia = commit --amend
cias = commit --amend --no-edit --sign
```

### Branch Publishing

```gitconfig
publish = "!f(){ git push -u origin $(git rev-parse --abbrev-ref HEAD); }; f"
pub = "!f(){ git publish \"$@\"; }; f"
```

### Interactive Branch Selection

```gitconfig
bmap = "!f(){ git branch | grep -v '\\*' | cut -c 3- | fzf --multi ... | xargs -I% git \"$@\" %; }; f"
```

Usage example:
```bash
git bmap checkout  # Interactively select and checkout branch
git bmap merge     # Interactively select and merge branches
```

---

## Worktree Layout Example

Typical repository structure with multiple worktrees:

```
/path/to/my-project/                (main repo, detached HEAD)
├── .git/
├── .tree/
│   ├── maincomp/           (main branch)
│   ├── feature-x/          (feature-x branch)
│   ├── fix-bug/            (fix-bug branch)
│   ├── experiment/         (experiment branch)
│   └── check-lint/         (check/lint-graphql branch)
└── my-project.bare/        (bare repository backup)
```

Each `.tree/*` directory is a complete working directory with its own branch checked out.
