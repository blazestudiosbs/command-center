# Approval-gated releases

The development worker can commit, push, and deploy Command Center only through a pending release that the authenticated owner approves on the Releases page.

Create a fine-grained GitHub personal access token restricted to the Command Center repository with **Contents: Read and write**. Do not grant administration, workflows, issues, or other unrelated permissions. Store only the token value at:

```text
/opt/command-center/secrets/github_token
```

Protect it with mode `600`, rebuild the development worker, then enable both release capabilities under Agent Permissions.

Safety boundaries:

- `codex/*` branches only.
- GitHub `origin` remotes only.
- No force push.
- `.env`, `secrets/`, `config/`, `.git/`, and `outputs/` cannot be included.
- Repository HEAD and the complete worktree fingerprint must still match the approved preview.
- Approvals expire after 30 minutes and are single-use.
- Deployment is limited to `command-center`, `command-center-ui`, and `vera-discord`.
