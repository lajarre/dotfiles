# Git worktree scripts reference

Complete documentation of custom git scripts for worktree management located in `~/bin/`.

## Safety invariants (read this first)

### Invariant 1: `.tree/` must never be committed
All worktrees live under `.tree/`. Therefore, `.tree/` must be git-ignored in every repository that uses these scripts.

**Verification (recommended):**
```bash
git check-ignore -v .tree/ .tree/* || true
```

**If `.tree/` is not ignored:**
1. Add this to the repo’s `.gitignore`:
   ```gitignore
   .tree/
   ```
2. Commit the change.
3. Only then create worktrees.

Rationale: if `.tree/` is tracked, worktrees can accidentally become part of commits and PRs.

### Invariant 2: run baseline tests after creating a worktree
After creating a new worktree, run baseline tests once before making changes. This tells you whether later failures are “new regressions” or “pre-existing”.

**Baseline test command selection (recommended order):**
1. A project-specific documented command (e.g., in `CLAUDE.md`, `README`, `Makefile`, or `scripts/test`).
2. Otherwise, pick a common default based on the repo:
   - `package.json`: `npm test` (or the project’s package manager)
   - `Cargo.toml`: `cargo test`
   - `pyproject.toml`: `pytest`
   - `go.mod`: `go test ./...`
3. If unclear, ask the user (do not guess).

---

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
1. (Safety) Verifies `.tree/` is git-ignored; exits with error if not
2. Creates `.tree/` directory if it doesn't exist
3. Creates worktree at `.tree/<name>`
4. If branch exists: checks it out; otherwise creates new branch
5. Copies `.env` and `.envrc` to the worktree if present in the parent repo
6. Symlinks `.claude/settings.local.json` from repo root (shared across all worktrees)
7. Prints the path and prompts running baseline tests

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
✓ Linked .claude/settings.local.json from repo root
To switch to this worktree: cd .tree/feature-x

Next step: run baseline tests in the new worktree to verify clean state
```

### Script location
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

### Script location
`~/bin/git-killtree`

---

## git-maingulp

Rebases main onto a branch, pushes, and cleans up the worktree and branch. This is the standard workflow for completing feature work.

### Usage
```bash
git maingulp <branch> <worktree-path>
```

### Requirements
- Must be run from the 'main' branch worktree (typically in `.tree/maincomp`)
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

### Recommended safety steps before running
1. In the feature worktree: run baseline tests and ensure they pass.
2. Ensure the worktree is clean (commit or stash).
3. Confirm with the user, because this workflow is destructive (push + delete worktree + delete branch).

### Script location
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

### Restrictions
- Cannot archive main/master: `Error: Don't archive main.`
- Branch is PR base: Lists affected PRs and exits

### Restoring archived branch
```bash
git checkout -b <branch-name> archive/<branch-name>
```

### Script location
`~/bin/git-archivebranch`

---

## git-substat
Utility for checking submodule status (not directly related to worktree workflow).

### Script location
`~/bin/git-substat`

---

## Git config aliases (selected)

### Branch management
```gitconfig
b = !git --no-pager branch --sort=-committerdate
co = checkout
cb = branch --show-current
```

### Branch publishing
```gitconfig
publish = "!f(){ git push -u origin $(git rev-parse --abbrev-ref HEAD); }; f"
pub = "!f(){ git publish "$@"; }; f"
```

---

## Worktree layout example

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
