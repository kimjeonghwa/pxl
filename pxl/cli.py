import click
import datetime
import getpass
import json
import sys

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pxl.config as config
import pxl.generate as generate
import pxl.state as state
import pxl.upload as upload


@click.group(name="pxl")
def cli():
    """Photo management script for S3 albums."""


@cli.command(name="init")
@click.option("--force", is_flag=True, default=False)
def init_cmd(force: bool):
    """Initialize pxl configuration"""
    if config.is_initialized() and not force:
        print("pxl is already initiated. Add `--force` to override.")
        sys.exit(1)

    print("We need some information. Please answer the prompts.")
    print("Defaults are between parentheses.")
    print()

    s3_endpoint = get_input(
        "S3 endpoint ({default}): ", default="digitaloceanspaces.com"
    )
    s3_region = get_input("S3 region ({default}): ", default="ams3")
    s3_bucket = get_input("S3 bucket: ")
    s3_key_id = get_input("S3 key ID: ")
    s3_key_secret = get_input("S3 key secret (not echoed): ", hide_input=True)

    cfg = config.Config(s3_endpoint, s3_region, s3_bucket, s3_key_id, s3_key_secret)

    config.save(cfg)


@cli.command(name="clean")
def clean_cmd():
    """Clean pxl files from system"""
    print("This operation will remove your `pxl` configuration.")
    print("Any deployed files or uploaded images are unaffected.")
    print("")

    confirmation = input("Do you want to continue? [y/N] ")
    if confirmation.lower() != "y":
        print("Not confirmed. Exiting.")
        sys.exit(0)

    config.clean()


@cli.command(name="upload")
@click.argument("dir_name")
@click.option("--force", is_flag=True, type=bool, help="Force break lock")
def upload_cmd(dir_name: str, force: bool) -> None:
    """
    Upload a directory to the photo hosting.
    """
    cfg = config.load()

    dir_path = Path(dir_name)
    if not dir_path.is_dir():
        print(f"{dir_path} is not a directory.")

    with upload.client(cfg, break_lock=force) as client:
        album_name = get_input(
            "What name should the album have? ({default}) ",
            default=dir_path.name.title(),
        )

        try:
            pxl_state_json = upload.get_json(client, "state.json")
            pxl_state = state.Overview.from_json(pxl_state_json)
        except client.boto.exceptions.NoSuchKey as e:
            pxl_state = state.Overview.empty()
        except Exception as e:
            print(e)
            sys.exit(1)

        print(pxl_state)

        # Get existing album with this name for appending.
        album = pxl_state.get_album_by_name(album_name)
        if album:
            append_confirm = get_input(
                "Appending to existing album ok? [Y/n] ",
                default="y",
                validate=lambda x: x.lower() in ["y", "n"],
            )
            if append_confirm == "n":
                print("Not appending. Choose a different album name.")
                sys.exit(1)
        else:
            print("Creating new album.")
            album = state.Album(
                name_display=album_name,
                name_nav=album_name.lower().replace(" ", "-"),
                created=datetime.datetime.now(),
                images=[],
            )

        # Find all files with known JPEG extensions. We don't
        # traverse nested directories, just the toplevel.
        for entry in dir_path.iterdir():
            if not entry.is_file():
                continue

            if not entry.suffix.lower() in [".jpeg", ".jpg"]:
                continue

            image = upload.public_image_with_size(client, entry)
            album = album.add_image(image)

        pxl_state = pxl_state.add_or_replace_album(album)
        upload.private_json(client, json.dumps(pxl_state.to_json()), "state.json")


@cli.command("build")
def build_cmd():
    """Build a static site based on current state."""
    print("Building site...")
    # TODO: parameterize
    output_dir = Path.cwd() / "build"
    design_dir = Path.cwd() / "design"

    cfg = config.load()
    with upload.client(cfg) as client:
        try:
            pxl_state_json = upload.get_json(client, "state.json")
            overview = state.Overview.from_json(pxl_state_json)
        except client.boto.exceptions.NoSuchKey as e:
            print("Remote state not found. Please upload before continuing.")
            sys.exit(1)
        except Exception as e:
            print(e)
            sys.exit(1)

        bucket_puburl = f"https://{cfg.s3_bucket}.{cfg.s3_region}.{cfg.s3_endpoint}"

        generate.build(
            overview=overview,
            output_dir=output_dir,
            template_dir=design_dir,
            bucket_puburl=bucket_puburl,
        )
    print("Done.")


def get_input(
    prompt: str,
    default: Optional[str] = None,
    hide_input: bool = False,
    validate: Callable[[str], bool] = lambda x: True,
) -> str:
    """
    Utility for common user input scenario's.

    Supports defaults, hiding the input by the user (useful for sensitive
    information). Accepts a validate callback and reprompts the user if
    this callback fails.
    """
    # Slightly magic behavior: if the default is set, we call the
    # format method with the default on the string. This means the
    # user is shown the default.
    if default:
        prompt = prompt.format(default=default)

    while True:
        user_input = (getpass.getpass(prompt) if hide_input else input(prompt)).strip()
        if user_input == "" and default:
            return default
        if validate(user_input):
            return user_input


def main():
    cli()
