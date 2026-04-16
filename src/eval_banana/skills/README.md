# Bundled Skills

This directory is the source of truth for agent skills shipped inside the
`eval-banana` wheel.

Bundled skills in this repository:

- `eval-banana`
- `gemini_media_use`

The two skills serve different purposes:

- `eval-banana` helps an agent understand this project and how to use the
  framework in a target repository.
- `gemini_media_use` provides helper scripts and references for Gemini media
  workflows that some harness runs need.

Both are development assets in this repository and runtime assets for users.
They are authored here, packaged into the wheel from here, and installed into a
target project's native agent skill directories from here.

Those install destinations are agent-native directories such as:

- `.claude/skills/`
- `.codex/skills/`
- `.agents/skills/`
- `.gemini/skills/`

`eval-banana run` does not copy these skills automatically.

`eb install` is the only supported path that moves bundled skills out of the
installed wheel and into a real project directory. That command:

- discovers the bundled skills from package resources
- installs them into the selected agent directories
- generates Codex metadata when needed
- marks installed directories so future upgrades can overwrite only
  eval-banana-owned targets by default

Do not treat the installed agent directories as source. Edit the bundled skill
contents here, then run `eb install` again in the target project.
