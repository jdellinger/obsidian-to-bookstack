import click

from .bookstack.bookstack import Bookstack, BookstackItems
from .config import load_env, load_toml
from .console import console
from .sqllite import DatabaseFunctions as dbf


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose logs")
@click.option("-c", "--config", required=False, help="Specify config file to load from")
@click.option("-e", "--env", required=False, help="Specify env file to load from")
@click.pass_context
def cli(ctx, verbose, config="", env=""):
    dbf.init_db()
    load_env(env)
    toml = load_toml(config)

    assert toml is not None

    path = toml["wiki"]["path"]
    excluded = toml["wiki"]["excluded"]["shelves"]

    console.log(f"Looking at Obsidian Vault at: [bold blue]{path}[/bold blue]")

    if excluded:
        console.log(f"Excluding shelves: [bold blue]{excluded}[/bold blue]")

    with console.status("Building client..."):
        b = Bookstack(path, excluded, verbose=verbose)
        ctx.obj = {"bookstack": b}


@cli.command(help="Call `local` and `remote`")
@click.pass_context
def sync(ctx):
    b = ctx.obj.get("bookstack")

    with console.status("Downloading any missing files..."):
        b.sync_local()

    with console.status("Uploading missing files to remote..."):
        b.sync_remote()


@cli.command(help="Upload any missing files to Bookstack")
@click.pass_context
def remote(ctx):
    with console.status("Uploading missing files to remote..."):
        b: Bookstack = ctx.obj.get("bookstack")
        b.sync_remote()


@cli.command(help="Download any missing files into the Obsidian Vault")
@click.pass_context
def local(ctx):
    b = ctx.obj.get("bookstack")
    with console.status("Downloading any missing files..."):
        b.sync_local()


@cli.command(help="Pull all changes from remote (new files and updates).")
@click.pass_context
def pull(ctx):
    """Combines 'local' and 'update --local' for a full download sync."""
    b = ctx.obj.get("bookstack")

    console.log("Step 1: Downloading any missing files from remote...")
    with console.status("Downloading..."):
        b.sync_local()

    console.log("Step 2: Updating existing local files from remote...")
    with console.status("Updating..."):
        b.update_remote(remote=False, local=True)


@cli.command(help="Push all changes to remote (new files and updates).")
@click.pass_context
def push(ctx):
    """Combines 'remote' and 'update --remote' for a full upload sync."""
    b = ctx.obj.get("bookstack")

    console.log("Step 1: Uploading any missing files to remote...")
    with console.status("Uploading..."):
        b.sync_remote()

    console.log("Step 2: Updating existing remote files from local changes...")
    with console.status("Updating..."):
        b.update_remote(remote=True, local=False)


@cli.command(help="Update files in Bookstack or Obsidian")
@click.pass_context
@click.option(
    "-r",
    "--remote",
    flag_value="remote",
    is_flag=True,
    help="Update remote pages from local copies",
)
@click.option(
    "-l",
    "--local",
    flag_value="local",
    is_flag=True,
    help="Update local pages from from copies",
)
def update(ctx, remote, local):
    b = ctx.obj.get("bookstack")
    if not any([remote, local]):
        raise click.UsageError("Please provide at least one of --remote or --local")
    if remote:
        with console.status("Updating remote files..."):
            b.update_remote(remote=True, local=False)
    elif local:
        with console.status("Updating local files..."):
            b.update_remote(remote=False, local=True)


@cli.command(help="Delete Bookstack and Obsidian object")
@click.pass_context
@click.option("--shelf", is_flag=True, help="Delete a shelf")
@click.option("--book", is_flag=True, help="Delete a book")
@click.option("--chapter", is_flag=True, help="Delete a chapter")
@click.option("--page", is_flag=True, help="Delete a page")
@click.argument("path", required=True)
def delete(ctx, shelf, book, chapter, page, path):
    b = ctx.obj.get("bookstack")
    if not any([shelf, book, chapter, page]):
        raise click.UsageError(
            "Please provide at least one of --shelf, --book, --chapter, or --page"
        )

    if shelf:
        with console.status(f"Deleting shelf at {path}"):
            b.delete(BookstackItems.SHELF, path)
    elif book:
        with console.status(f"Deleting book at {path}"):
            b.delete(BookstackItems.BOOK, path)
    elif chapter:
        with console.status(f"Deleting chapter at {path}"):
            b.delete(BookstackItems.CHAPTER, path)
    elif page:
        with console.status(f"Deleting page at {path}"):
            b.delete(BookstackItems.PAGE, path)


def main():
    cli()


if __name__ == "__main__":
    main()
