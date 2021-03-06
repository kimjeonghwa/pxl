import jinja2
import shutil

from pathlib import Path

import pxl.state as state


def build(
    overview: state.Overview,
    output_dir: Path,
    template_dir: Path,
    bucket_puburl: str,
    public_image_url: str,
) -> None:
    """Build a static site based on the state."""

    index_template = load_template(template_dir / "index.html.j2")
    album_template = load_template(template_dir / "album.html.j2")
    photo_template = load_template(template_dir / "photo.html.j2")

    clear_directory(output_dir)
    output_dir.mkdir(exist_ok=True)

    shutil.copytree(template_dir / "css", output_dir / "css")
    shutil.copytree(template_dir / "js", output_dir / "js")
    shutil.copy(template_dir / "404.html", output_dir / "404.html")

    img_baseurl = public_image_url or bucket_puburl

    with (output_dir / "index.html").open("w+") as f:
        index_template.stream(overview=overview, img_baseurl=img_baseurl).dump(f)

    for album in overview.albums:
        album_dir = output_dir / album.name_nav
        album_dir.mkdir()

        with (album_dir / "index.html").open("w+") as f:
            album_template.stream(album=album, img_baseurl=img_baseurl).dump(f)

        for i, image in enumerate(album.images):
            image_dir = album_dir / str(image.remote_uuid)
            image_dir.mkdir()

            title = f"{album.name_display} - {i} / {len(album.images) - 1}"

            with (image_dir / "index.html").open("w+") as f:
                img_prev = album.images[i - 1] if i - 1 >= 0 else None
                img_next = album.images[i + 1] if i + 1 < len(album.images) else None

                photo_template.stream(
                    img=image,
                    img_prev=img_prev,
                    img_next=img_next,
                    img_baseurl=img_baseurl,
                    album_name=album.name_nav,
                    title=title,
                ).dump(f)


def load_template(template_file: Path) -> jinja2.Template:
    """Load a jinja template from a file.

    There isn't a method in the standard API that does this, so
    we roll it ourselves."""

    with template_file.open() as f:
        return jinja2.Template(f.read())


def clear_directory(dir_path: Path) -> None:
    """Remove all directory contents, except for the directory itself.

    This is useful so the inode number for the directory doesn't get removed
    and HTTP servers and the like keep on working."""

    if not dir_path.exists():
        return

    assert dir_path.is_dir()

    for entry in dir_path.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
