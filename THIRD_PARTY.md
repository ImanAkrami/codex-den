# Third-party software

Codex Den is MIT licensed. Its runtime dependencies are installed separately; their licenses still apply to those packages:

| Package | License | Project |
| --- | --- | --- |
| Textual | MIT | https://github.com/Textualize/textual |
| Rich (through Textual) | MIT | https://github.com/Textualize/rich |
| tomli-w | MIT | https://github.com/hukkin/tomli-w |

The lockfile records dependency versions. Distribution wheels contain Codex Den's code and stylesheet, not bundled editor applications, extensions, or dependency source trees.

Documentation screenshots are generated from demonstration data using Textual/Rich. Optional PNG rendering uses [CairoSVG](https://cairosvg.org/) (LGPL-3.0-or-later) as a development tool; it is not a runtime dependency or bundled executable. See installed dependency metadata for complete transitive-license details.
