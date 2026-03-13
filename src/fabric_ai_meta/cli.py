"""CLI entrypoint for fabric-ai-meta using Click."""

import click


@click.group()
def main():
    """Fabric AI Meta — extract, analyze, and export Fabric semantic model metadata for AI frameworks."""
    pass


if __name__ == "__main__":
    main()
