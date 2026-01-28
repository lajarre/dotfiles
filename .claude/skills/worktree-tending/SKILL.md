---
name: worktree-tending
description: Use when creating, switching, merging, or removing git worktrees. Use when user mentions worktrees, branches in parallel, or .tree/ directories.
---

# Worktree Tending

Manage git worktrees with **worktrunk** (`wt`). Run `wt --help` or `wt <cmd> --help` for full command reference.

## Critical Rule

**After ANY worktree operation, run `wt list` and show results before yielding to user.**

## Quick Reference

| Task | Command |
|------|---------|
| New branch + worktree | `wt switch --create <branch>` |
| Existing branch | `wt switch <branch>` |
| GitHub PR | `wt switch pr:123` |
| List all | `wt list` |
| Interactive picker | `wt select` |
| Merge to main | `wt merge` (from feature worktree) |
| Remove without merge | `wt remove` or `wt remove -D <branch>` |
| Archive branch | `git archivebranch <branch>` (no wt equivalent) |

## What wt --help Won't Tell You

**Root worktree convention:** Keep detached on `origin/main` to avoid conflicts. After merges: `git checkout --detach origin/main`

**wt merge direction:** Run from *feature* worktree, merges current → target (opposite of `git merge`)

**Config location:** `~/.config/worktrunk/config.toml` — sets `.tree/` path template, post-create hooks, and `squash = false` default
