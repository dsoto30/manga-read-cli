# manga-read

Interactive CLI for searching manga on Weeb Central, reading chapters in the terminal, and downloading chapters as PDFs.

## Requirements

- Python 3.10+
- A terminal that supports interactive prompts

For terminal image reading, `read` mode works best in terminals with inline image support, such as iTerm2 or Kitty.

## Install From GitHub

The recommended install method is `pipx`, because it installs the CLI in its own isolated Python environment while still making the `manga-read` command available globally.

```bash
pipx install git+https://github.com/dsoto30/manga-read-cli.git
```

Then run:

```bash
manga-read
```

If you do not have `pipx` installed:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
```

Restart your terminal after `ensurepath`, then run the `pipx install` command again.

## Upgrade

```bash
pipx upgrade manga-read
```

## Uninstall

```bash
pipx uninstall manga-read
```

## Development Install

Clone the repo and install it in editable mode:

```bash
git clone https://github.com/dsoto30n/manga-read-cli.git
cd manga-read-cli
python -m venv venv
source venv/bin/activate
pip install -e .
```

Now run:

```bash
manga-read
```

## Build A Package

To build distributable package files:

```bash
pip install build
python -m build
```

This creates package artifacts in `dist/`.
