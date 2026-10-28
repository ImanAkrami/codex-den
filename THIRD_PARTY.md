# Third-party software

Codex Den is MIT licensed. Source installations resolve dependencies separately; standalone executables bundle Python and runtime dependencies. Their licenses apply to the included software:

| Package | License | Project |
| --- | --- | --- |
| Textual | MIT | https://github.com/Textualize/textual |
| Rich (through Textual) | MIT | https://github.com/Textualize/rich |
| tomli-w | MIT | https://github.com/hukkin/tomli-w |

The lockfile records dependency versions. Distribution wheels contain Codex Den's code and stylesheet. Native releases include architecture-specific `THIRD_PARTY_NOTICES` assets with dependency, Python, and native-library license text; those notices are also embedded in the executable. Editor applications and extensions are not bundled.

Standalone builds use [PyInstaller](https://pyinstaller.org/en/stable/license.html) and its contributed hooks as build tools. PyInstaller's license exception permits distribution of bundled applications under their own license. The build group pins PyInstaller 6.22.3 and hooks-contrib 2026.9; review their [release notes](https://pyinstaller.org/en/stable/CHANGES.html) and [hook changes](https://github.com/pyinstaller/pyinstaller-hooks-contrib/blob/v2026.9/CHANGELOG.rst) before updating. Native notices retain PyInstaller's license and exception.

Documentation screenshots are generated from demonstration data using Textual/Rich. Optional PNG rendering uses [CairoSVG](https://cairosvg.org/) (LGPL-3.0-or-later) as a development tool; it is not a runtime dependency or bundled executable. See installed dependency metadata for complete transitive-license details.
