"""a JupyterLite addon for jupyterlab core"""
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

import doit
from traitlets import Instance, default

from ..constants import JUPYTERLITE_JSON, UTF8
from .base import BaseAddon


class StaticAddon(BaseAddon):
    """Copy the core "gold master" artifacts into the output folder"""

    app_archive = Instance(
        Path,
        help=(
            """The path to a custom npm-style tarball (e.g. with `package/package.json`). """
            """This may alternately be specified with the `$JUPYTERLITE_APP_ARCHIVE` """
            """environment variable."""
        ),
    ).tag(config=True)

    __all__ = ["pre_init", "init", "post_init", "pre_status"]

    def pre_status(self, manager):
        yield dict(
            name=JUPYTERLITE_JSON,
            actions=[
                lambda: print(
                    f"""    tarball:      {self.app_archive.name} """
                    f"""{int(self.app_archive.stat().st_size / (1024 * 1024))}MB"""
                    if self.app_archive.exists()
                    else "    tarball:      none"
                ),
                lambda: print(f"""    output:         {self.manager.output_dir}"""),
                lambda: print(f"""    lite dir:       {self.manager.lite_dir}"""),
                lambda: print(f"""    apps:           {self.manager.apps}"""),
                lambda: print(
                    f"""    sourcemaps:     {not self.manager.no_sourcemaps}"""
                ),
            ],
        )

    def pre_init(self, manager):
        """well before anything else, we need to ensure that the output_dir exists
        and is empty (if the baseline tarball has changed)
        """
        output_dir = manager.output_dir

        yield dict(
            name="output_dir",
            doc="clean out the lite directory",
            file_dep=[self.app_archive],
            uptodate=[
                doit.tools.config_changed(
                    dict(
                        apps=self.manager.apps,
                        no_sourcemaps=self.manager.no_sourcemaps,
                    )
                )
            ],
            actions=[
                lambda: [output_dir.exists() and shutil.rmtree(output_dir), None][-1],
                (doit.tools.create_folder, [output_dir]),
            ],
        )

    def init(self, manager):
        """unpack and copy the tarball files into the output_dir"""
        yield dict(
            name="unpack",
            doc=f"unpack a 'gold master' JupyterLite from {self.app_archive.name}",
            actions=[(self._unpack_stdlib, [])],
            file_dep=[self.app_archive],
            targets=[manager.output_dir / JUPYTERLITE_JSON],
        )

    def post_init(self, manager):
        """maybe remove sourcemaps, or all static assets if an app is not installed"""
        output_dir = manager.output_dir
        pkg_json = output_dir / "package.json"
        pkg_data = json.loads(pkg_json.read_text(**UTF8))

        all_apps = set(pkg_data["jupyterlite"]["apps"])
        mgr_apps = set(manager.apps if manager.apps else all_apps)

        for to_remove in all_apps - mgr_apps:
            app = output_dir / to_remove
            if app.exists():
                yield dict(name=f"prune:{app}", actions=[(self.delete_one, [app])])

    @default("app_archive")
    def _default_app_archive(self):
        return self.manager.app_archive

    def _unpack_stdlib(self):
        """use bog-standard python tarfiles.

        TODO: a libarchive-based backend, which is already ported to WASM
        """
        output_dir = self.manager.output_dir

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            with tarfile.open(str(self.app_archive), "r:gz") as tar:
                tar.extractall(td)
                self.copy_one(tdp / "package", output_dir)

        self.maybe_timestamp(output_dir)
